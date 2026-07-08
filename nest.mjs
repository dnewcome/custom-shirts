/*
 * Nest the shirt panels onto a cutting bed for the ShopBot.
 *
 *   npm run nest                 # default 1400 mm usable width, 10 mm SA
 *   BED_W=2438 SA=10 npm run nest
 *
 * Writes dist/cut-layout.svg — a single millimetre-accurate SVG sized to the
 * bed, with every panel placed UPRIGHT (grainline vertical — fabric grain must
 * be respected, so panels are never rotated), duplicated per the CUT map below,
 * and a bed outline.
 *
 * HONEST LIMITS (read before cutting):
 *   - Packing is simple shelf/row packing, not true nesting. It won't be the
 *     tightest fabric usage; it's a valid, non-overlapping starting layout.
 *   - "Cut on fold" pieces (the back) are placed as the shape FreeSewing
 *     drafts. If you cut flat instead of on a fold, you must mirror/duplicate
 *     that piece yourself — it is NOT auto-unfolded here.
 *   - The CUT counts below are typical for a button-up; verify against how you
 *     actually intend to construct yours and edit as needed.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { WorkShirt, partNames } from './src/index.mjs'
import { measurements } from './src/measurements.mjs'
import { options } from './src/options.mjs'

const BED_W = Number(process.env.BED_W ?? 1400) // usable fabric/bed width, mm
const MARGIN = 20
const GAP = 12
const sa = process.env.SA !== undefined ? Number(process.env.SA) : 10

// How many of each panel to cut. Keyed by the slugged part name (lowercase).
// Anything not listed defaults to 1.
const CUT = {
  'simon-back': 1, // on fold
  'simon-frontright': 1,
  'simon-frontleft': 1,
  'simon-yoke': 2, // outer + inner facing
  'simon-sleeve': 2,
  'simon-cuff': 2,
  'simon-collar': 1, // on fold
  'simon-collarstand': 1, // on fold
  'simon-buttonplacket': 1,
  'simon-buttonholeplacket': 1,
  'simon-sleeveplacketoverlap': 2,
  'simon-sleeveplacketunderlap': 2,
  'workshirt-pocket': 2,
  'workshirt-pocketflap': 4, // self + facing, ×2 pockets
}

const css = `
  <style type="text/css"><![CDATA[
    path { fill: none; stroke: #1d1d1b; stroke-width: 1.2; }
    .fabric { stroke: #1d1d1b; stroke-width: 1.6; }
    .sa { stroke: #c0392b; stroke-width: 0.8; stroke-dasharray: 6 3; }
    .mark, .dashed { stroke: #2980b9; stroke-width: 0.8; stroke-dasharray: 5 3; }
    text { fill: #333; font-family: sans-serif; font-size: 13px; }
    circle { fill: #1d1d1b; }
    .bed { fill: none; stroke: #16a085; stroke-width: 3; stroke-dasharray: 12 6; }
  ]]></style>`

const slug = (name) => name.replace(/[^a-z0-9]+/gi, '-').toLowerCase()

// Render each part once, capture its inner SVG + bounding box (from viewBox).
const items = []
for (const name of partNames) {
  const svg = new WorkShirt({ measurements, options, sa, complete: true, only: [name] })
    .draft()
    .render()
  const vb = svg.match(/viewBox="([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)"/)
  const inner = svg.match(/<svg\b[^>]*>([\s\S]*)<\/svg>/)
  if (!vb || !inner) {
    console.error(`! could not parse ${name}, skipping`)
    continue
  }
  const [minX, minY, w, h] = [+vb[1], +vb[2], +vb[3], +vb[4]]
  const count = CUT[slug(name)] ?? 1
  for (let i = 0; i < count; i++) {
    items.push({ name, minX, minY, w, h, inner: inner[1] })
  }
}

// Shelf-pack, tallest first, upright only.
items.sort((a, b) => b.h - a.h)
let x = MARGIN
let y = MARGIN
let rowH = 0
const placed = []
for (const it of items) {
  if (x + it.w > BED_W - MARGIN && x > MARGIN) {
    x = MARGIN
    y += rowH + GAP
    rowH = 0
  }
  placed.push({ ...it, x, y })
  x += it.w + GAP
  rowH = Math.max(rowH, it.h)
}
const totalH = Math.round(y + rowH + MARGIN)

// Compose the bed SVG.
let out = `<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"
  width="${BED_W}mm" height="${totalH}mm" viewBox="0 0 ${BED_W} ${totalH}">
${css}
  <rect class="bed" x="${MARGIN / 2}" y="${MARGIN / 2}" width="${BED_W - MARGIN}" height="${totalH - MARGIN}" />
`
for (const p of placed) {
  const tx = p.x - p.minX
  const ty = p.y - p.minY
  out += `  <g transform="translate(${tx.toFixed(2)} ${ty.toFixed(2)})">${p.inner}</g>\n`
}
out += `</svg>\n`

mkdirSync('dist', { recursive: true })
writeFileSync('dist/cut-layout.svg', out)
console.log(
  `wrote dist/cut-layout.svg — ${placed.length} pieces, bed ${BED_W}×${totalH} mm, sa ${sa} mm`
)
