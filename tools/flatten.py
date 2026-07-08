#!/usr/bin/env python
"""
flatten.py — unfold 3D garment panels into flat 2D sewing patterns.

The REVERSE of the drape: a 3D panel mesh (from a scan, a Newton drape, or a
sculpt) -> a flat 2D pattern piece. Fabric panels are near-developable (they
bend but barely stretch), so we flatten with an AS-RIGID-AS-POSSIBLE (isometric)
parameterization — length-preserving, not angle-preserving.

Each connected component of the input OBJ is treated as one panel. libigl's SLIM
segfaults and LSCM fails on these bindings, so the ARAP local/global solve is
implemented here directly (igl only for the robust helpers: boundary loop,
harmonic init, cotangent-free areas).

  .venv/bin/python tools/flatten.py <mesh.obj> [out.svg]
  # validate against ground truth on our own drape:
  .venv/bin/python tools/flatten.py dist/newton/shirt_front.obj dist/flat/front.svg
"""
import sys, os, math
import numpy as np
import igl
from scipy.sparse import coo_matrix, csc_matrix
from scipy.sparse.linalg import factorized

MM = 1000.0   # OBJ is in metres (Newton units) -> mm for the pattern


def split_components(V, F):
    """Yield (Vc, Fc) per connected component (each = one panel)."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import connected_components
    e = np.vstack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    g = csr_matrix((np.ones(len(e)), (e[:, 0], e[:, 1])), shape=(len(V), len(V)))
    _, lab = connected_components(g, directed=False)
    for c in np.unique(lab[F[:, 0]]):
        fmask = lab[F[:, 0]] == c
        Fc = F[fmask]
        used = np.unique(Fc)
        remap = -np.ones(len(V), int); remap[used] = np.arange(len(used))
        yield V[used], remap[Fc]


def arap_flatten(V, F, iters=40):
    """As-rigid-as-possible flatten (Liu et al. local/global). Returns Nx2 uv."""
    n, m = len(V), len(F)
    E = [(0, 1), (1, 2), (2, 0)]
    # per-triangle reference 2D (each 3D triangle laid out isometrically) + cot weights
    P = V[F]                                        # (m,3,3)
    e01 = P[:, 1] - P[:, 0]; e02 = P[:, 2] - P[:, 0]
    l01 = np.linalg.norm(e01, axis=1)
    u = e01 / l01[:, None]
    proj = np.einsum("ij,ij->i", e02, u)
    h = np.linalg.norm(e02 - proj[:, None] * u, axis=1)
    xref = np.zeros((m, 3, 2))
    xref[:, 1, 0] = l01; xref[:, 2, 0] = proj; xref[:, 2, 1] = h
    def cot(a, b):                                  # cot of angle between 3D vectors a,b (rowwise)
        cr = np.linalg.norm(np.cross(a, b), axis=1) + 1e-12
        return np.einsum("ij,ij->i", a, b) / cr
    w = np.zeros((m, 3))                            # weight per edge = 0.5*cot(opposite angle)
    w[:, 0] = 0.5 * cot(P[:, 0] - P[:, 2], P[:, 1] - P[:, 2])   # edge(0,1) opposite vtx2
    w[:, 1] = 0.5 * cot(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])   # edge(1,2) opposite vtx0
    w[:, 2] = 0.5 * cot(P[:, 0] - P[:, 1], P[:, 2] - P[:, 1])   # edge(2,0) opposite vtx1

    # cotangent Laplacian L (n x n), pin vertex 0
    I, J, D = [], [], []
    for e, (a, b) in enumerate(E):
        ia, ib = F[:, a], F[:, b]; we = w[:, e]
        I += [ia, ib, ia, ib]; J += [ib, ia, ia, ib]; D += [-we, -we, we, we]
    L = coo_matrix((np.concatenate(D), (np.concatenate(I), np.concatenate(J))),
                   shape=(n, n)).tolil()
    L[0, :] = 0; L[0, 0] = 1.0
    solve = factorized(L.tocsc())

    # harmonic init (boundary -> circle), robust
    bl = igl.boundary_loop(F.astype(np.int32))
    uv = igl.harmonic(V, F.astype(np.int32), bl, igl.map_vertices_to_circle(V, bl), 1)

    xe = np.stack([xref[:, a] - xref[:, b] for a, b in E], axis=1)   # (m,3,2) ref edge vecs
    for _ in range(iters):
        ue = np.stack([uv[F[:, a]] - uv[F[:, b]] for a, b in E], axis=1)   # (m,3,2)
        S = np.einsum("te,tei,tej->tij", w, ue, xe)                       # (m,2,2)
        U, _, Vt = np.linalg.svd(S)
        R = U @ Vt
        flip = np.linalg.det(R) < 0
        U[flip, :, -1] *= -1; R = U @ Vt                                  # reflection fix
        rhs = np.zeros((n, 2))
        for e, (a, b) in enumerate(E):
            val = w[:, e, None] * np.einsum("tij,tj->ti", R, xe[:, e])
            np.add.at(rhs, F[:, a], val); np.add.at(rhs, F[:, b], -val)
        rhs[0] = uv[0]
        uv = np.column_stack([solve(rhs[:, 0]), solve(rhs[:, 1])])
    return uv


def axis_align(uv):
    """Center + rotate so the panel's long axis is vertical (upright pattern)."""
    c = uv.mean(0); p = uv - c
    _, _, Vt = np.linalg.svd(p, full_matrices=False)
    p = p @ Vt.T                                    # principal axes -> x,y
    if np.ptp(p[:, 0]) > np.ptp(p[:, 1]):           # make the long axis vertical
        p = p[:, ::-1].copy()
    return p


def distortion(V, F, uv):
    P3 = V[F]; P2 = np.pad(uv, ((0, 0), (0, 1)))[F]
    def lens(P):
        return np.concatenate([np.linalg.norm(P[:, a] - P[:, b], axis=1) for a, b in [(0, 1), (1, 2), (2, 0)]])
    r = lens(P2) / np.maximum(lens(P3), 1e-12)
    return r


def boundary_polyline(F, uv):
    bl = igl.boundary_loop(F.astype(np.int32))
    return uv[bl]


def write_svg(path, panels):
    """panels: list of (name, boundary_mm Nx2, mesh_uv_mm, F)."""
    pad = 20.0; x0 = pad; parts = []; H = 0.0
    for name, bnd, uv, F in panels:
        w = np.ptp(uv[:, 0]); h = np.ptp(uv[:, 1]); H = max(H, h)
        off = np.array([x0 - uv[:, 0].min(), pad - uv[:, 1].min()])
        b = bnd + off
        pts = " ".join(f"{p[0]:.1f},{p[1]:.1f}" for p in b)
        # faint mesh
        segs = []
        for a, bb in [(0, 1), (1, 2), (2, 0)]:
            for t in F:
                p, q = uv[t[a]] + off, uv[t[bb]] + off
                segs.append(f"M{p[0]:.1f},{p[1]:.1f}L{q[0]:.1f},{q[1]:.1f}")
        parts.append(f'<g><path d="{"".join(segs)}" stroke="#ccc" stroke-width="0.3" fill="none"/>'
                     f'<polygon points="{pts}" fill="none" stroke="#c0392b" stroke-width="1.5"/>'
                     f'<text x="{x0:.0f}" y="{pad-6:.0f}" font-size="12" fill="#333">{name}</text></g>')
        x0 += w + pad
    W = x0
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}mm" height="{H+2*pad:.0f}mm" '
           f'viewBox="0 0 {W:.0f} {H+2*pad:.0f}">{"".join(parts)}</svg>')
    open(path, "w").write(svg)


def main():
    obj = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(obj)[0] + "_flat.svg"
    V, F = igl.read_triangle_mesh(obj)
    V, F, _, _ = igl.remove_unreferenced(V.astype(np.float64), F.astype(np.int32))
    F = F[igl.doublearea(V, F) > 1e-10]             # drop degenerate faces
    V, F, _, _ = igl.remove_unreferenced(V, F.astype(np.int32))
    panels = []
    for idx, (Vc, Fc) in enumerate(split_components(V, F)):
        uv = arap_flatten(Vc, Fc)
        a3 = igl.doublearea(Vc, Fc.astype(np.int32)).sum()
        a2 = igl.doublearea(np.pad(uv, ((0, 0), (0, 1))), Fc.astype(np.int32)).sum()
        uv *= math.sqrt(a3 / max(a2, 1e-12))        # scale to preserve area
        uv = axis_align(uv)                         # PCA-align so the piece is upright
        r = distortion(Vc, Fc, uv)
        uv_mm = uv * MM
        bnd_mm = boundary_polyline(Fc, uv) * MM
        panels.append((f"panel{idx}", bnd_mm, uv_mm, Fc))
        warn = "  <-- HIGH DISTORTION: not developable (a tube/dart?) — cut along a seam first" \
               if (np.percentile(r, 95) > 1.25 or np.percentile(r, 5) < 0.8) else ""
        print(f"  panel{idx}: {len(Vc)}v {len(Fc)}f  bbox {np.ptp(uv_mm[:,0]):.0f}x{np.ptp(uv_mm[:,1]):.0f}mm  "
              f"stretch mean {r.mean():.3f} p5 {np.percentile(r,5):.3f} p95 {np.percentile(r,95):.3f}{warn}")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    write_svg(out, panels)
    print(f"[flatten] {len(panels)} panel(s) -> {out}")


if __name__ == "__main__":
    main()
