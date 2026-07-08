/*
 * Square patch pocket, cloned in spirit from the army fatigue shirt.
 *
 * A patch pocket is its own cut piece (you topstitch it onto the front), so it
 * lives as a standalone parametric part. The top `pocketHem` band folds to the
 * inside; everything below the fold line is the visible pocket.
 *
 * pocketTaper > 0 brings the two bottom corners inward (some utility pockets
 * angle toward a point). Leave it at 0 for the classic square look.
 */
import { pluginAnnotations } from '@freesewing/plugin-annotations'

export const pocket = {
  name: 'workshirt.pocket',
  plugins: [pluginAnnotations],
  options: {
    pocketWidth: { mm: 130, min: 90, max: 180, menu: 'pocket' },
    pocketDepth: { mm: 150, min: 90, max: 200, menu: 'pocket' },
    pocketHem: { mm: 35, min: 15, max: 60, menu: 'pocket' },
    pocketTaper: { pct: 0, min: 0, max: 40, menu: 'pocket' },
  },
  draft: ({ Point, points, Path, paths, options, sa, macro, part }) => {
    const w = options.pocketWidth
    const d = options.pocketDepth
    const hem = options.pocketHem
    const inset = (w / 2) * options.pocketTaper

    points.hemLeft = new Point(0, -hem)
    points.hemRight = new Point(w, -hem)
    points.topLeft = new Point(0, 0)
    points.topRight = new Point(w, 0)
    points.botRight = new Point(w - inset, d)
    points.botLeft = new Point(inset, d)

    // Cut outline: full-width hem band on top, body below, tapered at the foot.
    paths.seam = new Path()
      .move(points.hemLeft)
      .line(points.hemRight)
      .line(points.botRight)
      .line(points.botLeft)
      .close()
      .addClass('fabric')

    // Fold line where the hem band turns to the inside.
    paths.fold = new Path()
      .move(points.topLeft)
      .line(points.topRight)
      .addClass('mark dashed')
      .addText('fold to inside', 'center fill-mark')

    points.grainTop = new Point(w / 2, -hem + 10)
    points.grainBot = new Point(w / 2, d - 10)
    macro('grainline', { from: points.grainBot, to: points.grainTop })

    macro('title', {
      at: new Point(w / 2, d / 2),
      nr: 7,
      title: 'Patch pocket',
      notes: 'Cut 2',
    })

    if (sa) paths.sa = paths.seam.offset(sa).addClass('fabric sa')

    return part
  },
}
