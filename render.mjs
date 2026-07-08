/*
 * Draft the WorkShirt and write SVG to dist/.
 *
 *   - dist/workshirt-all.svg  : every panel laid out together (quick visual check)
 *   - dist/parts/<name>.svg   : one file per panel (feed these to Blender)
 *
 * Run with:  npm run render
 *
 * The per-part files are millimetre-accurate SVGs. In Blender: File > Import >
 * SVG brings each panel in as a curve (1 SVG unit = 1 mm at import scale 0.001
 * if you want metres); convert to mesh, then sew panels and run the cloth sim.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { WorkShirt, partNames } from './src/index.mjs'
import { measurements } from './src/measurements.mjs'
import { options } from './src/options.mjs'

// Seam allowance in mm. Override per-run: `SA=0 npm run render` for net
// seamlines (cleanest geometry for the Blender drape — you sew on the seamline).
// Keep the default 10 mm when exporting cut lines for the ShopBot.
const sa = process.env.SA !== undefined ? Number(process.env.SA) : 10

const baseSettings = {
  measurements,
  options,
  sa,
  complete: true, // include grainlines, titles, notches, etc.
  paperless: false,
}

const slug = (name) => name.replace(/[^a-z0-9]+/gi, '-').toLowerCase()

mkdirSync('dist/parts', { recursive: true })

// 1) Full layout
const all = new WorkShirt({ ...baseSettings }).draft().render()
writeFileSync('dist/workshirt-all.svg', all)
console.log('wrote dist/workshirt-all.svg')

// 2) One SVG per part
let ok = 0
for (const name of partNames) {
  try {
    const svg = new WorkShirt({ ...baseSettings, only: [name] }).draft().render()
    const file = `dist/parts/${slug(name)}.svg`
    writeFileSync(file, svg)
    console.log('wrote ' + file)
    ok++
  } catch (err) {
    console.error(`! failed to render ${name}: ${err.message}`)
  }
}
console.log(`\ndone: ${ok}/${partNames.length} parts`)
