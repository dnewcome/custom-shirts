"""
segment.py — split a 3D garment mesh into panel meshes for flatten.py (Blender).

The "3D -> panels" step of the reverse pipeline. Input is a captured/sculpted
garment mesh (OBJ/GLB). You mark the SEAMS on it (in Blender: Edit Mode, select
edges, Mark Seam) and save; this script cuts along those seams and writes one
OBJ per resulting panel. With no seams marked it falls back to splitting by
connected components (loose parts).

  blender --background --python tools/segment.py -- <mesh_in> <out_dir>
"""
import bpy, sys, os

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
mesh_in = argv[0] if argv else ""
out_dir = argv[1] if len(argv) > 1 else "dist/panels3d"
os.makedirs(out_dir, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)

ext = os.path.splitext(mesh_in)[1].lower()
if ext == ".obj":
    bpy.ops.wm.obj_import(filepath=mesh_in)
elif ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=mesh_in)
else:
    raise SystemExit(f"unsupported input: {mesh_in}")

obj = next(o for o in bpy.context.scene.objects if o.type == "MESH")
bpy.context.view_layer.objects.active = obj
obj.select_set(True)

# cut along marked seams (if any) so the panels come apart as loose parts
me = obj.data
n_seams = sum(1 for e in me.edges if e.use_seam)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="DESELECT")
if n_seams:
    bpy.ops.object.mode_set(mode="OBJECT")
    for e in me.edges:
        e.select = e.use_seam
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.edge_split(type="EDGE")          # cut the seams open
print(f"[segment] {n_seams} seams marked" + ("" if n_seams else " (none — splitting by loose parts)"))

# separate into loose parts (= panels) and export each
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.mesh.separate(type="LOOSE")
bpy.ops.object.mode_set(mode="OBJECT")

parts = [o for o in bpy.context.scene.objects if o.type == "MESH"]
for i, p in enumerate(sorted(parts, key=lambda o: o.name)):
    bpy.ops.object.select_all(action="DESELECT")
    p.select_set(True); bpy.context.view_layer.objects.active = p
    path = os.path.join(out_dir, f"panel_{i:02d}.obj")
    bpy.ops.wm.obj_export(filepath=path, export_selected_objects=True,
                          export_materials=False, forward_axis="Y", up_axis="Z")
    print(f"[segment] panel_{i:02d}: {len(p.data.polygons)} faces -> {path}")
print(f"[segment] {len(parts)} panel(s) -> {out_dir}  (then: flatten.py <panel>.obj)")
