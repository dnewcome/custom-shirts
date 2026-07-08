# tools/ — the round-trip pattern toolkit

The main project goes **pattern → 3D** (FreeSewing → `garment.json` → Newton drape).
These tools are the **reverse and the remix**: take a real garment, a photo, or a
3D sculpt, get it into 3D, edit it, and unfold it back into a **flat sewing
pattern**. The `garment.json` spec is the hub everything passes through.

```
   photos ─┐
  scan ────┤→  3D mesh ──(segment)──→ panels ──(flatten)──→ 2D pattern ──→ sew
  sculpt ──┘        ↑                                            │
                    └──────────── edit / remix in 3D ───────────┘
                                        │
                                 garment.json (spec, the hub)
```

## Tools

| Tool | Stage | What it does | Status |
|---|---|---|---|
| (photogrammetry / scan) | capture | photos/scan → 3D mesh (COLMAP, Polycam, structured-light) | external; the finicky part (see below) |
| `segment.py` (Blender) | segment | mark seams on a mesh → cut into panel meshes (OBJ) | **works** (`make segment`) |
| `flatten.py` (libigl) | flatten | a 3D panel mesh → flat 2D pattern (ARAP, isometric) + SVG | **works for developable panels** (`make flatten`) |
| edit / remix | — | sculpt/kitbash panels in Blender, or tune the spec | manual (Blender) |

## flatten.py — 3D panel → 2D pattern

As-rigid-as-possible (isometric, length-preserving) unfolding — the right energy
for fabric, which bends but barely stretches. Reports per-triangle **stretch**
(1.0 = perfect isometry); high stretch flags a piece that isn't developable.

```bash
make flatten FLAT_MESH=dist/newton/shirt_front.obj      # -> dist/newton/shirt_front_flat.svg
```

Validated against ground truth: flattening our own draped **front** recovers a
clean panel at **stretch mean 1.001** (±3.5%). Known limits:

- **Tubes need a cut.** A closed piece (a sewn sleeve = a cylinder) can't flatten
  to a plane — it reports high distortion. Cut it along its seam first
  (`segment.py` with the underarm seam marked), then flatten the open panel.
- **Darts / stretch** in a non-developable region show as residual distortion;
  add darts or accept the approximation.

## segment.py — 3D garment → panel meshes

```bash
# in Blender GUI: open the mesh, Edit Mode, select seam edges, Mark Seam, save. Then:
make segment MESH_IN=scan.obj OUT=dist/panels3d       # -> dist/panels3d/panel_*.obj
```
Cuts along marked seams and writes one OBJ per panel (falls back to connected
components if no seams are marked). Feed each `panel_*.obj` to `flatten.py`.

## Capture (stage 1, external, the hard part)

Photogrammetry of fabric fights you: textureless surfaces don't reconstruct
(add speckle/markers, or use busy/printed fabric), it must hold one rigid shape
(stuff/pin it on a form), and it's a thin double surface. A **structured-light or
line-laser scan is more reliable** than photos for plain fabric. For simply
*copying* a garment you own, the traditional **rub-off** (trace it panel by
panel) is still the most accurate route.

## Roadmap

- Seam-aware tube cutting in `flatten.py` so sleeves/collars flatten without a manual cut.
- Flatten output → back into `garment.json` (imported garment becomes editable spec).
- Seam allowance + notches/grainlines on the flattened SVG for cutting.
- Capture recipe (a tested photogrammetry/structured-light workflow for a garment).
