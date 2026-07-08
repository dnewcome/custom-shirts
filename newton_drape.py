#!/usr/bin/env python
"""
Newton (Style3D) drape DERIVED from the canonical garment spec.

Source of truth: dist/garment.json  (body + panel templates with NAMED EDGES +
instances + an explicit STITCH GRAPH + a neckband constraint). This script is a
pure deriver: it triangulates the templates, lays the instances out on a body,
stitches EXACTLY the graph edges, holds the neckline to a neck-sized ring (the
collar stand-in), and relaxes it. Nothing here defines the garment — edit
export-garment.mjs / the FreeSewing params and regenerate.

  .venv/bin/python newton_drape.py --viewer gl                 # interactive
  .venv/bin/python newton_drape.py --viewer null --num-frames 150   # headless + OBJ
"""
import json, math, os
import numpy as np
import triangle as tr
import warp as wp
import newton
import newton.examples
from newton import Mesh, ParticleFlags
from newton.solvers import style3d

MM = 1.0e-3
HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist", "newton")
os.makedirs(DIST, exist_ok=True)
G = json.load(open(os.path.join(HERE, "dist", "garment.json")))
M = G["measurements"]
FAB = G["fabric"]

# ---------------------------------------------------------------- meshing
def triangulate(outline, maxarea):
    pts = np.asarray(outline, dtype=float)
    n = len(pts)
    segs = np.array([[i, (i + 1) % n] for i in range(n)], dtype=int)
    t = tr.triangulate({"vertices": pts, "segments": segs}, f"pq30a{maxarea}")
    v = np.asarray(t["vertices"], dtype=float)
    f = np.asarray(t["triangles"], dtype=int)
    assert len(v) >= n and np.allclose(v[:n], pts), "triangle reordered boundary verts"
    a, b2, c = v[f[:, 0]], v[f[:, 1]], v[f[:, 2]]
    area2 = (b2[:, 0]-a[:, 0])*(c[:, 1]-a[:, 1]) - (b2[:, 1]-a[:, 1])*(c[:, 0]-a[:, 0])
    flip = area2 < 0
    f[flip] = f[flip][:, ::-1]
    return v, f, n

# ---------------------------------------------------------------- body / torso
def _ab(circ, wide, deep):
    r = circ / (2 * math.pi); return r * wide * MM, r * deep * MM

_sh = M["shoulderToShoulder"] / 2.0 * MM
# collider is capped BELOW the neck ring so the pinned neckline never fights it
STATIONS = [
    (+0.020, _sh * 0.82, _sh * 0.42),     # shoulder ledge = top of collider
    (-0.250, *_ab(M["chest"], 1.16, 0.82)),
    (-0.470, *_ab(M["waist"], 1.14, 0.82)),
    (-0.590, *_ab(M["hips"], 1.14, 0.84)),
    (-0.870, *_ab(M["hips"], 1.12, 0.84)),
]

def torso_ab(z):
    if z >= STATIONS[0][0]:  return STATIONS[0][1], STATIONS[0][2]
    if z <= STATIONS[-1][0]: return STATIONS[-1][1], STATIONS[-1][2]
    for k in range(len(STATIONS) - 1):
        z0, a0, b0 = STATIONS[k]; z1, a1, b1 = STATIONS[k + 1]
        if z1 <= z <= z0:
            t = (z0 - z) / (z0 - z1)
            return a0 + (a1 - a0) * t, b0 + (b1 - b0) * t
    return STATIONS[-1][1], STATIONS[-1][2]

def push_out(P, margin=1.07):
    out = P.copy()
    for i in range(len(out)):
        x, y, z = out[i]
        a, b = torso_ab(float(z))
        r = math.sqrt((x / a) ** 2 + (y / b) ** 2)
        if r < margin:
            s = margin / max(r, 1e-6)
            out[i, 0] = x * s; out[i, 1] = y * s
    return out

def torso_mesh():
    Nt = 56
    th = np.linspace(0, 2 * math.pi, Nt, endpoint=False)
    rings = [np.column_stack([a*np.cos(th), b*np.sin(th), np.full(Nt, z)]) for (z, a, b) in STATIONS]
    V = np.vstack(rings).astype(np.float32); F = []
    for k in range(len(rings) - 1):
        b0, b1 = k*Nt, (k+1)*Nt
        for j in range(Nt):
            j2 = (j+1) % Nt
            F += [[b0+j, b0+j2, b1+j], [b0+j2, b1+j2, b1+j]]
    top_c = len(V); V = np.vstack([V, [[0, 0, STATIONS[0][0]+0.03]]]).astype(np.float32)
    for j in range(Nt): F.append([j, top_c, (j+1) % Nt])
    bb = (len(rings)-1)*Nt
    bot_c = len(V); V = np.vstack([V, [[0, 0, STATIONS[-1][0]-0.02]]]).astype(np.float32)
    for j in range(Nt): F.append([bb+(j+1) % Nt, bot_c, bb+j])
    F = np.asarray(F, dtype=int)
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    nrm = np.cross(b-a, c-a); cen = (a+b+c)/3.0; rad = cen.copy(); rad[:, 2] = 0.0
    flip = (nrm*rad).sum(1) < 0
    F[flip] = F[flip][:, ::-1]
    return V, F

# ---------------------------------------------------------------- 3D placement
A_P, B_P = _ab(M["chest"] + 90.0, 1.20, 0.80)      # garment wrap ellipse (chest + ease)
NECK_R = G["neckband"]["circ"] / (2 * math.pi) * MM * 1.30   # neck opening radius
NECK_Z = 0.085                                      # neck ring height (above collider)
NECK_BLEND = 180.0                                  # mm; funnel height below the ring

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)

def wrap(v2d, xmax, sx, fy):
    """Flat panel (mm) -> 3D (m). Shoulder fold joins front/back at the top;
    a neck-ring funnel shrinks the top-center opening to neck size + lifts it."""
    x = np.abs(v2d[:, 0]); y = v2d[:, 1]
    s = np.clip(x / xmax, 0.0, 1.0)
    alpha = s * (math.pi / 2)
    Xb = A_P * np.sin(alpha); Yb = B_P * np.cos(alpha)
    fold = smoothstep(83.6 * 0.55, 83.6, x) * (1.0 - smoothstep(0.0, 250.0, y))
    # neck-ring funnel: strong near the top-center, fades out by NECK_BLEND / s~0.42
    npull = smoothstep(0.42, 0.20, s) * (1.0 - smoothstep(0.0, NECK_BLEND, y))
    ratio = 1.0 - npull * (1.0 - NECK_R / A_P)
    Xb = Xb * ratio
    Y = Yb * (1.0 - fold) * ratio
    z = -y * MM + fold * 0.030 + npull * (NECK_Z + y * MM)   # lift the funnel to NECK_Z
    return np.column_stack([sx * Xb, fy * Y, z]).astype(np.float32)

def _norm(v):
    n = np.linalg.norm(v); return v / n if n > 1e-9 else v

SLEEVE_HW = 210.0   # sleeve bicep half-width, mm (|x| at y=0)
SLEEVE_WW = 135.0   # sleeve wrist half-width, mm

ARM_LEN = M["shoulderToWrist"] * MM   # 3D sleeve loft length = arm length, so it reaches the wrist
ARM_DROP = float(os.environ.get("ARM_DROP") or 0.9)   # arm-axis downward tilt (bigger = more A-pose)

def arm_mesh(A0, D):
    """Tapered arm collider from the shoulder down the arm axis: upper-arm radius
    (from biceps) -> wrist radius, length shoulderToWrist. Outward normals."""
    D = _norm(np.asarray(D, dtype=float))
    U = _norm(np.cross(D, np.array([0.0, 0.0, 1.0]))); W = _norm(np.cross(D, U))
    L = M["shoulderToWrist"] * MM
    r0 = M["biceps"] / (2 * math.pi) * MM * 0.85   # keep the arm inside the sleeve (avoid poke-through)
    r1 = M["wrist"] / (2 * math.pi) * MM * 0.95
    start = A0 + D * 0.02                           # start just outside the armhole, not inside the shoulder
    Nr, Nt = 12, 24
    th = np.linspace(0, 2 * math.pi, Nt, endpoint=False)
    ring = np.cos(th)[:, None] * U[None, :] + np.sin(th)[:, None] * W[None, :]
    rings = []
    for k in range(Nr):
        t = k / (Nr - 1)
        rings.append(start[None, :] + D * (t * L) + (r0 + (r1 - r0) * t) * ring)
    V = np.vstack(rings); F = []
    for k in range(Nr - 1):
        b0, b1 = k * Nt, (k + 1) * Nt
        for j in range(Nt):
            j2 = (j + 1) % Nt
            F += [[b0 + j, b0 + j2, b1 + j], [b0 + j2, b1 + j2, b1 + j]]
    wc = len(V); V = np.vstack([V, (start + D * L)[None, :]])   # cap the wrist
    bb = (Nr - 1) * Nt
    for j in range(Nt): F.append([bb + j, bb + (j + 1) % Nt, wc])
    F = np.asarray(F, dtype=int)
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    nrm = np.cross(b - a, c - a); cen = (a + b + c) / 3.0
    rad = (cen - start) - np.outer((cen - start) @ D, D)        # radial (perp to axis)
    flip = (nrm * rad).sum(1) < 0
    F[flip] = F[flip][:, ::-1]
    return V.astype(np.float32), F

def _halfwidth_fn(v2d, nbnd):
    """Half-width |x| of the sleeve as a function of row y (from the boundary)."""
    bx = np.abs(v2d[:nbnd, 0]); by = v2d[:nbnd, 1]
    def hw(y):
        m = np.abs(by - y) < 22.0
        return max(bx[m].max(), 15.0) if m.any() else 15.0
    return hw

def place_sleeve(T, side, inst, tmpl):
    """Loft the flat sleeve onto the body as a generalized cylinder: every vert
    blends from the armhole ring (front.armhole+back.armhole) at the cap end to a
    wrist circle at the bottom, indexed by along-arm y and around-arm angle. The
    cap lands on the armhole ring; the two underarm edges land coincident (seam
    closes). Nothing is compressed to a point -> no strain explosion."""
    v2d, edges, nbnd = T["v2d"], T["edges"], T["nbnd"]
    fpos = inst[f"front{side}"]["pos3d"][tmpl["front"]["edges"]["armhole"]]   # underarm->shoulder
    bpos = inst[f"back{side}"]["pos3d"][tmpl["back"]["edges"]["armhole"]]     # underarm->shoulder
    ring = np.vstack([fpos, bpos[::-1]]).astype(float)                        # underarm..shoulder..underarm
    seg = np.linalg.norm(np.diff(ring, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)]); cum /= (cum[-1] or 1.0)
    def ring_at(t):
        t = min(max(t, 0.0), 1.0)
        i = max(1, min(int(np.searchsorted(cum, t)), len(ring) - 1))
        f = (t - cum[i - 1]) / max(cum[i] - cum[i - 1], 1e-9)
        return ring[i - 1] * (1 - f) + ring[i] * f
    A0 = ring.mean(0)
    _, _, Vt = np.linalg.svd(ring - A0, full_matrices=False)
    nrm = Vt[2]
    if np.dot(nrm, np.array([A0[0], A0[1], 0.0])) < 0: nrm = -nrm   # point outward
    D = _norm(nrm + np.array([0, 0, -ARM_DROP]))                   # arm axis: out + down
    U = _norm(np.cross(D, np.array([0.0, 0.0, 1.0])))
    W = _norm(np.cross(D, U))
    hw = _halfwidth_fn(v2d, nbnd)
    xs, ys = v2d[:, 0], v2d[:, 1]
    ytop, ywrist = ys.min(), ys.max(); span = max(ywrist - ytop, 1.0)
    Rw = SLEEVE_WW / math.pi * MM
    flip = (side == "L")
    pos = np.zeros((len(v2d), 3), dtype=np.float32)
    for i in range(len(v2d)):
        phi = math.pi * xs[i] / max(hw(ys[i]), 1e-3)
        phi = max(-math.pi, min(math.pi, phi))
        if flip: phi = -phi
        lnorm = (ys[i] - ytop) / span                       # 0 at cap top, 1 at wrist
        ring_p = ring_at((phi + math.pi) / (2 * math.pi))   # around-arm -> armhole ring
        wrist_p = A0 + D * ARM_LEN + Rw * (math.cos(phi) * U + math.sin(phi) * W)
        pos[i] = (1.0 - lnorm) * ring_p + lnorm * wrist_p
    # place the cap EDGE exactly on the armhole ring (by arc-length) so it is
    # coincident with the shirt armhole -> clean sew + a solid anchor to pin
    cap_order = edges["cap"]
    cp = v2d[cap_order]
    cc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(cp, axis=0), axis=1))])
    cc /= (cc[-1] or 1.0)
    for m, vi in enumerate(cap_order):
        pos[vi] = ring_at(1.0 - cc[m] if flip else cc[m])
    return pos, A0, D

def quat_z_to(d):
    """Quaternion rotating local +Z onto direction d."""
    d = _norm(np.asarray(d, dtype=float)); z = np.array([0, 0, 1.0])
    c = float(np.dot(z, d))
    if c > 0.9999: return wp.quat_identity()
    if c < -0.9999: return wp.quat_from_axis_angle(wp.vec3(1.0, 0.0, 0.0), math.pi)
    ax = _norm(np.cross(z, d))
    return wp.quat_from_axis_angle(wp.vec3(*ax), math.acos(max(-1.0, min(1.0, c))))

@wp.kernel
def _damp_velocity(qd: wp.array(dtype=wp.vec3), k: float):
    # bleed kinetic energy each substep (Style3D has no global damping / air drag,
    # so without this the cloth oscillates forever instead of settling)
    i = wp.tid()
    qd[i] = qd[i] * k

# ================================================================ Example
class Example:
    def __init__(self, viewer, args):
        self.viewer = viewer
        maxarea = getattr(args, "maxarea", 110.0)
        self.sim_substeps = 10
        self.frame_dt = 1.0 / 60.0
        self.sim_dt = self.frame_dt / self.sim_substeps
        self.sim_time = 0.0
        self.damp = float(os.environ.get("DAMP") or 0.92)   # per-substep velocity damping

        builder = newton.ModelBuilder(up_axis=newton.Axis.Z)
        newton.solvers.SolverStyle3D.register_custom_attributes(builder)

        # templates: triangulate once
        tmpl = {}
        for name, t in G["templates"].items():
            v2d, tris, nbnd = triangulate(t["outline"], maxarea)
            xmax = float(np.asarray(t["outline"])[:, 0].max())
            tmpl[name] = dict(v2d=v2d, tris=tris, nbnd=nbnd, xmax=xmax, edges=t["edges"])

        # ---- place every instance into ONE un-merged vertex pool ----
        TYPES = ["front", "back", "sleeve"]     # per-piece colour groups for the render
        inst = {}; V3 = []; PV = []; TRI = []; TRITYPE = []; arms = []; voff = 0
        def register(name, spec, pos3d):
            nonlocal voff
            T = tmpl[spec["template"]]
            inst[name] = dict(off=voff, n=len(pos3d), tmpl=spec["template"], pos3d=pos3d)
            V3.append(pos3d.astype(float)); PV.append(T["v2d"].astype(float) * MM)
            TRI.append(T["tris"] + voff)
            TRITYPE.append(np.full(len(T["tris"]), TYPES.index(spec["template"])))
            voff += len(pos3d)
        for name, spec in G["instances"].items():           # body first
            if spec["template"] == "sleeve": continue
            T = tmpl[spec["template"]]
            register(name, spec, push_out(wrap(T["v2d"], T["xmax"], spec["sx"], spec["fy"])))
        for name, spec in G["instances"].items():            # sleeves need the armhole ring
            if spec["template"] != "sleeve": continue
            pos3d, A0, D = place_sleeve(tmpl["sleeve"], spec["side"], inst, tmpl)
            register(name, spec, pos3d); arms.append((A0, D))
        V3 = np.vstack(V3); PV = np.vstack(PV); TRI = np.vstack(TRI)
        TRITYPE = np.concatenate(TRITYPE)
        self.tmpl, self.inst, self.TYPES = tmpl, inst, TYPES

        def edge_globals(instance, edge):
            i = inst[instance]; return [i["off"] + k for k in tmpl[i["tmpl"]]["edges"][edge]]
        def edge_pos(instance, edge):
            i = inst[instance]; return i["pos3d"][tmpl[i["tmpl"]]["edges"][edge]]

        # ---- STITCH GRAPH: WELD paired seam verts into shared particles ----
        # SolverStyle3D does NOT integrate springs; a seam is shared topology
        # (one particle used by both panels), with the flat pattern kept as
        # separate UV islands (panel_verts). `b` may be a single edge or a list.
        parent = list(range(voff))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb: parent[ra] = rb
        THRESH = {"armscye": 0.030}
        for st in G["stitches"]:
            ga = edge_globals(*st["a"]); pa = edge_pos(*st["a"])
            b = st["b"]; targets = b if isinstance(b[0], list) else [b]
            gb, pbl = [], []
            for be in targets:
                gb += edge_globals(*be); pbl.append(edge_pos(*be))
            pb = np.vstack(pbl); thr = THRESH.get(st.get("kind"), 0.015); hit = 0
            for m, a in enumerate(ga):
                d = np.linalg.norm(pb - pa[m], axis=1); j = int(np.argmin(d))
                if d[j] < thr: union(a, gb[j]); hit += 1
            print(f"    {st.get('kind','?'):9s} {st['a'][0]}.{st['a'][1]:12s} -> {hit}/{len(ga)} welds")

        # collapse each union to one particle at the group's mean position
        roots = np.array([find(i) for i in range(voff)])
        uniq = np.unique(roots)
        newidx = {int(r): k for k, r in enumerate(uniq)}
        vmap = np.array([newidx[int(r)] for r in roots])       # old panel vert -> merged idx
        Vm = np.zeros((len(uniq), 3)); cnt = np.zeros(len(uniq))
        np.add.at(Vm, vmap, V3); np.add.at(cnt, vmap, 1.0)
        Vm /= cnt[:, None]
        indices3d = vmap[TRI.reshape(-1)].reshape(-1, 3)       # welded 3D topology
        # welding can collapse a triangle (two of its verts merged) -> drop those
        # from BOTH the 3D and the UV index arrays so they stay parallel
        keep = ((indices3d[:, 0] != indices3d[:, 1]) &
                (indices3d[:, 1] != indices3d[:, 2]) &
                (indices3d[:, 0] != indices3d[:, 2]))
        dropped = int((~keep).sum())
        indices3d = indices3d[keep]; TRI = TRI[keep]; TRITYPE = TRITYPE[keep]
        self.vmap = vmap; self.tri_type = TRITYPE
        print(f"[weld] {voff} panel verts -> {len(uniq)} particles "
              f"({voff - len(uniq)} welded, {dropped} collapsed tris dropped)")

        # ONE Style3D cloth: welded 3D mesh + flat pattern as separate UV islands
        style3d.add_cloth_mesh(
            builder, pos=wp.vec3(0, 0, 0), rot=wp.quat_identity(), vel=wp.vec3(0, 0, 0),
            vertices=[wp.vec3(*p) for p in Vm],
            indices=indices3d.reshape(-1).tolist(),
            panel_verts=[wp.vec2(*p) for p in PV],
            panel_indices=TRI.reshape(-1).tolist(),
            density=FAB["density"], scale=1.0, particle_radius=5.0e-3,
            tri_aniso_ke=wp.vec3(*FAB["tri_aniso_ke"]),
            edge_aniso_ke=wp.vec3(*FAB["edge_aniso_ke"]), label="shirt")

        # body collider: parametric torso + a tapered arm mesh per sleeve (sized
        # from measurements). Kept as separate shapes; combined for the render.
        ident = wp.transform(p=wp.vec3(0, 0, 0), q=wp.quat_identity())
        tv, tf = torso_mesh()
        builder.add_shape_mesh(body=builder.add_body(), xform=ident,
                               mesh=Mesh(tv.tolist(), tf.reshape(-1).tolist()))
        for A0, D in arms:
            av, af = arm_mesh(A0, D)
            builder.add_shape_mesh(body=builder.add_body(), xform=ident,
                                   mesh=Mesh(av.tolist(), af.reshape(-1).tolist()))
        self.model = builder.finalize()
        self.gfaces = indices3d
        # render only the torso; arms stay collider-only so they don't hide the
        # (loose) amber sleeves that drape over them
        self.body = (tv, tf)

        # NECKBAND: pin the neckline edges (on the neck ring, above the collider)
        flags = self.model.particle_flags.numpy(); pinned = set()
        for instance, edge in G["neckband"]["edges"]:
            for gi in edge_globals(instance, edge):
                pinned.add(int(vmap[gi]))
        for k in pinned:
            flags[k] = flags[k] & ~int(ParticleFlags.ACTIVE)
        self.model.particle_flags = wp.array(flags)
        print(f"[neckband] pinned {len(pinned)} neck particles")

        self.model.soft_contact_radius = 0.2e-2
        self.model.soft_contact_margin = 0.35e-2
        self.model.soft_contact_ke = 1.0e1    # stiffer penalty overshoots -> the cloth buzzes on the body
        self.model.soft_contact_kd = 1.0e-6
        self.model.soft_contact_mu = 0.2      # high friction here caused stick-slip jitter
        self.model.set_gravity((0.0, 0.0, -9.81))

        self.solver = newton.solvers.SolverStyle3D(model=self.model, iterations=5)
        # Cloth self-collision makes the heavy draping folds buzz against each
        # other forever (they never rest). Off by default for a clean settle
        # (folds may overlap slightly); SELFCOLLIDE=1 re-enables it.
        if os.environ.get("NOCOLLIDE") == "1":
            self.solver.collision = None
        elif os.environ.get("SELFCOLLIDE") != "1" and self.solver.collision is not None:
            self.solver.collision.stiff_vf = 0.0
            self.solver.collision.stiff_ee = 0.0
            self.solver.collision.stiff_ef = 0.0
        self.state_0, self.state_1 = self.model.state(), self.model.state()
        self.control = self.model.control()
        self.contacts = self.model.contacts()
        self.viewer.set_model(self.model)
        try:
            self.viewer.set_camera(wp.vec3(0.0, -1.6, -0.05), 0.0, -270.0)
        except Exception:
            pass

        print(f"[build] {builder.particle_count} particles, {len(self.gfaces)} garment tris, "
              f"body {len(self.body[0])} v")
        self.capture()

    def capture(self):
        if wp.get_device().is_cuda:
            with wp.ScopedCapture() as cap:
                self.simulate()
            self.graph = cap.graph
        else:
            self.graph = None

    def simulate(self):
        self.model.collide(self.state_0, self.contacts)
        for _ in range(self.sim_substeps):
            self.state_0.clear_forces()
            self.viewer.apply_forces(self.state_0)
            self.solver.step(self.state_0, self.state_1, self.control, self.contacts, self.sim_dt)
            self.state_0, self.state_1 = self.state_1, self.state_0
            wp.launch(_damp_velocity, dim=self.model.particle_count,
                      inputs=[self.state_0.particle_qd, self.damp])

    def step(self):
        if self.graph: wp.capture_launch(self.graph)
        else: self.simulate()
        self.sim_time += self.frame_dt

    def render(self):
        self.viewer.begin_frame(self.sim_time)
        self.viewer.log_state(self.state_0)
        self.viewer.log_contacts(self.contacts, self.state_0)
        self.viewer.end_frame()

    def export_obj(self):
        q = self.state_0.particle_q.numpy()
        if np.isnan(q).any():
            print("[export] WARNING: NaN — skipping OBJ"); return
        spd = np.linalg.norm(self.state_0.particle_qd.numpy(), axis=1) * 1000
        p = np.percentile(spd, [50, 90, 99])
        fast = spd > 200
        col = fast & (q[:, 2] > 0.0)                    # collar/neck region
        slv = fast & (np.abs(q[:, 0]) > 0.34)           # out on the sleeves
        bod = fast & ~col & ~slv
        print(f"[settle] speed mm/s: p50={p[0]:.1f} p90={p[1]:.1f} p99={p[2]:.1f} max={spd.max():.1f} "
              f"(damp={self.damp})")
        print(f"[settle] fast(>200): {fast.sum()}  collar={col.sum()} sleeve={slv.sum()} body={bod.sum()}")
        def w(path, verts, faces):
            with open(path, "w") as fh:
                for p in verts: fh.write(f"v {p[0]:.5f} {p[1]:.5f} {p[2]:.5f}\n")
                for f in faces: fh.write(f"f {f[0]+1} {f[1]+1} {f[2]+1}\n")
        w(os.path.join(DIST, "shirt.obj"), q, self.gfaces)
        w(os.path.join(DIST, "body.obj"), self.body[0], self.body[1])
        # one OBJ per pattern piece (front/back/sleeve) so the render can colour
        # them separately — this is what makes the drape SHOW THE PATTERN
        for t, name in enumerate(self.TYPES):
            faces = self.gfaces[self.tri_type == t]
            w(os.path.join(DIST, f"shirt_{name}.obj"), q, faces)
        np.save(os.path.join(DIST, "shirt_q.npy"), q)
        print(f"[export] shirt.obj + per-piece {self.TYPES} + body.obj")


if __name__ == "__main__":
    parser = newton.examples.create_parser()
    parser.add_argument("--maxarea", type=float, default=110.0,
                        help="triangle max area (mm^2); smaller = denser cloth")
    viewer, args = newton.examples.init(parser)
    example = Example(viewer, args)
    newton.examples.run(example, args)
    example.export_obj()
