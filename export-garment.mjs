/*
 * export-garment.mjs — emit dist/garment.json, the SOURCE OF TRUTH.
 *
 * A garment is NOT its 3D shape. It is:
 *   - body measurements
 *   - panel TEMPLATES: a 2D outline (mm) whose boundary is split into NAMED
 *     EDGES (neckline, shoulder, armhole, side, hem, centerFront/Back)
 *   - panel INSTANCES: a template placed in the garment (mirror + which face)
 *   - a STITCH GRAPH: explicit (instance,edge) <-> (instance,edge) seams
 *   - a NECKBAND constraint (the collar holds the neck opening to neck size)
 *   - fabric properties
 *
 * Both the flat pattern (SVG, for cutting) and the 3D drape (Newton) are
 * DERIVED from this one document. Edit the FreeSewing params or the stitch
 * graph here, regenerate, and pattern + visualization stay consistent.
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { WorkShirt } from './src/index.mjs'
import { measurements } from './src/measurements.mjs'
import { options } from './src/options.mjs'

const N = 200                                   // boundary samples per template
const round = (v) => Math.round(v * 100) / 100

const p = new WorkShirt({ measurements, options, sa: 0, complete: false })
p.draft()
const set = p.parts[0]

// Sample a part's seam into N ordered points + the arc-fraction of each landmark.
function sampleTemplate(partName, landmarkNames) {
  const part = set[partName]
  const seam = part.paths.seam
  const L = seam.length()
  const outline = []
  for (let i = 0; i < N; i++) {
    const d = Math.min((i / N) * L + 0.01, L - 0.01)
    const q = seam.shiftAlong(d)
    outline.push([round(q.x), round(q.y)])
  }
  // arc-fraction of each landmark (nearest densely-sampled point on the path)
  const frac = {}
  for (const k of landmarkNames) {
    const pt = part.points[k]
    if (!pt) continue
    let best = 1e18, bf = 0
    for (let i = 0; i <= 2000; i++) {
      const d = Math.min((i / 2000) * L, L - 1e-3)
      const q = seam.shiftAlong(d)
      const dist = (q.x - pt.x) ** 2 + (q.y - pt.y) ** 2
      if (dist < best) { best = dist; bf = d / L }
    }
    frac[k] = bf
  }
  return { outline, frac, L: round(L) }
}

// Assign each outline index to a named edge given ordered [name, loFrac, hiFrac].
function segment(outline, ranges) {
  const edges = {}
  for (const [name] of ranges) edges[name] = []
  for (let i = 0; i < outline.length; i++) {
    const f = i / outline.length
    for (const [name, lo, hi] of ranges) {
      if (f >= lo && f < hi) { edges[name].push(i); break }
    }
  }
  return edges
}

// ---- FRONT: cfNeck -> (centerFront + hem) -> side -> armhole -> shoulder -> neckline
const F = sampleTemplate('brian.front', ['cfNeck', 'hem', 'armhole', 'shoulder', 'hps'])
let fEdges = segment(F.outline, [
  ['cfhem', 0.0, F.frac.hem],           // centerFront + hem combined (no landmark at the corner)
  ['side', F.frac.hem, F.frac.armhole],
  ['armhole', F.frac.armhole, F.frac.shoulder],
  ['shoulder', F.frac.shoulder, F.frac.hps],
  ['neckline', F.frac.hps, 1.0001],
])
// split cfhem at the center-bottom corner: centerFront is x~0, hem is y~max
{
  const idx = fEdges.cfhem
  const cf = [], hem = []
  for (const i of idx) (F.outline[i][0] < 8 ? cf : hem).push(i)
  fEdges.centerFront = cf; fEdges.hem = hem; delete fEdges.cfhem
}

// ---- BACK: cbNeck -> centerBack -> hem -> side -> armhole -> shoulder -> neckline
const B = sampleTemplate('brian.back', ['cbHem', 'hem', 'armhole', 'shoulder', 'hps'])
const bEdges = segment(B.outline, [
  ['centerBack', 0.0, B.frac.cbHem],
  ['hem', B.frac.cbHem, B.frac.hem],
  ['side', B.frac.hem, B.frac.armhole],
  ['armhole', B.frac.armhole, B.frac.shoulder],
  ['shoulder', B.frac.shoulder, B.frac.hps],
  ['neckline', B.frac.hps, 1.0001],
])

// ---- SLEEVE: wristRight -> underarmRight -> cap (over the top) -> underarmLeft -> wrist
const S = sampleTemplate('simon.sleeve', ['wristRight', 'bicepsRight', 'bicepsLeft', 'wristLeft'])
const sEdges = segment(S.outline, [
  ['underarmRight', 0.0, S.frac.bicepsRight],   // wristRight -> bicepsRight (front side edge)
  ['cap', S.frac.bicepsRight, S.frac.bicepsLeft], // the sleeve head (sews to the armhole)
  ['underarmLeft', S.frac.bicepsLeft, S.frac.wristLeft],
  ['wrist', S.frac.wristLeft, 1.0001],
])

const garment = {
  units: 'mm',
  measurements,
  // heavier cotton/poly twill: more mass (hangs straighter) + much stiffer
  // bending (fewer, larger folds — reads as thick, not papery).
  fabric: { density: 0.48, tri_aniso_ke: [1.5e2, 1.5e2, 2e1], edge_aniso_ke: [3e-4, 1.6e-4, 8e-5] },
  templates: {
    front: { outline: F.outline, edges: fEdges },
    back: { outline: B.outline, edges: bEdges },
    sleeve: { outline: S.outline, edges: sEdges },
  },
  // instances: body panels placed as (side sx=+right/-left, face fy=-front/+back);
  // sleeves placed by `side` (their cap is lofted onto the armhole ring).
  instances: {
    frontR: { template: 'front', sx: +1, fy: -1 },
    frontL: { template: 'front', sx: -1, fy: -1 },
    backR: { template: 'back', sx: +1, fy: +1 },
    backL: { template: 'back', sx: -1, fy: +1 },
    sleeveR: { template: 'sleeve', side: 'R' },
    sleeveL: { template: 'sleeve', side: 'L' },
  },
  // explicit seam graph: [instance, edge] <-> [instance, edge] (b may be a list)
  stitches: [
    { kind: 'side', a: ['frontR', 'side'], b: ['backR', 'side'] },
    { kind: 'side', a: ['frontL', 'side'], b: ['backL', 'side'] },
    { kind: 'shoulder', a: ['frontR', 'shoulder'], b: ['backR', 'shoulder'] },
    { kind: 'shoulder', a: ['frontL', 'shoulder'], b: ['backL', 'shoulder'] },
    { kind: 'placket', a: ['frontR', 'centerFront'], b: ['frontL', 'centerFront'] },
    { kind: 'foldCB', a: ['backR', 'centerBack'], b: ['backL', 'centerBack'] },
    // armscye: the sleeve cap sews to (front armhole + back armhole)
    { kind: 'armscye', a: ['sleeveR', 'cap'], b: [['frontR', 'armhole'], ['backR', 'armhole']] },
    { kind: 'armscye', a: ['sleeveL', 'cap'], b: [['frontL', 'armhole'], ['backL', 'armhole']] },
    // sleeve seam: the two underarm edges sew to each other (closes the tube)
    { kind: 'sleeveSeam', a: ['sleeveR', 'underarmRight'], b: ['sleeveR', 'underarmLeft'] },
    { kind: 'sleeveSeam', a: ['sleeveL', 'underarmRight'], b: ['sleeveL', 'underarmLeft'] },
  ],
  // the collar/neckband: neckline edges are held to a neck-sized ring
  neckband: {
    circ: measurements.neck,
    edges: [['frontR', 'neckline'], ['frontL', 'neckline'],
            ['backR', 'neckline'], ['backL', 'neckline']],
  },
  // TODO next: cuff (wrist <-> cuff) + collar band panels.
}

mkdirSync('dist', { recursive: true })
writeFileSync('dist/garment.json', JSON.stringify(garment))
const ec = (t) => Object.entries(t.edges).map(([k, v]) => `${k}:${v.length}`).join(' ')
console.log('wrote dist/garment.json')
console.log('  front  edges ->', ec(garment.templates.front))
console.log('  back   edges ->', ec(garment.templates.back))
console.log('  sleeve edges ->', ec(garment.templates.sleeve))
console.log('  instances:', Object.keys(garment.instances).join(', '),
            '| stitches:', garment.stitches.length)
