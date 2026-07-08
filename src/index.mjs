/*
 * WorkShirt — the design.
 *
 * We extend FreeSewing's Simon (a button-up dress shirt) by reusing all of its
 * parts and adding our own square patch pocket + flap. Simon already ships the
 * pieces we want (yoke, barrel cuffs, collar + stand, button plackets), so the
 * body/fit work happens through measurements (src/measurements.mjs) and options
 * (src/options.mjs); the army-fatigue detailing comes from our pocket parts.
 *
 * Why reuse Simon instead of drafting from scratch: the collar/neckline and
 * cuff/sleeve geometry (the dimensionally fussy grafts) stay internally
 * consistent because they all come from one block.
 */
import { Design } from '@freesewing/core'
import {
  back,
  buttonholePlacket,
  buttonPlacket,
  collar,
  collarStand,
  cuff,
  front,
  frontRight,
  frontLeft,
  sleeve,
  sleevePlacketOverlap,
  sleevePlacketUnderlap,
  yoke,
} from '@freesewing/simon'
import { pocket } from './parts/pocket.mjs'
import { pocketFlap } from './parts/pocketFlap.mjs'

const parts = [
  back,
  buttonholePlacket,
  buttonPlacket,
  collar,
  collarStand,
  cuff,
  front,
  frontRight,
  frontLeft,
  sleeve,
  sleevePlacketOverlap,
  sleevePlacketUnderlap,
  yoke,
  pocket,
  pocketFlap,
]

export const WorkShirt = new Design({
  data: { name: 'workshirt', version: '0.1.0' },
  parts,
})

// Resolved part names, for per-part SVG export in render.mjs.
export const partNames = parts.map((p) => (typeof p === 'function' ? p().name : p.name))
