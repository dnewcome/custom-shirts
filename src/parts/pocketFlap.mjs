/*
 * Button-down flap for the square patch pocket. Slightly wider than the pocket
 * so it overhangs, with an optional center point at the bottom (flapPoint).
 * Set flapPoint to 0 for a straight-bottomed flap.
 */
import { pluginAnnotations } from '@freesewing/plugin-annotations'

export const pocketFlap = {
  name: 'workshirt.pocketFlap',
  plugins: [pluginAnnotations],
  options: {
    flapWidth: { mm: 134, min: 90, max: 184, menu: 'pocket' },
    flapDepth: { mm: 60, min: 30, max: 90, menu: 'pocket' },
    flapPoint: { mm: 12, min: 0, max: 30, menu: 'pocket' },
  },
  draft: ({ Point, points, Path, paths, options, sa, macro, part }) => {
    const w = options.flapWidth
    const d = options.flapDepth
    const pt = options.flapPoint

    points.topLeft = new Point(0, 0)
    points.topRight = new Point(w, 0)
    points.botRight = new Point(w, d)
    points.botMid = new Point(w / 2, d + pt)
    points.botLeft = new Point(0, d)

    paths.seam = new Path()
      .move(points.topLeft)
      .line(points.topRight)
      .line(points.botRight)
      .line(points.botMid)
      .line(points.botLeft)
      .close()
      .addClass('fabric')

    points.grainTop = new Point(w / 2, 6)
    points.grainBot = new Point(w / 2, d - 6)
    macro('grainline', { from: points.grainBot, to: points.grainTop })

    macro('title', {
      at: new Point(w / 2, d / 2),
      nr: 8,
      title: 'Pocket flap',
      notes: 'Cut 2 + 2 (self + facing)',
    })

    if (sa) paths.sa = paths.seam.offset(sa).addClass('fabric sa')

    return part
  },
}
