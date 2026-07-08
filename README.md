# custom-shirts

A parametric work/casual button-up shirt, authored in code.

**The design goal:** the slim fit + length of a Banana Republic shirt, the
durable detailing of a Vietnam-era cotton/poly fatigue shirt (square patch
pockets, barrel cuffs), without reading as dressy. Wearable to work or anywhere.

**The pipeline:**

```
   code (FreeSewing v4)  ->  SVG panels  ->  Blender (3D drape on a body)  ->  iterate
                                         \
                                          ->  ShopBot + drag knife (cut fabric)  ->  sew
```

We author the pattern as code so fit and detailing are independent, tunable
knobs, and so visualizing/iterating never requires cutting fabric until it's
close.

## Layout

| Path | What it is |
|---|---|
| `src/measurements.mjs` | Your body measurements (mm). **Edit these first.** |
| `src/options.mjs` | Design knobs — fit ease, cuff style, pocket size. |
| `src/parts/pocket.mjs` | Square army-style patch pocket (custom part). |
| `src/parts/pocketFlap.mjs` | Button-down flap for the pocket (custom part). |
| `src/index.mjs` | The design: extends FreeSewing's **Simon** shirt + our pockets. |
| `render.mjs` | Drafts and writes SVG to `dist/`. |
| `export-garment.mjs` | Builds `dist/garment.json`, the **source of truth** (panels + named edges + stitch graph). |
| `newton_drape.py` | Derives the 3D GPU cloth drape from `garment.json` (Newton/Style3D). |

We reuse the **Simon** button-up block (it already ships a yoke, barrel cuffs,
collar + stand, and button plackets) and add the fatigue-shirt pockets. Keeping
the collar/neckline and cuff/sleeve from one block means those fussy
dimensional grafts stay consistent.

## Use

Everything is wired through a `Makefile` (run `make help` to list targets):

```bash
make drape-gl       # ** interactive GPU cloth drape ** — live window, orbit w/ mouse
make drape          # headless drape -> OBJ -> Blender still (dist/newton/drape*.png)
make render         # flat pattern -> dist/workshirt-all.svg + dist/parts/*.svg
make nest           # ShopBot cut layout -> dist/cut-layout.svg  (BED_W=1400 SA=10)
make assemble       # static 3D assembly (no physics) -> dist/assembly.png + .blend
make flatten        # ** reverse ** unfold a 3D panel mesh -> flat 2D pattern (see tools/)
make segment        # ** reverse ** split a 3D garment mesh into panels by marked seams
make setup          # one-time: create .venv, install Newton + tool deps
```

Knobs are Make variables: `make drape-gl FRAMES=400 MAXAREA=70`, `make render SA=0`
(net seamlines), `make nest BED_W=<mm>`. The npm scripts still exist as an
alternative (`npm run render|nest|panels|assemble`).

### The source of truth: `dist/garment.json`

A garment is **not** its 3D shape. It is a declarative spec, and everything else
is derived from it:

- **body** measurements,
- **panel templates** — a 2D outline whose boundary is split into **named edges**
  (`neckline`, `shoulder`, `armhole`, `side`, `hem`, `centerFront`/`centerBack`),
- **instances** — a template placed in the garment (mirror + which face),
- a **stitch graph** — explicit `[instance, edge] ↔ [instance, edge]` seams,
- a **neckband** constraint (the collar holds the neck opening to neck size),
- **fabric** properties.

`make garment` (→ `export-garment.mjs`) generates it from the FreeSewing draft.
Both the flat pattern (for cutting) and the 3D drape read from this one document,
so editing the FreeSewing params or the stitch graph keeps them consistent — the
round-trip substrate. Add sleeves/collar by adding a template + rows to the
stitch graph, not by writing new geometry.

### 3D cloth drape (Newton / Style3D)

`make drape-gl` **derives** a GPU cloth drape from `garment.json`, using
[Newton](https://github.com/newton-physics/newton)'s **Style3D** garment solver
(`newton_drape.py`). It triangulates each template, lays the instances on a
parametric torso, stitches **exactly** the graph edges, holds the neckline to a
neck-sized ring, and relaxes under gravity + collision. Requires an NVIDIA GPU
(CUDA 12, driver 545+) and the `.venv` from `make setup`.

> Status: a settled shirt draped on **Newton's Style3D "Female" avatar** (a real
> human body, retargeted into our frame — `BODY=param` falls back to the
> parametric torso+arms). The render **colour-codes each pattern piece**
> (front / back / sleeve) over a ghosted body, so the drape reads as the *pattern*
> — the colour boundaries are the seams (side, armscye, neckline). Caveat: the
> avatar is **female and fixed-size**, so the fit shown is on her, not your
> measurements. Refinements outstanding: collar "wings" where the neck funnel
> meets the shoulder fold, sleeve length/coverage, avatar alignment
> (`AV_SHOULDER` / `AV_SCALE` / `AV_FLIP`). **Cuffs and a collar band** are the
> next spec additions. Tune live in `--viewer gl`: `FRAMES`, `MAXAREA`,
> `ARM_DROP` (arm pose), `NECK_R`.

### Adding a garment part

Because the garment is a spec, adding a part is data, not new geometry code.
Sleeves are the worked example — they took a template, two instances, two stitch
rules, and one placement function:

1. **Template** (`export-garment.mjs`) — sample the FreeSewing part's seam and
   split its boundary into **named edges** at the landmark points:
   ```
   sleeve.edges = { cap, underarmRight, underarmLeft, wrist }
   ```
2. **Instances** — place the template one or more times:
   ```
   sleeveR: { template: 'sleeve', side: 'R' },  sleeveL: { … 'L' }
   ```
3. **Stitches** — add rows to the seam graph. A stitch's `b` side may be a single
   `[instance, edge]` or a **list** (one edge sewing to several):
   ```
   { kind: 'armscye',    a: ['sleeveR','cap'],           b: [['frontR','armhole'], ['backR','armhole']] }
   { kind: 'sleeveSeam', a: ['sleeveR','underarmRight'], b: ['sleeveR','underarmLeft'] }
   ```
4. **Placement** (`newton_drape.py`) — only if the part isn't a body panel that
   the default `wrap()` handles. The sleeve gets `place_sleeve()`, which lofts the
   flat panel from the armhole ring (at the cap) to a wrist circle, and a capsule
   arm collider so it drapes over something.

Cuffs (`wrist ↔ cuff`) and a collar band (`neckline ↔ collar`) are the same four
steps.

### Drape gotchas (Newton / Style3D)

- **Mirror only the 3D placement, not `panel_verts`.** Negating the flat rest
  coordinates flips triangle winding; Style3D's `panel_areas > 0` filter then
  drops every triangle and crashes on an empty edge array.
- **Collider normals must face outward.** An inside-out torso mesh produces no
  contacts and the cloth free-falls through it. `torso_mesh()` flips faces to
  radial-outward.
- **Weld seams; don't spring them.** SolverStyle3D does *not* integrate generic
  `add_spring` springs (its only spring is the interactive drag tool), so sewing
  by springs silently does nothing — seams drift open. A seam is *shared
  topology*: merge the coincident seam vertices into one particle (union-find
  over the stitch graph), pass the welded 3D `indices` while keeping each panel's
  flat pattern as its own `panel_verts` / `panel_indices` UV island. Drop any
  triangle the weld collapses (its BVH will assert otherwise).
- **Don't compress a region to a point.** Collapsing the sleeve-cap interior to a
  single ring made both sleeves explode to −15 m. Spread verts with the loft.
- **Damp hanging seams.** Newton's default spring damping is 0; an undamped,
  heavy hanging piece (a sleeve) resonates off. Use `KD > 0`, and pin the cap to
  the armhole ring as a stable anchor.
- **Pinning on the collider surface → NaN.** A pinned vertex sitting exactly on
  the collider fights its own contact. Keep pins clear of colliders (the neck
  ring sits above the capped-off torso top).
- **Body pokes through the cloth → firm contact + per-substep `collide`.** Soft
  body contact (`soft_contact_ke` ~10) barely pushes the cloth off the collider,
  so the mannequin shows through. Match `cloth_h1`: `soft_contact_ke = 5e3`,
  frictionless, `iterations=10` — but then call `model.collide` **every substep**
  (once-per-frame lets contacts go stale and the firm penalty overshoots into
  buzz). It still CUDA-graph-captures, so speed is unchanged.
- **It never settles → damp it and drop self-collision.** SolverStyle3D has no
  global damping and its default air-drag is 0, so cloth oscillates forever; add
  per-substep velocity damping (we scale `particle_qd`). And cloth
  *self*-collision (`solver.collision.stiff_vf/ee/ef`) makes heavy draping folds
  buzz against each other endlessly — we turn it off by default for a clean rest
  (folds may overlap slightly; `SELFCOLLIDE=1` re-enables it). Body/arm contact
  stays on.

`dist/workshirt-all.svg` is the whole pattern laid out (open in any browser).
`dist/parts/<name>.svg` is one millimetre-accurate panel per file.

## Iterating

1. Edit `src/measurements.mjs` with your real numbers. Measure the Banana
   Republic shirt too, to capture the *ease* that makes it slim.
2. `npm run render`, eyeball `dist/workshirt-all.svg`.
3. Tune `src/options.mjs` (fit ease, cuff style, pocket dimensions).
4. When the flat pattern looks right, take the per-part SVGs into Blender for a
   3D drape check before cutting anything (see below).
5. One confirmation muslin, then cut real fabric.

### Fit / detailing knobs

- Simon's full option list: <https://freesewing.org/docs/designs/simon>
- Pocket size/shape and flap: options in `src/parts/*.mjs`
  (`pocketWidth`, `pocketDepth`, `pocketHem`, `pocketTaper`, `flapWidth`,
  `flapDepth`, `flapPoint`).
- Seam allowance: `sa` in `render.mjs` (10 mm). Set to `0` to export net
  seamlines (useful for the Blender drape, where you sew on the seamline).

## Blender drape

`File > Import > SVG` brings each panel in as a curve (1 SVG unit = 1 mm).
Convert curves to mesh, position the panels around an avatar, mark seam edges,
and run cloth sim. Two helper add-ons make this much easier:

- **Seams to Sewing Pattern** — <https://thomaskole.nl/s2s/>
- **Garment Tool** (Blender 4.5+) — design/sew panels into sim-ready cloth.

## Cutting

A CNC router (ShopBot) with a **drag knife** or **rotary/pivoting knife** cuts
the SVG outlines in fabric — preferred over a laser for cotton/poly (no scorched
or melted edges). Export the cut outlines (set `sa` as desired), bring the
SVG/DXF into your CAM (VCarve/Aspire), generate profile toolpaths with a
drag-knife post-processor, and hold the fabric flat (vacuum table or
adhesive-backed sheet).

## Versions

Pinned to the FreeSewing **v4.9.0** family. Note: FreeSewing dropped its
official DXF exporter after v2, so this project targets SVG (which Blender
imports natively); convert SVG→DXF in CAM only if your cutter needs DXF.
