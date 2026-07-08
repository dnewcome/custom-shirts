"""
Blender drape: import the FreeSewing front/back panels, mirror each half to full
width, hang them from the shoulder line, and let cloth sim drape them over a body
form. Renders to dist/drape.png.

Run:  /opt/blender-5.0.1-linux-x64/blender --background --python drape.py

This is a first-pass drape: the side seams are NOT sewn yet (panels hang open at
the sides). It shows fabric, length, and silhouette of OUR pattern on a body —
the proof that the code->SVG->3D pipeline is connected. Sewing the seams shut is
the next iteration.
"""
import bpy, bmesh, json, math, os
from mathutils import Vector

MM = 0.001
HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(HERE, "dist", "panels.json")))
M = data["measurements"]

# ---- clean scene ----------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
coll = scene.collection


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


def build_panel(name, outline, y_offset, cell=8.0):
    """Build a clean quad-grid mesh clipped to the half outline, then mirror to
    full width. Quad grids drape far more stably than a triangulated n-gon."""
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
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
    # mirror the half to full width across the center fold (X=0)
    mir = ob.modifiers.new("mir", "MIRROR")
    mir.use_axis = (True, False, False)
    mir.use_mirror_merge = True
    mir.merge_threshold = 0.003
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier="mir")
    ob.location.y = y_offset
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
    return ob


# ---- body form ------------------------------------------------------------
# Elliptical torso sized from chest/waist; top at the shoulders, down past hem.
a = M["chest"] * MM / 4.0 * 0.86          # half width  (X)
b = a * 0.52                               # half depth  (Y) — realistic torso depth
top_z = 0.02                               # shoulder line
hem_z = -M["hpsToWaistBack"] * MM - M["waistToHips"] * MM - 0.15
h = top_z - hem_z
bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=1.0, depth=h,
                                    location=(0, 0, (top_z + hem_z) / 2.0))
torso = bpy.context.active_object
torso.name = "body"
torso.scale = (a, b, 1.0)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
bpy.ops.object.shade_smooth()
torso.modifiers.new("col", "COLLISION")

# Shoulder support: a flattened dome wider than the chest, so the sewn shirt
# rests on the shoulders instead of sliding down.
bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=20, radius=1.0,
                                     location=(0, 0, 0.0))
shoulders = bpy.context.active_object
shoulders.name = "shoulders"
shoulders.scale = (a * 1.1, b * 1.0, 0.07)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
bpy.ops.object.shade_smooth()
shoulders.modifiers.new("col", "COLLISION")

# ---- panels ---------------------------------------------------------------
gap = b + 0.010
front = build_panel("front", data["panels"]["front"]["outline"], -gap)
back = build_panel("back", data["panels"]["back"]["outline"], +gap)

# join into one cloth object so they share a sim (required for sewing springs)
bpy.ops.object.select_all(action="DESELECT")
front.select_set(True)
back.select_set(True)
bpy.context.view_layer.objects.active = front
bpy.ops.object.join()
shirt = bpy.context.active_object
shirt.name = "shirt"

# ---- sew the seams (loose edges -> cloth sewing springs) ------------------
# Landmarks (mm): underarm y=262, hem y=738, shoulder x~235 z~-35, neck x~84.
UNDERARM_Z, HEM_Z = -0.262, -0.738
me = shirt.data
bm = bmesh.new()
bm.from_mesh(me)
bm.verts.ensure_lookup_table()
boundary = [v for v in bm.verts if any(len(e.link_faces) == 1 for e in v.link_edges)]


def zip_edges(a_list, b_list):
    n = min(len(a_list), len(b_list))
    made = 0
    if n == 0:
        return 0
    for i in range(n):
        va = a_list[int(i * len(a_list) / n)]
        vb = b_list[int(i * len(b_list) / n)]
        try:
            bm.edges.new((va, vb))
            made += 1
        except ValueError:
            pass
    return made


sewn = 0
for side in (+1, -1):  # right, left
    # side seam: outer-X boundary verts between hem and underarm
    f_side = sorted([v for v in boundary if v.co.x * side > 0.20
                     and HEM_Z + 0.01 < v.co.z < UNDERARM_Z and v.co.y < 0], key=lambda v: v.co.z)
    b_side = sorted([v for v in boundary if v.co.x * side > 0.20
                     and HEM_Z + 0.01 < v.co.z < UNDERARM_Z and v.co.y > 0], key=lambda v: v.co.z)
    sewn += zip_edges(f_side, b_side)
    # shoulder seam: top edge between neck and shoulder tip
    f_sh = sorted([v for v in boundary if v.co.z > -0.05 and 0.07 < abs(v.co.x) < 0.25
                   and v.co.x * side > 0 and v.co.y < 0], key=lambda v: abs(v.co.x))
    b_sh = sorted([v for v in boundary if v.co.z > -0.05 and 0.07 < abs(v.co.x) < 0.25
                   and v.co.x * side > 0 and v.co.y > 0], key=lambda v: abs(v.co.x))
    sewn += zip_edges(f_sh, b_sh)
bm.to_mesh(me)
bm.free()
print("created %d sewing edges" % sewn)

# Pin the BACK's top edge (neck + shoulders) so the garment hangs from the
# shoulders like a cape; the front is then sewn up to it and drapes around the
# body. This holds it up without locking the shoulder seams open.
grp = shirt.vertex_groups.new(name="pin")
pin_idx = [v.index for v in me.vertices if v.co.y > 0.05 and v.co.z > -0.08]
grp.add(pin_idx, 1.0, "REPLACE")
print("pinned %d back-top verts" % len(pin_idx))

# ---- cloth ----------------------------------------------------------------
cl = shirt.modifiers.new("cloth", "CLOTH")
cs = cl.settings
cs.quality = 8
cs.mass = 0.25
cs.tension_stiffness = 15
cs.compression_stiffness = 15
cs.shear_stiffness = 5
cs.bending_stiffness = 1.5
cs.vertex_group_mass = "pin"       # pin the back top edge
cs.pin_stiffness = 1.0
if hasattr(cs, "use_sewing_springs"):
    cs.use_sewing_springs = True
    cs.sewing_force_max = 1.5
col = cl.collision_settings
col.collision_quality = 5
col.distance_min = 0.006
col.use_self_collision = False     # self-collision was blowing the sim up

# ---- materials ------------------------------------------------------------
def mat(name, rgb, rough=0.85):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    return m

shirt.data.materials.append(mat("fatigue", (0.21, 0.23, 0.13)))      # olive drab
torso.data.materials.append(mat("form", (0.55, 0.50, 0.46), 0.9))    # mannequin gray

# ---- camera, light, world -------------------------------------------------
target = bpy.data.objects.new("target", None)
coll.objects.link(target)
target.location = (0, 0, -0.32)

cam_data = bpy.data.cameras.new("cam")
cam_data.lens = 55
cam = bpy.data.objects.new("cam", cam_data)
coll.objects.link(cam)
cam.location = (1.25, -1.55, 0.02)   # 3/4 view
tc = cam.constraints.new("TRACK_TO")
tc.target = target
tc.track_axis = "TRACK_NEGATIVE_Z"
tc.up_axis = "UP_Y"
scene.camera = cam

sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
coll.objects.link(sun)
sun.data.energy = 4.0
sun.rotation_euler = (math.radians(55), math.radians(8), math.radians(40))

fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA"))
coll.objects.link(fill)
fill.data.energy = 60.0
fill.data.size = 1.5
fill.location = (-1.6, -1.2, 0.4)
ftc = fill.constraints.new("TRACK_TO")
ftc.target = target
ftc.track_axis = "TRACK_NEGATIVE_Z"
ftc.up_axis = "UP_Y"

world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.92, 0.93, 0.95, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.7

# ---- render settings ------------------------------------------------------
engine = "BLENDER_WORKBENCH"
for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
    try:
        scene.render.engine = e
        engine = e
        break
    except TypeError:
        continue
if engine == "BLENDER_WORKBENCH":
    scene.render.engine = "BLENDER_WORKBENCH"
    sh = scene.display.shading
    sh.light = "STUDIO"
    sh.color_type = "MATERIAL"   # use the olive material, not flat gray
    sh.show_shadows = True
    sh.show_cavity = True
elif engine == "CYCLES":
    scene.cycles.samples = 48
    scene.cycles.use_denoising = True
scene.render.resolution_x = 820
scene.render.resolution_y = 1060
scene.render.film_transparent = False
scene.render.filepath = os.path.join(HERE, "dist", "drape.png")
print("engine:", engine)

# ---- simulate -------------------------------------------------------------
scene.frame_start = 1
scene.frame_end = 300                    # extra frames for the seams to draw closed
for f in range(scene.frame_start, scene.frame_end + 1):
    scene.frame_set(f)
print("simulated to frame", scene.frame_end)

# smooth shading for the render
bpy.ops.object.select_all(action="DESELECT")
shirt.select_set(True)
bpy.context.view_layer.objects.active = shirt
bpy.ops.object.shade_smooth()

bpy.ops.render.render(write_still=True)
print("rendered ->", scene.render.filepath)
