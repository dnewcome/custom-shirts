/*
 * Export panel outlines + landmarks to dist/panels.json for the Blender drape.
 * Panels are drafted as HALF pieces (center fold at x=0); Blender mirrors them
 * to full width. Coordinates are millimetres, FreeSewing axes (x right, y down).
 */
import { writeFileSync, mkdirSync } from 'node:fs'
import { WorkShirt } from './src/index.mjs'
import { measurements } from './src/measurements.mjs'
import { options } from './src/options.mjs'

const p = new WorkShirt({ measurements, options, sa: 0, complete: false })
p.draft()
const set0 = p.parts[0]

const round = (v) => Math.round(v * 100) / 100

function sampleSeam(partName, N = 160) {
  const part = set0[partName]
  const seam = part.paths.seam
  const L = seam.length()
  const pts = []
  for (let i = 0; i < N; i++) {
    const d = Math.min(L * (i / N) + 0.01, L - 0.01)
    const pt = seam.shiftAlong(d)
    if (pt) pts.push([round(pt.x), round(pt.y)])
  }
  // landmark points we use to segment sewable edges
  const L_ = {}
  for (const k of ['cbNeck', 'cfNeck', 'neck', 'hps', 'shoulder', 'armhole', 'waist', 'hips', 'hem', 'cbHem']) {
    if (part.points[k]) L_[k] = [round(part.points[k].x), round(part.points[k].y)]
  }
  return { outline: pts, landmarks: L_ }
}

const data = {
  units: 'mm',
  measurements,
  // Use the Brian base blocks (full front/back to the shoulder, no separate
  // yoke) as the drape proxy — matching shoulders make the sewing clean. The
  // cut pattern still uses Simon's yoked pieces; this is just for the 3D drape.
  panels: {
    front: sampleSeam('brian.front'),
    back: sampleSeam('brian.back'),
    sleeve: sampleSeam('simon.sleeve', 200),
  },
}

mkdirSync('dist', { recursive: true })
writeFileSync('dist/panels.json', JSON.stringify(data))
console.log('wrote dist/panels.json (front/back outlines + landmarks)')
