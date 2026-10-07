# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural trees and shrubs.

A simplified Weber-Penn style generator: a trunk (or several stems for
shrubs) grows child branches level by level. Each level has its own count,
length, angle, curvature and gravity. Leaves or needles go on the last
levels. Bark and foliage are built as two meshes so foliage can be hidden
in winter.
"""

import math

from mathutils import Vector

from . import materials as M
from . import plants as P
from .meshkit import UP, MeshBuilder, any_perpendicular, rotate

MIN_RADIUS = 0.0015


def _level(**kw):
    d = dict(n=10, len=0.5, len_var=0.15, down=50.0, down_var=10.0, rot=137.5, rot_var=20.0,
             curve=0.0, curve_var=10.0, seg=4, sides=4, ratio=0.6, start=0.1, end=0.95,
             gravity=0.0, up=0.0, wobble=0.03, whorl=0, planar=False, tip=0.2, shrink=0.6)
    d.update(kw)
    return d


def _shape(kind, p):
    """Relative length of first-level branches at position p (0 crown base, 1 top)."""
    if kind == "conical":
        return 0.15 + 0.85 * (1.0 - p)
    if kind == "spherical":
        return 0.25 + 0.75 * math.sin(math.pi * min(max(p, 0.0), 1.0))
    if kind == "flame":
        return 0.2 + 0.8 * (p / 0.7 if p <= 0.7 else (1.0 - p) / 0.3)
    if kind == "dome":
        return 0.35 + 0.65 * math.sin(math.pi * (0.25 + 0.6 * p))
    return 1.0


def maple_leaf(mb, base, d, n, length, width, mat, rand):
    """Palmate leaf from three lobes."""
    mb.leaf(base, d, n, length, width, P.pointed, mat=mat, rand=rand, steps=4, fold=0.1)
    side = d.cross(n).normalized()
    for s in (-1, 1):
        ld = (d + side * s * 0.95).normalized()
        mb.leaf(base, ld, n, length * 0.75, width * 0.8, P.pointed, mat=mat, rand=rand, steps=3, fold=0.1)


class TreeGen:
    def __init__(self, cfg, rng):
        self.cfg = cfg
        self.rng = rng
        self.bark = MeshBuilder()
        self.foliage = MeshBuilder()
        self.levels = cfg["levels"]
        self.height = rng.uniform(*cfg["height"])
        self.ref = []

    # -- geometry ---------------------------------------------------------
    def _path(self, start, direction, length, lv):
        rng = self.rng
        seg = lv["seg"]
        pts = [start.copy()]
        d = direction.normalized()
        curve = math.radians(lv["curve"] + rng.gauss(0, lv["curve_var"])) / seg
        for i in range(seg):
            axis = d.cross(UP)
            if axis.length > 1e-6:
                d = rotate(d, axis.normalized(), curve)
            d = d + UP * (lv["up"] - lv["gravity"] * (0.3 + i / seg)) / seg
            d = d + Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))) * lv["wobble"]
            d.normalize()
            pts.append(pts[-1] + d * (length / seg))
        return pts

    def grow(self, level, start, direction, length, radius):
        lv = self.levels[level]
        rng = self.rng
        pts = self._path(start, direction, length, lv)
        seg = lv["seg"]
        radii = []
        for i in range(seg + 1):
            t = i / seg
            r = radius * ((1.0 - t) * (1.0 - lv["tip"]) + lv["tip"])
            if level == 0:
                r *= 1.0 + 0.45 * max(0.0, 1.0 - t / 0.08) ** 2  # root flare
            radii.append(max(r, MIN_RADIUS))
        # vd_height runs up the trunk; branches get one fixed value (branch_height) so
        # height-based bark effects (birch's dark base, pine's copper top) are chosen per species
        bh = self.cfg.get("branch_height", 0.3)
        h0, h1 = (0.0, 1.0) if level == 0 else (bh, bh)
        self.bark.tube(pts, radii, lv["sides"], rand=rng.random(), uv_scale=1.0, h0=h0, h1=h1)

        last = level == len(self.levels) - 1
        if not last:
            self.children(level, pts, radii, length)
        self.foliate(level, pts, last)

    def _sample(self, pts, t):
        f = t * (len(pts) - 1)
        i = min(int(f), len(pts) - 2)
        k = f - i
        p = pts[i].lerp(pts[i + 1], k)
        d = (pts[i + 1] - pts[i]).normalized()
        return p, d, i, k

    def children(self, level, pts, radii, length):
        rng = self.rng
        cl = self.levels[level + 1]
        n = cl["n"] if level == 0 else max(1, round(cl["n"] * min(1.3, length / max(self.ref[level], 1e-3))))
        n = max(1, round(n * rng.uniform(0.85, 1.15)))
        phi = rng.uniform(0, 2 * math.pi)
        whorl = cl["whorl"]
        groups = math.ceil(n / whorl) if whorl else n
        for gi in range(groups):
            t = cl["start"] + (cl["end"] - cl["start"]) * (gi + rng.uniform(0.2, 0.8)) / groups
            p, pd, i, k = self._sample(pts, t)
            pr = radii[i] + (radii[i + 1] - radii[i]) * k
            members = whorl if whorl else 1
            for j in range(members):
                if whorl:
                    ang = phi + j * 2 * math.pi / whorl + rng.gauss(0, 0.25)
                elif cl["planar"]:
                    ang = (0.0 if gi % 2 else math.pi) + rng.gauss(0, 0.3)
                else:
                    phi += math.radians(cl["rot"] + rng.gauss(0, cl["rot_var"]))
                    ang = phi
                if cl["planar"]:
                    perp = pd.cross(UP)
                    perp = perp.normalized() if perp.length > 1e-6 else any_perpendicular(pd)
                    perp = rotate(perp, pd, ang)
                else:
                    perp = rotate(any_perpendicular(pd), pd, ang)
                theta = math.radians(cl["down"] + rng.gauss(0, cl["down_var"]))
                cd = (pd * math.cos(theta) + perp * math.sin(theta)).normalized()
                if level == 0:
                    crown = (t - cl["start"]) / max(cl["end"] - cl["start"], 1e-3)
                    clen = self.trunk_len * cl["len"] * _shape(self.cfg["shape"], crown)
                else:
                    clen = length * cl["len"] * (1.0 - cl["shrink"] * t)
                clen *= 1.0 + rng.uniform(-cl["len_var"], cl["len_var"])
                clen = max(clen, 0.02)
                cr = pr * cl["ratio"] * math.sqrt(min(1.0, clen / max(length, 1e-3)))
                cr = min(cr, pr * 0.85)
                self.grow(level + 1, p - cd * pr * 0.5, cd, clen, cr)

    def foliate(self, level, pts, last):
        fol = self.cfg.get("foliage")
        if not fol or level < fol["from_level"]:
            return
        rng = self.rng
        kind = fol["kind"]
        length = sum((pts[i + 1] - pts[i]).length for i in range(len(pts) - 1))
        if kind == "leaves":
            n = fol["n"] if last else int(fol["n"] * 0.5)
            n = max(1, round(n * min(1.5, length / max(self.ref[-1], 1e-3)) * rng.uniform(0.8, 1.2)))
            phi = rng.uniform(0, 6.28)
            for i in range(n):
                t = fol["start"] + (1.0 - fol["start"]) * (i + rng.random() * 0.5) / n
                if not last:
                    t = 0.5 + 0.5 * t
                p, pd, _i, _k = self._sample(pts, min(t, 1.0))
                phi += math.radians(137.5 + rng.gauss(0, 25))
                perp = rotate(any_perpendicular(pd), pd, phi)
                ang = math.radians(fol["angle"] + rng.gauss(0, 12))
                ld = (pd * math.cos(ang) + perp * math.sin(ang))
                ld = (ld - UP * fol["droop"] + UP * fol.get("lift", 0.0)).normalized()
                nrm = (UP * fol["face_up"] + perp * (1.0 - fol["face_up"]) +
                       Vector((rng.gauss(0, 0.3), rng.gauss(0, 0.3), rng.gauss(0, 0.3)))).normalized()
                size = fol["size"] * rng.uniform(0.75, 1.2)
                base = p + ld * size * 0.15
                if fol["outline"] == "maple":
                    maple_leaf(self.foliage, base, ld, nrm, size, size * 0.6, 0, rng.random())
                else:
                    self.foliage.leaf(base, ld, nrm, size, size * fol["width"], fol["outline"], mat=0,
                                      rand=rng.random(), steps=fol["steps"], fold=0.12, curl=0.12)
        elif kind == "spray":
            start = fol["start"] if last else fol["parent_start"]
            self.foliage.spray(pts, fol["size"] * rng.uniform(0.85, 1.15), fol["spacing"], math.radians(fol["forward"]),
                               [math.radians(a) for a in fol["planes"]], rand=rng.random(), rng=rng, start=start)
        else:  # needles
            density = fol["density"] if last else fol["density"] * 0.6
            n = max(4, int(density * length * rng.uniform(0.8, 1.2)))
            start = fol["start"] if last else 0.6
            r = rng.random()
            for i in range(n):
                t = start + (1.0 - start) * rng.random() ** fol.get("tip_bias", 1.0)
                p, pd, _i, _k = self._sample(pts, t)
                perp = rotate(any_perpendicular(pd), pd, rng.uniform(0, 2 * math.pi))
                nd = (pd * fol["forward"] + perp + UP * fol["up"]).normalized()
                side = nd.cross(perp).normalized()
                self.foliage.needle(p, nd, side, fol["size"] * rng.uniform(0.8, 1.15), fol["width"],
                                    rand=(r + rng.random() * 0.3) % 1.0)

    # -- entry ------------------------------------------------------------
    def build(self):
        cfg = self.cfg
        rng = self.rng
        self.trunk_len = self.height * cfg["trunk"]
        self.ref = [self.trunk_len]
        for lv in self.levels[1:]:
            self.ref.append(self.ref[-1] * lv["len"])
        radius = self.height * cfg["radius"]
        stems = cfg.get("stems", 1)
        for s in range(stems):
            if stems > 1:
                a = s * 2 * math.pi / stems + rng.gauss(0, 0.3)
                out = Vector((math.cos(a), math.sin(a), 0.0))
                lean = math.radians(rng.uniform(*cfg["stem_lean"]))
                d = (UP * math.cos(lean) + out * math.sin(lean)).normalized()
                start = out * radius * 1.5
            else:
                lean = math.radians(cfg.get("lean", 3.0))
                a = rng.uniform(0, 2 * math.pi)
                d = (UP + Vector((math.cos(a), math.sin(a), 0)) * math.tan(rng.uniform(0, lean))).normalized()
                start = Vector((0, 0, -0.05))
            self.grow(0, start, d, self.trunk_len * rng.uniform(0.85, 1.1), radius * rng.uniform(0.85, 1.1))
        return self.bark, self.foliage


# ---------------------------------------------------------------------------
# species

SPECIES = {
    "OAK": dict(
        height=(10.0, 14.0), radius=0.032, trunk=0.55, shape="dome", lean=4.0,
        bark=("furrowed", "#2E2720", "#6B6052", 2.0),
        leaf=("#2F5219", ("#8A5A1E", "#6E4A1C", "#A57A2A"), "#7E9A55"),
        levels=[
            _level(seg=10, sides=14, tip=0.25, wobble=0.04),
            _level(n=30, len=0.95, down=55, down_var=15, curve=25, curve_var=20, seg=7, sides=8,
                   ratio=0.75, start=0.3, end=1.0, gravity=0.25, wobble=0.12, tip=0.12),
            _level(n=13, len=0.5, down=45, down_var=15, curve=-10, seg=4, sides=5, ratio=0.7, gravity=0.3,
                   wobble=0.12, start=0.15),
            _level(n=9, len=0.35, down=45, seg=2, sides=3, ratio=0.7, wobble=0.1, start=0.2),
        ],
        foliage=dict(kind="leaves", from_level=2, n=13, start=0.15, angle=55, droop=0.1, face_up=0.6,
                     size=0.17, width=0.6, outline=P.oak, steps=6),
    ),
    "BIRCH": dict(
        height=(12.0, 16.0), radius=0.016, trunk=0.92, shape="flame", lean=6.0,
        bark=("birch", "#1E1C1A", "#D6D1C4", 1.0),
        leaf=("#3E6A1E", ("#D8B52A", "#C99A1E", "#E2C440"), "#9CB96A"),
        levels=[
            _level(seg=12, sides=10, tip=0.08, wobble=0.03),
            _level(n=52, len=0.38, down=40, down_var=12, curve=-20, curve_var=15, seg=6, sides=5,
                   ratio=0.55, start=0.3, end=0.98, gravity=0.35, wobble=0.08, tip=0.15),
            _level(n=11, len=0.6, down=40, curve=-35, seg=4, sides=3, ratio=0.6, gravity=1.0, wobble=0.08),
            _level(n=8, len=0.45, down=30, curve=-20, seg=3, sides=3, ratio=0.7, gravity=1.4, wobble=0.06),
        ],
        foliage=dict(kind="leaves", from_level=2, n=16, start=0.1, angle=50, droop=0.3, face_up=0.4,
                     size=0.095, width=0.7, outline=P.serrated, steps=4),
    ),
    "MAPLE": dict(
        height=(9.0, 13.0), radius=0.03, trunk=0.5, shape="spherical", lean=3.0,
        bark=("smooth", "#4A4540", "#7D766C", 1.5),
        leaf=("#2D5A1A", ("#C2321A", "#E06A1A", "#E2A42A"), "#86A85A"),
        levels=[
            _level(seg=10, sides=12, tip=0.2, wobble=0.03),
            _level(n=28, len=0.9, down=45, down_var=12, curve=15, curve_var=15, seg=6, sides=7,
                   ratio=0.7, start=0.35, end=1.0, gravity=0.15, wobble=0.08, tip=0.12),
            _level(n=13, len=0.5, down=40, curve=-5, seg=4, sides=4, ratio=0.65, gravity=0.2, wobble=0.08),
            _level(n=8, len=0.35, down=40, seg=2, sides=3, ratio=0.7, wobble=0.08),
        ],
        foliage=dict(kind="leaves", from_level=2, n=7, start=0.3, angle=55, droop=0.1, face_up=0.7,
                     size=0.17, width=0.6, outline="maple", steps=4),
    ),
    "SPRUCE": dict(
        height=(13.0, 18.0), radius=0.018, trunk=1.0, shape="conical", lean=1.5,
        bark=("plates", "#2C231C", "#5E4C3C", 2.0),
        needles=("#22401B", "#355C26"),
        levels=[
            _level(seg=14, sides=10, tip=0.02, wobble=0.01),
            _level(n=150, whorl=5, len=0.33, len_var=0.1, down=95, down_var=8, curve=35, curve_var=10,
                   seg=5, sides=4, ratio=0.5, start=0.06, end=0.99, gravity=0.35, wobble=0.04, tip=0.15),
            _level(n=24, len=0.42, down=62, down_var=10, planar=True, seg=3, sides=3, ratio=0.5,
                   gravity=0.9, wobble=0.05, start=0.15, shrink=0.5),
        ],
        foliage=dict(kind="spray", from_level=1, start=0.0, parent_start=0.3, size=0.15, spacing=0.035,
                     forward=40, planes=(25, -25)),
    ),
    "PINE": dict(
        height=(12.0, 16.0), radius=0.022, trunk=1.0, shape="dome", lean=5.0,
        bark=("pine", "#4A3B30", "#6E5A4A", 1.5), branch_height=0.8,
        needles=("#24401C", "#4C6A2C"),
        levels=[
            _level(seg=12, sides=12, tip=0.06, wobble=0.035),
            _level(n=48, len=0.4, len_var=0.3, down=70, down_var=18, curve=30, curve_var=25, seg=6, sides=6,
                   ratio=0.55, start=0.6, end=0.99, gravity=0.15, wobble=0.15, tip=0.15),
            _level(n=12, len=0.38, down=45, down_var=15, curve=25, seg=3, sides=3, ratio=0.6, wobble=0.12,
                   start=0.25),
            _level(n=7, len=0.45, down=40, down_var=15, curve=20, seg=2, sides=3, ratio=0.7, wobble=0.1,
                   start=0.3),
        ],
        foliage=dict(kind="spray", from_level=2, start=0.25, parent_start=0.65, size=0.16, spacing=0.025,
                     forward=55, planes=(0, 60, 120)),
    ),
    "SHRUB": dict(
        height=(1.4, 2.2), radius=0.012, trunk=0.85, shape="spherical", stems=9, stem_lean=(8, 35),
        bark=("smooth", "#3E342A", "#6B5E4E", 4.0),
        leaf=("#2A4E1A", ("#B5791E", "#C49A2A", "#8E4A1A"), "#7E9A55"),
        levels=[
            _level(seg=6, sides=5, tip=0.25, wobble=0.06, curve=-10),
            _level(n=14, len=0.5, down=40, down_var=15, curve=5, seg=4, sides=3, ratio=0.6, start=0.2,
                   gravity=0.2, wobble=0.1),
            _level(n=9, len=0.45, down=40, seg=2, sides=3, ratio=0.7, wobble=0.1, start=0.2),
        ],
        foliage=dict(kind="leaves", from_level=1, n=18, start=0.1, angle=55, droop=0.05, face_up=0.6,
                     size=0.06, width=0.75, outline=P.ovate, steps=4),
    ),
}


def tree(key):
    cfg = SPECIES[key]

    def build(rng, variant):
        gen = TreeGen(cfg, rng)
        bark, foliage = gen.build()
        name = f"VD {key.title()}"
        bark_mat = M.bark(f"{name} Bark", *cfg["bark"])
        parts = [("bark", bark.build(f"{name} Bark", [bark_mat]), {})]
        if "needles" in cfg:
            mat = M.needles(f"{name} Needles", *cfg["needles"])
            # flat shading: needle sprays share a centre vertex between crossed planes, and the
            # averaged smooth normals there make EEVEE reflect the sky as a grey sheen
            parts.append(("foliage", foliage.build(f"{name} Needles", [mat], smooth=False), {"evergreen": True}))
        else:
            summer, autumn, back = cfg["leaf"]
            mat = M.leaf(f"{name} Leaf", summer, autumn, back=back)
            parts.append(("foliage", foliage.build(f"{name} Leaves", [mat]), {"deciduous": True}))
        return parts

    return build
