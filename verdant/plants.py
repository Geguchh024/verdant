# SPDX-License-Identifier: GPL-3.0-or-later
"""Generators for grass, wildflowers, clover, ferns, stones and leaf litter.

Each generator takes a seeded ``random.Random`` and returns a list of
``(part_name, mesh)`` tuples. Sizes are in metres.
"""

import math

import bmesh
from mathutils import Vector, noise

from . import materials as M
from .meshkit import UP, MeshBuilder, any_perpendicular, rotate

# ---------------------------------------------------------------------------
# leaf outlines: half width (0..1) at fraction t along the midrib


def ovate(t):
    return min(1.0, 1.9 * t ** 0.5 * (1.0 - t) ** 0.85)


def lanceolate(t):
    return min(1.0, 2.6 * t ** 0.7 * (1.0 - t) ** 1.2)


def serrated(t):
    return ovate(t) * (1.0 + 0.07 * math.sin(t * 46.0))


def oak(t):
    base = min(1.0, 1.7 * t ** 0.6 * (1.0 - t) ** 0.55)
    return base * (0.55 + 0.45 * abs(math.cos(t * math.pi * 4.5)))


def pointed(t):
    return min(1.0, 2.2 * t ** 0.55 * (1.0 - t) ** 1.1)


def heart(t):
    # obcordate clover leaflet: widest near the notched tip
    w = 1.6 * t ** 0.6 * (1.0 - t * 0.55)
    return max(0.0, min(1.0, w) * (1.0 - 0.6 * max(0.0, t - 0.85) / 0.15))


def oblong(t):
    return min(1.0, 3.0 * t ** 0.4 * (1.0 - t) ** 0.3)


def round_petal(t):
    return min(1.0, 2.0 * t ** 0.7 * (1.0 - t) ** 0.35)


def pinna(t):
    # a pinna with rounded lobes (pinnules) along both edges
    return min(1.0, 1.8 * t ** 0.3 * (1.0 - t) ** 0.8) * (0.62 + 0.38 * abs(math.sin(t * math.pi * 6.5)))


def strap(t):
    return 1.0 - t ** 3


# ---------------------------------------------------------------------------
# helpers

def _disk(rng, radius):
    a = rng.uniform(0, 2 * math.pi)
    r = radius * math.sqrt(rng.random())
    return Vector((r * math.cos(a), r * math.sin(a), 0.0)), a


def _tilted(rng, outward, lean, jitter=0.15):
    d = UP + outward * lean + Vector((rng.gauss(0, jitter), rng.gauss(0, jitter), 0.0))
    return d.normalized()


def _side_for(direction, rng):
    side = UP.cross(direction)
    if side.length < 1e-6:
        side = Vector((1.0, 0.0, 0.0))
    return rotate(side.normalized(), direction, rng.uniform(-0.6, 0.6))


def _curve(start, direction, length, segments, bend, rng, wobble=0.04):
    """Points along an arching stem."""
    pts = [start.copy()]
    d = direction.normalized()
    for i in range(segments):
        d = (d - UP * bend / segments + Vector((rng.gauss(0, wobble), rng.gauss(0, wobble), 0))).normalized()
        pts.append(pts[-1] + d * (length / segments))
    return pts


def grass_clump(mb, rng, count, radius, height, width, lean=0.5, bend=0.4, segments=4, mat=0, fold=0.3):
    for _ in range(count):
        pos, a = _disk(rng, radius)
        outward = Vector((math.cos(a), math.sin(a), 0.0))
        d = _tilted(rng, outward, lean * rng.uniform(0.3, 1.2))
        length = rng.uniform(*height)
        mb.blade(pos, d, _side_for(d, rng), length, rng.uniform(*width), segments=segments,
                 bend=bend * rng.uniform(0.5, 1.4), fold=fold, mat=mat, rand=rng.random())


def _seed_stalk(mb, rng, base, height, mat_stem, mat_seed, kind="spike"):
    d = (UP + Vector((rng.gauss(0, 0.12), rng.gauss(0, 0.12), 0))).normalized()
    pts = _curve(base, d, height, 6, rng.uniform(0.05, 0.3), rng, 0.02)
    radii = [0.0018 * (1.0 - 0.6 * i / 6) for i in range(7)]
    mb.tube(pts, radii, 3, mat=mat_stem, rand=rng.random())
    tip_dir = (pts[-1] - pts[-2]).normalized()
    head_len = height * rng.uniform(0.12, 0.2)
    r = rng.random()
    if kind == "spike":
        # alternating spikelets along the top of the stalk (ryegrass)
        n = 10
        for i in range(n):
            t = i / n
            p = pts[-1] - tip_dir * head_len * (1.0 - t)
            side = any_perpendicular(tip_dir)
            side = rotate(side, tip_dir, math.pi * i)
            sd = (tip_dir + side * 0.7).normalized()
            mb.leaf(p, sd, side.cross(sd), 0.012, 0.004, lanceolate, mat=mat_seed, rand=r, steps=3, fold=0.3)
    else:
        # loose panicle: thin drooping branches with seeds (meadow grass)
        for i in range(14):
            t = rng.random()
            p = pts[-1] - tip_dir * head_len * t
            side = rotate(any_perpendicular(tip_dir), tip_dir, rng.uniform(0, 2 * math.pi))
            bd = (tip_dir * 0.5 + side + UP * -0.2).normalized()
            blen = rng.uniform(0.015, 0.04) * (0.4 + t)
            mb.tube([p, p + bd * blen], [0.0006, 0.0004], 3, mat=mat_stem, rand=r)
            q = p + bd * blen
            mb.leaf(q, (bd - UP * 0.4).normalized(), any_perpendicular(bd), 0.006, 0.0025, lanceolate,
                    mat=mat_seed, rand=r, steps=3, fold=0.3)


# ---------------------------------------------------------------------------
# grass species

def lawn_grass(rng, variant):
    mb = MeshBuilder()
    grass_clump(mb, rng, rng.randint(30, 42), 0.035, (0.05, 0.11), (0.0025, 0.004),
                lean=0.5, bend=0.25, segments=4)
    mat = M.grass("VD Lawn Grass", "#1E3410", "#3C6A1C", "#7EA33C", "#A99A5B", dryness=0.04)
    return [("blades", mb.build("VD Lawn Grass", [mat]))]


def meadow_grass(rng, variant):
    mb = MeshBuilder()
    grass_clump(mb, rng, rng.randint(45, 65), 0.07, (0.2, 0.55), (0.004, 0.007),
                lean=0.45, bend=0.5, segments=5)
    for _ in range(rng.randint(2, 6) if variant != 0 else 0):
        base, _a = _disk(rng, 0.04)
        _seed_stalk(mb, rng, base, rng.uniform(0.45, 0.8), 1, 2, kind="spike" if variant == 1 else "panicle")
    mats = [M.grass("VD Meadow Grass", "#1F3510", "#45701F", "#93AD45", "#B5A464", dryness=0.08),
            M.stem("VD Grass Stem", "#5A7A2A", "#A5A060"),
            M.flat("VD Seed Head", "#9C9466", translucency=0.3, var=0.2)]
    return [("blades", mb.build("VD Meadow Grass", mats))]


def tall_tuft(rng, variant):
    """Arching ornamental grass with feathery plumes (like Miscanthus)."""
    mb = MeshBuilder()
    grass_clump(mb, rng, rng.randint(70, 95), 0.12, (0.7, 1.3), (0.009, 0.014),
                lean=0.9, bend=0.9, segments=7, fold=0.2)
    for _ in range(rng.randint(5, 10) if variant != 1 else 0):
        base, _a = _disk(rng, 0.08)
        h = rng.uniform(1.3, 1.8)
        d = (UP + Vector((rng.gauss(0, 0.1), rng.gauss(0, 0.1), 0))).normalized()
        pts = _curve(base, d, h, 6, 0.15, rng, 0.015)
        mb.tube(pts, [0.003 * (1 - 0.5 * i / 6) for i in range(7)], 3, mat=1, rand=rng.random())
        # feathery plume: a soft spray along the top of the stalk
        td = (pts[-1] - pts[-2]).normalized()
        plume = [pts[-1] - td * 0.28, pts[-1] - td * 0.14, pts[-1]]
        mb.spray(plume, 0.05, 0.01, math.radians(25), [0.0, math.radians(60), math.radians(120)],
                 mat=2, rand=rng.random(), rng=rng)
    mats = [M.grass("VD Tall Tuft", "#22381A", "#4F7A2E", "#9AB066", "#C2AE76", dryness=0.12),
            M.stem("VD Tuft Stem", "#6C7E3A", "#B9A877"),
            M.flat("VD Plume", "#A8977A", translucency=0.5, var=0.15)]
    return [("blades", mb.build("VD Tall Tuft", mats))]


def dry_grass(rng, variant):
    mb = MeshBuilder()
    grass_clump(mb, rng, rng.randint(25, 40), 0.06, (0.15, 0.45), (0.003, 0.006),
                lean=0.8, bend=0.7, segments=5)
    for _ in range(rng.randint(2, 5)):
        base, _a = _disk(rng, 0.04)
        _seed_stalk(mb, rng, base, rng.uniform(0.35, 0.6), 1, 2, kind="panicle")
    mats = [M.grass("VD Dry Grass", "#4D4524", "#9B8A4F", "#CDB97E", "#C9B27A", dryness=0.45),
            M.stem("VD Dry Stem", "#9B8A55", "#C8B47E"),
            M.flat("VD Dry Seed", "#B49E6A", translucency=0.3, var=0.2)]
    return [("blades", mb.build("VD Dry Grass", mats))]


# ---------------------------------------------------------------------------
# flowers and small plants

def clover(rng, variant):
    mb = MeshBuilder()
    for _ in range(rng.randint(22, 34)):
        base, a = _disk(rng, 0.09)
        h = rng.uniform(0.03, 0.08)
        out = Vector((math.cos(a), math.sin(a), 0))
        pts = _curve(base, _tilted(rng, out, 0.4), h, 3, 0.1, rng, 0.05)
        mb.tube(pts, [0.0012, 0.001, 0.0009, 0.0008], 3, mat=1, rand=rng.random())
        top = pts[-1]
        r = rng.random()
        spin = rng.uniform(0, 2 * math.pi)
        size = rng.uniform(0.014, 0.022)
        for k in range(3):
            ang = spin + k * 2 * math.pi / 3
            d = Vector((math.cos(ang), math.sin(ang), rng.uniform(-0.05, 0.2))).normalized()
            mb.leaf(top, d, UP, size, size * 1.1, heart, mat=0, rand=r, steps=5, fold=0.15, curl=-0.1)
    if variant == 1:
        # white clover flower heads
        for _ in range(rng.randint(2, 4)):
            base, _a = _disk(rng, 0.05)
            pts = _curve(base, UP, rng.uniform(0.1, 0.16), 3, 0.05, rng, 0.03)
            mb.tube(pts, [0.0012] * 4, 3, mat=1)
            c = pts[-1]
            for i in range(40):
                d = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0.3, 1))).normalized()
                mb.needle(c, d, any_perpendicular(d), 0.008, 0.0015, mat=2, rand=rng.random())
    mats = [M.leaf("VD Clover", "#2F5A1C", ("#6A6A22", "#8A7A30", "#5A4A20"), back="#6C8F48", vein=0.25,
                   evergreen=True),
            M.stem("VD Clover Stem", "#4F7A2E"),
            M.petal("VD Clover Flower", "#F1EEE4")]
    return [("plant", mb.build("VD Clover", mats))]


FLOWERS = [
    # name, petal colour, centre colour, petals, petal length, width, outline, cup, centre radius
    ("Daisy", "#F4F2EC", "#E3B21A", 22, 0.019, 0.0045, oblong, 0.05, 0.006),
    ("Poppy", "#C8231A", "#1E1A14", 4, 0.03, 0.035, round_petal, 0.45, 0.005),
    ("Cornflower", "#3D5FC9", "#3A2F6A", 11, 0.018, 0.009, pointed, 0.2, 0.005),
    ("Buttercup", "#F2C318", "#C9A010", 5, 0.013, 0.013, round_petal, 0.35, 0.003),
]


def wildflower(rng, variant):
    name, color, center, n, plen, pw, outline, cup, cr = FLOWERS[variant % len(FLOWERS)]
    mb = MeshBuilder()
    # basal leaves
    for _ in range(rng.randint(4, 8)):
        base, a = _disk(rng, 0.03)
        out = Vector((math.cos(a), math.sin(a), 0))
        d = _tilted(rng, out, 1.2)
        mb.blade(base, d, _side_for(d, rng), rng.uniform(0.06, 0.14), rng.uniform(0.008, 0.015),
                 segments=4, bend=0.5, fold=0.2, mat=0, rand=rng.random(), width_fn=lambda t: lanceolate(t) + 0.15)
    for _ in range(rng.randint(1, 3)):
        base, _a = _disk(rng, 0.02)
        h = rng.uniform(0.25, 0.5)
        d = (UP + Vector((rng.gauss(0, 0.12), rng.gauss(0, 0.12), 0))).normalized()
        pts = _curve(base, d, h, 5, rng.uniform(-0.1, 0.15), rng, 0.03)
        mb.tube(pts, [0.0018 * (1 - 0.3 * i / 5) for i in range(6)], 4, mat=0, rand=rng.random())
        # a couple of stem leaves
        for k in range(2):
            p = pts[1 + k]
            sd = rotate(any_perpendicular(d), d, rng.uniform(0, 6.28))
            ld = (sd + UP * 0.6).normalized()
            mb.leaf(p, ld, ld.cross(sd.cross(ld)).normalized(), 0.04, 0.008, lanceolate, mat=0,
                    rand=rng.random(), steps=4)
        top = pts[-1]
        face = ((pts[-1] - pts[-2]).normalized() + UP).normalized()
        r = rng.random()
        spin = rng.uniform(0, 2 * math.pi)
        x = any_perpendicular(face)
        for i in range(n):
            ang = spin + i * 2 * math.pi / n + rng.gauss(0, 0.05)
            radial = rotate(x, face, ang)
            pd = (radial + face * cup).normalized()
            mb.leaf(top + radial * cr * 0.8, pd, face, plen * rng.uniform(0.9, 1.1), pw, outline,
                    mat=1, rand=r, steps=5, fold=0.05, curl=-0.1 * cup)
        # centre: short fat tube with a cap
        mb.tube([top - face * 0.002, top + face * 0.003], [cr, cr * 0.85], 8, mat=2, rand=r, cap=True)
    mats = [M.stem("VD Flower Leaf", "#355E20", "#4A7A2A"),
            M.petal(f"VD {name} Petal", color),
            M.flat(f"VD {name} Centre", center, rough=0.8)]
    return [("plant", mb.build(f"VD {name}", mats))]


def fern(rng, variant):
    mb = MeshBuilder()
    fronds = rng.randint(7, 12)
    for f in range(fronds):
        a = f * 2 * math.pi / fronds + rng.gauss(0, 0.2)
        out = Vector((math.cos(a), math.sin(a), 0))
        length = rng.uniform(0.45, 0.85)
        d = _tilted(rng, out, rng.uniform(0.5, 1.1), 0.05)
        pts = _curve(out * 0.02, d, length, 10, rng.uniform(0.9, 1.5), rng, 0.01)
        mb.tube(pts, [0.003 * (1 - 0.8 * i / 10) for i in range(11)], 3, mat=1, rand=rng.random())
        side = UP.cross(d).normalized()
        r = rng.random()
        pinnae = 26
        for i in range(2, pinnae):
            t = i / pinnae
            k = int(t * 10)
            p = pts[k].lerp(pts[min(k + 1, 10)], t * 10 - k)
            td = (pts[min(k + 1, 10)] - pts[k]).normalized()
            plen = length * 0.2 * math.sin(math.pi * min(1.0, t * 1.12)) ** 0.7 + 0.008
            for s in (-1, 1):
                pd = (side * s + td * 0.55).normalized()
                nrm = td.cross(side * s).normalized() * s
                if nrm.z < 0:
                    nrm = -nrm
                mb.leaf(p, pd, nrm, plen, plen * 0.17, pinna, mat=0, rand=r, steps=11, fold=0.1, curl=0.2)
    mats = [M.leaf("VD Fern", "#355F1A", ("#8A6A26", "#9A5A22", "#6A4A1E"), back="#5C8A35", vein=0.1, rough=0.65),
            M.stem("VD Fern Stem", "#3E5A1E", "#5C7A2E")]
    return [("plant", mb.build("VD Fern", mats))]


# ---------------------------------------------------------------------------
# ground debris

def stone(rng, variant):
    """A broken stone: a noisy blob with a few flat fracture facets."""
    import bpy
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1.0)
    off = Vector((rng.uniform(0, 100), rng.uniform(0, 100), rng.uniform(0, 100)))
    sx, sy, sz = rng.uniform(0.8, 1.2), rng.uniform(0.6, 0.95), rng.uniform(0.45, 0.75)
    cuts = []
    for _ in range(rng.randint(3, 6)):
        n = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 0.6))).normalized()
        cuts.append((n, rng.uniform(0.55, 0.85)))
    for v in bm.verts:
        co = v.co
        co *= 1.0 + 0.3 * noise.fractal(co * 1.2 + off, 0.5, 2.0, 4) + 0.06 * noise.noise(co * 5.0 + off)
        for n, d in cuts:  # flatten everything beyond each fracture plane onto it
            k = co.dot(n) - d
            if k > 0:
                co -= n * k
        co.z = max(co.z, -0.3)
        co.x *= sx
        co.y *= sy
        co.z *= sz
    size = [0.08, 0.18, 0.35][variant % 3] * rng.uniform(0.8, 1.2)
    for v in bm.verts:
        v.co *= size
        v.co.z += size * sz * 0.15
    me = bpy.data.meshes.new("VD Stone")
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    if hasattr(me, "set_sharp_from_angle"):  # keep fracture edges crisp
        me.set_sharp_from_angle(angle=math.radians(38))
    me.materials.append(M.rock("VD Stone"))
    return [("stone", me)]


LITTER_OUTLINES = (oak, ovate, serrated, pointed)


def leaf_litter(rng, variant):
    mb = MeshBuilder()
    for _ in range(rng.randint(18, 30)):
        pos, a = _disk(rng, 0.3)
        pos.z = rng.uniform(0.002, 0.012)
        d = Vector((math.cos(a), math.sin(a), rng.uniform(-0.1, 0.1))).normalized()
        nrm = (UP + Vector((rng.gauss(0, 0.3), rng.gauss(0, 0.3), 0))).normalized()
        length = rng.uniform(0.04, 0.09)
        mb.leaf(pos, d, nrm, length, length * rng.uniform(0.5, 0.75), rng.choice(LITTER_OUTLINES), mat=0,
                rand=rng.random(), steps=8, fold=0.2, curl=rng.uniform(-0.3, 0.3))
    for _ in range(rng.randint(2, 5)):
        pos, a = _disk(rng, 0.25)
        d = Vector((math.cos(a), math.sin(a), 0.0))
        pts = _curve(pos + UP * 0.005, d, rng.uniform(0.1, 0.3), 4, -0.02, rng, 0.08)
        for p in pts:
            p.z = max(p.z, 0.004)
        mb.tube(pts, [0.004, 0.0035, 0.003, 0.0025, 0.002], 4, mat=1, rand=rng.random())
    mats = [M.leaf("VD Leaf Litter", "#6B4A22", ("#7A4E22", "#5A3A1C", "#8E6A2C"), back="#7A6040",
                   spring="#6B4A22", vein=0.2, translucency=0.1, rough=0.7, evergreen=True),
            M.bark("VD Twig Bark", "smooth", "#3A2E24", "#5E4E3E", 3.0)]
    return [("litter", mb.build("VD Leaf Litter", mats))]
