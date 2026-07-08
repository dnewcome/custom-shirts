"""
Static 3D assembly (no cloth sim): wrap the flat FreeSewing panels onto a body
shape so you can see how the pieces fit together. Pure geometry — each panel is
bent around an elliptical torso; front and back meet at the side seams; patch
pockets sit tangent on the chest; a collar band rings the neck.

Run:  /opt/blender-5.0.1-linux-x64/blender --background --python assemble.py
Out:  dist/assembly.png

Note: a pure cylindrical wrap can't fold the shoulder over the top the way a
worn shirt does, so the torso reads true but the shoulder/armhole is approximate.
"""
import bpy, bmesh, json, math, os
from mathutils import Vector

MM = 0.001
HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "dist", "panels.json")))
M = data["measurements"]

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
coll = scene.collection

# torso ellipse (half-width a in X, half-depth b in Y), sized from chest girth
a = M["chest"] * MM / (2 * math.pi) * 1.25
b = M["chest"] * MM / (2 * math.pi) * 0.78


def mat(name, rgb, rough=0.7):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return m


def point_in_poly(px, py, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def panel_object(name, outline, is_front, material, cell=6.0):
    """Build a grid mesh clipped to the half outline, mirror to full width, then
    wrap each vertex around the torso ellipse. x->angle, z(height) unchanged."""
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    hw = maxx * MM
    nx = int((maxx - minx) / cell) + 2
    ny = int((maxy - miny) / cell) + 2
    bm = bmesh.new()
    vert = {}

    def V(i, j):
        if (i, j) not in vert:
            x = minx + i * cell
            y = miny + j * cell
            vert[(i, j)] = bm.verts.new((x * MM, 0.0, -y * MM))
        return vert[(i, j)]

    for i in range(nx):
        for j in range(ny):
            cx = minx + (i + 0.5) * cell
            cy = miny + (j + 0.5) * cell
            if point_in_poly(cx, cy, outline):
                try:
                    bm.faces.new((V(i, j), V(i + 1, j), V(i + 1, j + 1), V(i, j + 1)))
                except ValueError:
                    pass
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    # mirror half -> full
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    mir = ob.modifiers.new("mir", "MIRROR")
    mir.use_axis = (True, False, False)
    mir.use_mirror_merge = True
    mir.merge_threshold = 0.003
    bpy.ops.object.modifier_apply(modifier="mir")
    # wrap onto the ellipse
    bm2 = bmesh.new()
    bm2.from_mesh(me)
    for v in bm2.verts:
        t = max(-1.0, min(1.0, v.co.x / hw))
        th = t * (math.pi / 2) if is_front else math.pi - t * (math.pi / 2)
        v.co.x = a * math.sin(th)
        v.co.y = -b * math.cos(th)
    bm2.to_mesh(me)
    bm2.free()
    ob.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return ob


def row_span(outline, y):
    """Leftmost/rightmost x where the horizontal line at y crosses the outline."""
    xs = []
    n = len(outline)
    for i in range(n):
        x1, y1 = outline[i]
        x2, y2 = outline[(i + 1) % n]
        if (y1 <= y < y2) or (y2 <= y < y1):
            xs.append(x1 + (x2 - x1) * (y - y1) / (y2 - y1))
    if len(xs) < 2:
        return None
    return min(xs), max(xs)


def build_sleeve(name, outline, S, D, material, cell=10.0):
    """Wrap each horizontal row of the flat sleeve into a circle -> tapered tube
    from the cap (at shoulder point S) down the arm direction D to the wrist."""
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    nx = int((maxx - minx) / cell) + 2
    ny = int((maxy - miny) / cell) + 2
    bm = bmesh.new()
    vert = {}

    def V(i, j):
        if (i, j) not in vert:
            vert[(i, j)] = bm.verts.new((minx + i * cell, 0.0, miny + j * cell))
        return vert[(i, j)]

    for i in range(nx):
        for j in range(ny):
            cx = minx + (i + 0.5) * cell
            cy = miny + (j + 0.5) * cell
            if point_in_poly(cx, cy, outline):
                try:
                    bm.faces.new((V(i, j), V(i + 1, j), V(i + 1, j + 1), V(i, j + 1)))
                except ValueError:
                    pass
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    # wrap
    Dn = D.normalized()
    u = Dn.cross(Vector((0, 0, 1)))
    if u.length < 1e-6:
        u = Vector((1, 0, 0))
    u.normalize()
    w = Dn.cross(u).normalized()
    bm2 = bmesh.new()
    bm2.from_mesh(me)
    wrist_r = [0.0]
    for v in bm2.verts:
        x_mm, y_mm = v.co.x, v.co.z
        span = row_span(outline, y_mm)
        if not span or span[1] - span[0] < 1e-6:
            continue
        xl, xr = span
        t = (x_mm - xl) / (xr - xl)
        phi = t * 2 * math.pi
        r = (xr - xl) * MM / (2 * math.pi)
        arm = (y_mm - miny) * MM
        v.co = S + Dn * arm + u * (r * math.cos(phi)) + w * (r * math.sin(phi))
        wrist_r[0] = r  # last row ~ wrist
    bm2.to_mesh(me)
    bm2.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.data.materials.append(material)
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_smooth()
    span_w = row_span(outline, maxy - cell)
    wr = (span_w[1] - span_w[0]) * MM / (2 * math.pi) if span_w else 0.05
    end = S + Dn * ((maxy - miny) * MM)
    return end, Dn, wr


def add_cuff(name, end, Dn, radius, material):
    """Short band wrapped around the wrist end of a sleeve."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius * 1.06, depth=0.06)
    ob = bpy.context.active_object
    ob.name = name
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(Dn)
    ob.location = end - Dn * 0.015
    ob.data.materials.append(material)
    bpy.ops.object.shade_smooth()
    return ob


def add_pocket(name, theta, z0, wmm, hmm, material):
    """Flat square patch pocket sitting tangent on the body at (theta, z0)."""
    w, h = wmm * MM, hmm * MM
    P = Vector((a * math.sin(theta), -b * math.cos(theta), z0))
    radial = Vector((math.sin(theta), -math.cos(theta), 0)).normalized()
    horiz = Vector((math.cos(theta), math.sin(theta), 0)).normalized()
    up = Vector((0, 0, 1))
    base = P + radial * 0.005
    bm = bmesh.new()
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
    vs = [bm.verts.new(base + horiz * cx + up * cy) for (cx, cy) in corners]
    bm.faces.new(vs)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    ob.data.materials.append(material)
    return ob


# ---- materials (cohesive olive, distinguishable per piece) -----------------
# Same olive family, but strong light/dark contrast so each piece and seam reads.
m_front = mat("front", (0.44, 0.48, 0.29))   # light olive
m_back = mat("back", (0.17, 0.20, 0.12))     # dark olive
m_pocket = mat("pocket", (0.31, 0.25, 0.13)) # brown
m_collar = mat("collar", (0.27, 0.34, 0.20))
m_sleeve = mat("sleeve", (0.30, 0.34, 0.20))  # between front & back tone
m_cuff = mat("cuff", (0.19, 0.22, 0.13))
m_body = mat("body", (0.66, 0.60, 0.55), 0.9)

# ---- shirt body -----------------------------------------------------------
panel_object("front", data["panels"]["front"]["outline"], True, m_front)
panel_object("back", data["panels"]["back"]["outline"], False, m_back)

# ---- sleeves + cuffs ------------------------------------------------------
sleeve_out = data["panels"]["sleeve"]["outline"]
for sgn, nm in ((1, "R"), (-1, "L")):
    S = Vector((sgn * a, 0.0, -0.04))                 # shoulder/armhole top
    D = Vector((sgn * 0.55, 0.0, -1.0))               # down and out
    end, Dn, wr = build_sleeve("sleeve" + nm, sleeve_out, S, D, m_sleeve)
    add_cuff("cuff" + nm, end, Dn, wr, m_cuff)

# ---- pockets (two square chest pockets) -----------------------------------
add_pocket("pocketL", math.radians(-34), -0.20, 130, 150, m_pocket)
add_pocket("pocketR", math.radians(34), -0.20, 130, 150, m_pocket)

# ---- collar (stand band + flared fold-over) -------------------------------
rn = M["neck"] * MM / (2 * math.pi)
# stand: vertical band rising from the neckline
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=rn, depth=0.05, location=(0, 0, 0.0))
stand = bpy.context.active_object
stand.name = "collarStand"
stand.scale = (1.45, 1.0, 1.0)
bpy.ops.object.transform_apply(scale=True)
stand.data.materials.append(m_collar)
bpy.ops.object.shade_smooth()
# fold-over: a cone frustum flaring outward over the top of the stand
bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=rn, radius2=rn * 1.5, depth=0.05,
                                location=(0, 0, 0.05))
fold = bpy.context.active_object
fold.name = "collarFold"
fold.scale = (1.45, 1.0, 1.0)
bpy.ops.object.transform_apply(scale=True)
fold.data.materials.append(m_collar)
bpy.ops.object.shade_smooth()

# ---- head + neck for context ----------------------------------------------
bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=rn * 0.92, depth=0.13, location=(0, 0, 0.075))
neck = bpy.context.active_object
neck.data.materials.append(m_body)
bpy.ops.object.shade_smooth()
bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=24, radius=0.092, location=(0, 0, 0.21))
head = bpy.context.active_object
head.scale = (0.9, 1.0, 1.1)
bpy.ops.object.transform_apply(scale=True)
head.data.materials.append(m_body)
bpy.ops.object.shade_smooth()

# ---- camera, lights, world ------------------------------------------------
target = bpy.data.objects.new("target", None)
coll.objects.link(target)
target.location = (0, 0, -0.30)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 60
coll.objects.link(cam)
cam.location = (1.42, -1.05, 0.08)   # stronger 3/4 to reveal the side seam
tc = cam.constraints.new("TRACK_TO")
tc.target = target
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"
scene.camera = cam

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
coll.objects.link(sun)
sun.data.energy = 3.5
sun.rotation_euler = (math.radians(58), math.radians(6), math.radians(35))
fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA"))
coll.objects.link(fill)
fill.data.energy = 80
fill.data.size = 1.6
fill.location = (-1.7, -1.3, 0.5)
ftc = fill.constraints.new("TRACK_TO")
ftc.target = target
ftc.track_axis = "TRACK_NEGATIVE_Z"
ftc.up_axis = "UP_Y"

world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.93, 0.95, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.45

engine = "BLENDER_WORKBENCH"
for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
    try:
        scene.render.engine = e
        engine = e
        break
    except TypeError:
        continue
if engine == "BLENDER_WORKBENCH":
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"
    sh.show_shadows = True
scene.render.resolution_x = 860
scene.render.resolution_y = 1080
scene.render.filepath = os.path.join(HERE, "dist", "assembly.png")
print("engine:", engine)
bpy.ops.render.render(write_still=True)
print("rendered ->", scene.render.filepath)

# save a .blend you can open in the Blender GUI to rotate / inspect / tweak
blend = os.path.join(HERE, "dist", "assembly.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend)
print("saved ->", blend)
