/*
 * Your body measurements, in MILLIMETRES (shoulderSlope is in DEGREES).
 *
 * These are PLACEHOLDER values for a slim men's ~size M. Replace them with your
 * own. Two good sources:
 *   1. Measure your body (FreeSewing has a how-to per measurement:
 *      https://freesewing.org/docs/measurements ).
 *   2. Measure the Banana Republic shirt that fits — that gives you the *ease*
 *      (shirt measurement minus body measurement) that makes it read "slim".
 *      Capture that ease, then tune the options in src/options.mjs to match.
 *
 * These 13 are the complete set required by the Simon block (+ Brian base) we
 * extend. Drafting will throw if any are missing.
 */
export const measurements = {
  biceps: 335,
  chest: 1000,
  hips: 980,
  hpsToBust: 250,          // high-point-shoulder straight down to bust line
  hpsToWaistBack: 470,     // nape-ish to natural waist, down the back
  neck: 410,
  shoulderSlope: 13,       // DEGREES
  shoulderToShoulder: 460,
  shoulderToWrist: 660,    // sleeve length, shoulder tip to wrist bone
  waist: 900,
  waistToArmpit: 230,
  waistToHips: 120,
  wrist: 175,
}
