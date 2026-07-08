"""
Blender render of the Newton drape output (dist/newton/shirt.obj + torso.obj).
Run:  /opt/blender-5.0.1-linux-x64/blender --background --python render_drape.py
Produces dist/newton/drape.png (3/4) and dist/newton/drape_side.png.
"""
import bpy, os, math

HERE = os.path.dirname(os.path.abspath(__file__))
NEW = os.path.join(HERE, "dist", "newton")

# ---- clean slate ----------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
coll = scene.collection

def load_obj(path):
    bpy.ops.wm.obj_import(filepath=path, forward_axis="Y", up_axis="Z")
    return bpy.context.selected_objects[0]

def mat(name, rgb, rough=0.75):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    return m

# ---- garment + body -------------------------------------------------------
shirt = load_obj(os.path.join(NEW, "shirt.obj"))
shirt.name = "shirt"
# panels are separate components; make each one's normals point outward
# (left panels were placed mirrored, so their winding is reversed)
me = shirt.data
bpy.context.view_layer.objects.active = shirt
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.mode_set(mode="OBJECT")
shirt.data.materials.append(mat("cloth", (0.34, 0.38, 0.22), 0.82))  # olive fatigue
bpy.ops.object.shade_smooth()

torso = load_obj(os.path.join(NEW, "torso.obj"))
torso.name = "torso"
torso.data.materials.append(mat("body", (0.62, 0.55, 0.50), 0.6))
bpy.ops.object.shade_smooth()

# ---- camera / lights / world (same recipe as assemble.py) -----------------
target = bpy.data.objects.new("target", None)
coll.objects.link(target)
target.location = (0, 0, -0.34)

cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 60
coll.objects.link(cam)
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
fill.data.energy = 90
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
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5

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
print("engine:", engine)

def render(cam_loc, path):
    cam.location = cam_loc
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("rendered ->", path)

render((1.30, -1.15, 0.05), os.path.join(NEW, "drape.png"))       # 3/4 front
render((0.05, -1.75, -0.10), os.path.join(NEW, "drape_front.png"))  # straight front
render((1.75, 0.05, -0.10), os.path.join(NEW, "drape_side.png"))    # side (seam)
