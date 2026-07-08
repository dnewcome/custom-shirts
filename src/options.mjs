/*
 * Design-option overrides passed to the draft. Anything you don't set here
 * falls back to Simon's defaults. This is your main "knobs" file once the
 * pattern drafts cleanly.
 *
 * Value conventions when overriding Simon's own options:
 *   - list options  -> the string value, e.g. cuffStyle: 'straightBarrelCuff'
 *   - bool options  -> true / false
 *   - pct options   -> a FRACTION, e.g. 0.08 means 8%
 *   - mm  options   -> millimetres, e.g. 130
 *   - deg options   -> degrees
 *
 * Full list of Simon's options + meanings:
 *   https://freesewing.org/docs/designs/simon
 *
 * Our custom pocket/flap options (pocketWidth, pocketDepth, pocketHem,
 * pocketTaper, flapWidth, flapDepth, flapPoint) are defined in src/parts/.
 */
export const options = {
  // --- Army-fatigue detailing ---------------------------------------------
  // Barrel cuff (vs. french). 'straight' reads most workwear/utility.
  cuffStyle: 'straightBarrelCuff',

  // --- Square patch pocket (our custom part) ------------------------------
  // 0 taper = perfectly square bottom, the classic fatigue-shirt look.
  pocketTaper: 0,

  // --- Fit (start at Simon defaults; tune toward the BR slim fit) ---------
  // Uncomment and adjust once you've drafted once and measured against the BR
  // shirt. Smaller chestEase = slimmer. (pct options are fractions.)
  // chestEase: 0.06,
  // waistEase: 0.04,
  // hipsEase: 0.06,
}
