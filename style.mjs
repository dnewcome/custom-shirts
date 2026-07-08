/*
 * Visualization helper: FreeSewing's raw render() emits geometry that relies on
 * a CSS stylesheet to look right (unfilled panels, thin strokes, small text).
 * This injects a minimal stylesheet into an SVG so it renders like a pattern.
 *
 *   node style.mjs <in.svg> <out.svg>
 */
import { readFileSync, writeFileSync } from 'node:fs'

const [, , inFile, outFile] = process.argv

const css = `
  <style type="text/css"><![CDATA[
    path { fill: none; stroke: #1d1d1b; stroke-width: 1.2; }
    .fabric { stroke: #1d1d1b; stroke-width: 1.6; }
    .sa { stroke: #c0392b; stroke-width: 0.8; stroke-dasharray: 6 3; }
    .mark, .dashed { stroke: #2980b9; stroke-width: 0.8; stroke-dasharray: 5 3; }
    .grainline { stroke: #555; stroke-width: 1; }
    text { fill: #333; font-family: sans-serif; font-size: 14px; }
    text.text-xs, .text-sm { font-size: 11px; }
    circle { fill: #1d1d1b; }
  ]]></style>`

let svg = readFileSync(inFile, 'utf8')
// Insert the stylesheet right after the opening <svg ...> tag.
svg = svg.replace(/(<svg\b[^>]*>)/, `$1${css}`)
writeFileSync(outFile, svg)
console.log(`styled -> ${outFile}`)
