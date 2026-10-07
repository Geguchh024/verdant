# SPDX-License-Identifier: GPL-3.0-or-later
"""Procedural shaders for vegetation, bark, rocks and ground.

No image textures: everything is built from standard shader nodes, so the
materials keep working without the add-on. All vegetation shaders read the
``VD Season`` node group, which lets one scene setting turn every plant
spring-fresh, autumn-coloured or winter-dry at once.
"""

import math

import bpy

SEASON_GROUP = "VD Season"
SEASONS = {
    # spring, autumn, winter
    "SPRING": (1.0, 0.0, 0.0),
    "SUMMER": (0.0, 0.0, 0.0),
    "AUTUMN": (0.0, 1.0, 0.0),
    "WINTER": (0.0, 0.6, 1.0),
}


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_color(h):
    h = h.lstrip("#")
    r, g, b = (srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))
    return (r, g, b, 1.0)


def _available(sockets):
    for s in sockets:
        if getattr(s, "is_unavailable", not getattr(s, "enabled", True)):
            continue
        yield s


_ALIASES = {"Fac": "Factor", "Factor": "Fac"}


def _find(sockets, key):
    if isinstance(key, int):
        return list(_available(sockets))[key]
    for name in (key, _ALIASES.get(key)):
        for s in _available(sockets):
            if s.name == name or s.identifier == name:
                return s
    raise KeyError(key)


class NB:
    """Tiny node builder: helpers take values or sockets and return a socket."""

    def __init__(self, tree):
        self.tree = tree
        self.nodes = tree.nodes
        self.links = tree.links

    def node(self, idname, inputs=None, **props):
        n = self.nodes.new(idname)
        for k, v in props.items():
            setattr(n, k, v)
        for k, v in (inputs or {}).items():
            self.set(_find(n.inputs, k), v)
        return n

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.links.new(v, sock)
        elif v is not None:
            if isinstance(v, str):
                v = hex_color(v)
            if sock.type == "RGBA" and len(v) == 3:
                v = (*v, 1.0)
            sock.default_value = v

    @staticmethod
    def out(node, key=0):
        return _find(node.outputs, key)

    def math(self, op, a, b=0.0, clamp=False):
        n = self.node("ShaderNodeMath", {0: a}, operation=op, use_clamp=clamp)
        if len(list(_available(n.inputs))) > 1:
            self.set(_find(n.inputs, 1), b)
        return self.out(n)

    def vmath(self, op, a, b=(0, 0, 0), key=0):
        return self.out(self.node("ShaderNodeVectorMath", {0: a, 1: b}, operation=op), key)

    def mix(self, fac, a, b, blend="MIX"):
        n = self.node("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_factor=True)
        self.set(_find(n.inputs, "Factor_Float"), fac)
        self.set(_find(n.inputs, "A_Color"), a)
        self.set(_find(n.inputs, "B_Color"), b)
        return _find(n.outputs, "Result_Color")

    def smooth(self, x, lo, hi):
        n = self.node("ShaderNodeMapRange", {"Value": x, "From Min": lo, "From Max": hi},
                      interpolation_type="SMOOTHSTEP")
        return self.out(n, "Result")

    def remap(self, x, lo, hi, a, b):
        return self.out(self.node("ShaderNodeMapRange", {"Value": x, "From Min": lo, "From Max": hi,
                                                          "To Min": a, "To Max": b}), "Result")

    def attr(self, name):
        return self.out(self.node("ShaderNodeAttribute", attribute_name=name), "Fac")

    def obj_random(self):
        return self.out(self.node("ShaderNodeObjectInfo"), "Random")

    def hsv(self, color, hue=0.5, sat=1.0, val=1.0):
        n = self.node("ShaderNodeHueSaturation", {"Color": color, "Hue": hue, "Saturation": sat, "Value": val})
        return self.out(n)

    def noise(self, vec, scale, detail=4.0, rough=0.5, key="Fac"):
        return self.out(self.node("ShaderNodeTexNoise", {"Vector": vec, "Scale": scale, "Detail": detail,
                                                         "Roughness": rough}), key)

    def voronoi(self, vec, scale, feature="F1", key="Distance", rand=1.0):
        return self.out(self.node("ShaderNodeTexVoronoi", {"Vector": vec, "Scale": scale, "Randomness": rand},
                                  feature=feature), key)

    def season(self):
        n = self.nodes.new("ShaderNodeGroup")
        n.node_tree = season_group()
        return n.outputs["Spring"], n.outputs["Autumn"], n.outputs["Winter"]

    def bump(self, height, strength=0.4, distance=0.01):
        return self.out(self.node("ShaderNodeBump", {"Height": height, "Strength": strength, "Distance": distance}))


def season_group():
    g = bpy.data.node_groups.get(SEASON_GROUP)
    if g:
        return g
    g = bpy.data.node_groups.new(SEASON_GROUP, "ShaderNodeTree")
    out = g.nodes.new("NodeGroupOutput")
    for i, name in enumerate(("Spring", "Autumn", "Winter")):
        g.interface.new_socket(name, in_out="OUTPUT", socket_type="NodeSocketFloat")
        v = g.nodes.new("ShaderNodeValue")
        v.name = v.label = name
        v.location = (-200, -100 * i)
        g.links.new(v.outputs[0], out.inputs[name])
    scene_props = getattr(bpy.context.scene, "verdant", None)
    if scene_props is not None:
        set_season(scene_props.season)
    return g


def set_season(key):
    g = bpy.data.node_groups.get(SEASON_GROUP)
    if g is None:
        return
    for name, value in zip(("Spring", "Autumn", "Winter"), SEASONS[key]):
        g.nodes[name].outputs[0].default_value = value


def _new(name):
    m = bpy.data.materials.get(name)
    if m:
        return m, None
    m = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        m.use_nodes = True
    m.use_backface_culling = False
    m["vd"] = True
    nt = m.node_tree
    nt.nodes.clear()
    return m, NB(nt)


def _finish(nb, color, rough=0.5, translucency=0.0, normal=None, spec=0.5, sheen=0.0):
    p = nb.node("ShaderNodeBsdfPrincipled", {"Base Color": color, "Roughness": rough, "Specular IOR Level": spec})
    if normal is not None:
        nb.set(p.inputs["Normal"], normal)
    if sheen:
        nb.set(p.inputs["Sheen Weight"], sheen)
    shader = nb.out(p)
    if translucency:
        t = nb.node("ShaderNodeBsdfTranslucent", {"Color": nb.hsv(color, 0.5, 1.15, 1.25)})
        if normal is not None:
            nb.set(t.inputs["Normal"], normal)
        m = nb.node("ShaderNodeMixShader", {0: translucency, 1: shader, 2: nb.out(t)})
        shader = nb.out(m)
    o = nb.node("ShaderNodeOutputMaterial")
    nb.links.new(shader, o.inputs["Surface"])
    p.location = (600, 0)
    o.location = (1000, 0)


# ---------------------------------------------------------------------------
# vegetation

def grass(name, base, mid, tip, dry, dryness=0.06, translucency=0.35):
    """Grass blades: dark base, colour variation per blade and per clump,
    a share of dry blades that grows in autumn and winter."""
    m, nb = _new(name)
    if nb is None:
        return m
    spring, autumn, winter = nb.season()
    h = nb.attr("vd_height")
    r = nb.attr("vd_rand")
    orr = nb.obj_random()
    col = nb.mix(nb.smooth(h, 0.0, 0.45), base, mid)
    col = nb.mix(nb.smooth(h, 0.45, 1.0), col, tip)
    col = nb.mix(nb.math("MULTIPLY", spring, 0.35), col, "#9BC23A")
    # some blades are dry; more of them in autumn and nearly all in winter
    dry_share = nb.math("ADD", dryness, nb.math("ADD", nb.math("MULTIPLY", autumn, 0.35),
                                                 nb.math("MULTIPLY", winter, 0.75)))
    r2 = nb.math("FRACT", nb.math("MULTIPLY", r, 7.13))
    is_dry = nb.math("LESS_THAN", r2, dry_share)
    dry_col = nb.mix(nb.smooth(h, 0.0, 0.6), nb.hsv(dry, 0.5, 1.0, 0.55), dry)
    col = nb.mix(is_dry, col, dry_col)
    hue = nb.remap(nb.math("ADD", r, orr), 0.0, 2.0, 0.47, 0.53)
    val = nb.remap(r, 0.0, 1.0, 0.75, 1.15)
    col = nb.hsv(col, hue, nb.remap(orr, 0, 1, 0.85, 1.1), val)
    # cheap ambient occlusion toward the root
    col = nb.mix(nb.math("POWER", h, 0.6), nb.hsv(col, 0.5, 1.0, 0.35), col)
    _finish(nb, col, rough=0.48, translucency=translucency, spec=0.35)
    return m


def leaf(name, summer, autumn_cols, back="#9FB86A", spring="#8CC63F", vein=0.12, translucency=0.3,
         rough=0.55, evergreen=False):
    """Broad leaves with veins from UVs, a lighter underside and seasonal colour.

    In autumn each tree (Object Info random) and each leaf (vd_rand) picks
    from the species' autumn palette and turns at a slightly different time.
    """
    m, nb = _new(name)
    if nb is None:
        return m
    sp, autumn, winter = nb.season()
    uv = nb.node("ShaderNodeUVMap", uv_map="UVMap")
    sep = nb.node("ShaderNodeSeparateXYZ", {"Vector": nb.out(uv)})
    u, v = nb.out(sep, "X"), nb.out(sep, "Y")
    du = nb.math("ABSOLUTE", nb.math("SUBTRACT", u, 0.5))
    midrib = nb.math("SUBTRACT", 1.0, nb.smooth(du, 0.0, 0.025))
    side = nb.math("SINE", nb.math("MULTIPLY", nb.math("SUBTRACT", v, nb.math("MULTIPLY", du, 1.4)), 38.0))
    veins = nb.math("MULTIPLY", nb.smooth(side, 0.85, 1.0), nb.math("SUBTRACT", 1.0, nb.smooth(du, 0.35, 0.5)))
    vein_mask = nb.math("MAXIMUM", midrib, nb.math("MULTIPLY", veins, 0.6))
    r = nb.attr("vd_rand")
    orr = nb.obj_random()

    col = summer
    col = nb.mix(nb.math("MULTIPLY", sp, 0.6), col, spring)
    if not evergreen:
        # pick an autumn colour per tree and per leaf
        pick = nb.math("FRACT", nb.math("ADD", nb.math("MULTIPLY", orr, 0.7), nb.math("MULTIPLY", r, 0.45)))
        a = nb.mix(nb.smooth(pick, 0.2, 0.5), autumn_cols[0], autumn_cols[1])
        a = nb.mix(nb.smooth(pick, 0.6, 0.9), a, autumn_cols[2])
        turn = nb.math("SUBTRACT", nb.math("MULTIPLY", autumn, 1.5), nb.math("MULTIPLY", r, 0.5), clamp=True)
        col = nb.mix(turn, col, a)
    else:
        col = nb.mix(nb.math("MULTIPLY", winter, 0.4), col, nb.hsv(col, 0.48, 0.7, 0.75))
    # blotchy per-leaf variation
    col = nb.hsv(col, nb.remap(r, 0, 1, 0.48, 0.52), nb.remap(orr, 0, 1, 0.9, 1.1), nb.remap(r, 0, 1, 0.8, 1.15))
    col = nb.mix(nb.math("MULTIPLY", vein_mask, vein), col, nb.hsv(col, 0.5, 0.7, 1.6))
    geo = nb.node("ShaderNodeNewGeometry")
    col = nb.mix(nb.math("MULTIPLY", nb.out(geo, "Backfacing"), 0.55), col, nb.mix(0.5, col, back))
    normal = nb.bump(nb.math("SUBTRACT", 1.0, vein_mask), 0.25, 0.002)
    _finish(nb, col, rough=rough, translucency=translucency, normal=normal, spec=0.45)
    return m


def needles(name, color, tip="#6E8F3A"):
    m, nb = _new(name)
    if nb is None:
        return m
    sp, autumn, winter = nb.season()
    h = nb.attr("vd_height")
    r = nb.attr("vd_rand")
    col = nb.mix(nb.math("MULTIPLY", h, 0.5), color, tip)
    col = nb.mix(nb.math("MULTIPLY", sp, nb.math("MULTIPLY", h, 0.8)), col, "#8DBF45")
    col = nb.mix(nb.math("MULTIPLY", winter, 0.35), col, nb.hsv(col, 0.48, 0.7, 0.7))
    col = nb.hsv(col, nb.remap(r, 0, 1, 0.48, 0.52), nb.remap(nb.obj_random(), 0, 1, 0.85, 1.1),
                 nb.remap(r, 0, 1, 0.7, 1.15))
    _finish(nb, col, rough=0.62, translucency=0.2, spec=0.22)
    return m


def petal(name, color, center="#E8C21A", center_size=0.0):
    """Flower petals: colour fades slightly toward the base."""
    m, nb = _new(name)
    if nb is None:
        return m
    h = nb.attr("vd_height")
    r = nb.attr("vd_rand")
    col = nb.mix(nb.smooth(h, 0.0, 0.35), nb.hsv(color, 0.5, 1.1, 0.6), color)
    if center_size:
        col = nb.mix(nb.math("LESS_THAN", h, center_size), col, center)
    col = nb.hsv(col, nb.remap(r, 0, 1, 0.49, 0.51), 1.0, nb.remap(nb.obj_random(), 0, 1, 0.85, 1.1))
    _finish(nb, col, rough=0.45, translucency=0.4, spec=0.4, sheen=0.3)
    return m


def flat(name, color, rough=0.6, translucency=0.0, var=0.1):
    """Solid colour with per-part variation (flower centres, stems, seed heads)."""
    m, nb = _new(name)
    if nb is None:
        return m
    r = nb.attr("vd_rand")
    col = nb.hsv(color, nb.remap(r, 0, 1, 0.5 - var * 0.2, 0.5 + var * 0.2), 1.0,
                 nb.remap(nb.obj_random(), 0, 1, 1.0 - var, 1.0 + var))
    _finish(nb, col, rough=rough, translucency=translucency)
    return m


def _bark_coords(nb, scale):
    """Seamless bark coordinates: wrap UV u onto a circle with unit circumference."""
    uv = nb.node("ShaderNodeUVMap", uv_map="UVMap")
    sep = nb.node("ShaderNodeSeparateXYZ", {"Vector": nb.out(uv)})
    ang = nb.math("MULTIPLY", nb.out(sep, "X"), 2 * math.pi)
    k = 1.0 / (2 * math.pi)
    x = nb.math("MULTIPLY", nb.math("COSINE", ang), k)
    y = nb.math("MULTIPLY", nb.math("SINE", ang), k)
    vec = nb.out(nb.node("ShaderNodeCombineXYZ", {"X": x, "Y": y, "Z": nb.out(sep, "Y")}))
    return nb.vmath("MULTIPLY", vec, (scale, scale, scale)), nb.out(sep, "Y")


def bark(name, style, dark, light, scale=1.0):
    """Bark styles: furrowed (oak), birch, smooth (maple), plates (spruce) and pine (Scots pine)."""
    m, nb = _new(name)
    if nb is None:
        return m
    co, v = _bark_coords(nb, scale)
    stretch = nb.vmath("MULTIPLY", co, (1.0, 1.0, 0.25))
    n = nb.noise(co, 6.0, 8.0, 0.6)
    if style == "furrowed":
        vor = nb.voronoi(nb.vmath("ADD", stretch, nb.vmath("MULTIPLY", n, (0.2, 0.2, 0.2))), 5.0, "DISTANCE_TO_EDGE")
        height = nb.smooth(vor, 0.0, 0.12)
        col = nb.mix(height, dark, light)
        col = nb.mix(nb.noise(co, 2.0), nb.hsv(col, 0.5, 0.8, 0.8), col)
        rough_h = nb.math("ADD", nb.math("MULTIPLY", height, 0.8), nb.math("MULTIPLY", n, 0.2))
        _finish(nb, col, rough=0.85, normal=nb.bump(rough_h, 0.9, 0.02), spec=0.2)
    elif style == "birch":
        # dark horizontal lenticels and black patches on white bark
        lent = nb.noise(nb.vmath("MULTIPLY", co, (3.0, 3.0, 40.0)), 3.0, 2.0)
        lent = nb.smooth(lent, 0.62, 0.7)
        patch = nb.smooth(nb.noise(nb.vmath("MULTIPLY", co, (1.0, 1.0, 0.6)), 1.4, 6.0, 0.65), 0.62, 0.68)
        col = nb.mix(nb.noise(co, 8.0), light, nb.hsv(light, 0.5, 1.3, 0.85))
        col = nb.mix(lent, col, "#3A3632")
        col = nb.mix(patch, col, dark)
        # old birches turn dark and fissured near the ground
        base = nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, nb.smooth(nb.attr("vd_height"), 0.0, 0.12)),
                       nb.smooth(nb.noise(co, 3.0, 4.0), 0.3, 0.55))
        col = nb.mix(base, col, "#2A2622")
        hgt = nb.math("SUBTRACT", 1.0, nb.math("MAXIMUM", lent, patch))
        _finish(nb, col, rough=0.6, normal=nb.bump(hgt, 0.4, 0.004), spec=0.3)
    elif style == "plates":
        vor = nb.voronoi(nb.vmath("ADD", nb.vmath("MULTIPLY", co, (1.0, 1.0, 0.5)),
                                  nb.vmath("MULTIPLY", n, (0.15, 0.15, 0.15))), 4.0, "DISTANCE_TO_EDGE")
        cracks = nb.smooth(vor, 0.0, 0.06)
        col = nb.mix(cracks, dark, light)
        _finish(nb, col, rough=0.8, normal=nb.bump(cracks, 0.8, 0.015), spec=0.25)
    elif style == "pine":
        # Scots pine: thick grey-brown plates split by deep furrows low on the trunk,
        # turning into thin, flaking copper bark higher up
        h = nb.attr("vd_height")
        zone = nb.smooth(nb.math("ADD", h, nb.math("MULTIPLY", nb.math("SUBTRACT", nb.noise(co, 1.5, 3.0), 0.5),
                                                  0.3)), 0.4, 0.62)
        warp = nb.vmath("MULTIPLY", n, (0.06, 0.06, 0.06))
        # roughly ten plates around the trunk, each about three times taller than wide
        vor = nb.voronoi(nb.vmath("ADD", nb.vmath("MULTIPLY", co, (1.0, 1.0, 0.33)), warp), 7.0, "DISTANCE_TO_EDGE")
        plate = nb.smooth(vor, 0.01, 0.16)  # wide, deep furrows
        grain = nb.noise(nb.vmath("MULTIPLY", co, (6.0, 6.0, 2.0)), 6.0, 6.0, 0.6)
        scaly = nb.voronoi(nb.vmath("MULTIPLY", co, (1.0, 1.0, 0.6)), 40.0, "DISTANCE_TO_EDGE")
        lower = nb.mix(grain, dark, light)
        lower = nb.mix(nb.math("MULTIPLY", nb.smooth(scaly, 0.0, 0.08), 0.2), nb.hsv(lower, 0.5, 0.9, 0.7), lower)
        lower = nb.mix(nb.math("MULTIPLY", plate, nb.smooth(grain, 0.5, 0.7)), lower, "#8C7F72")  # weathered tops
        lower = nb.mix(nb.math("MULTIPLY", nb.smooth(nb.noise(co, 4.0, 3.0), 0.55, 0.7), 0.6), lower, "#7A5038")
        lower = nb.mix(plate, "#2A1F18", lower)
        # thin papery scales that peel sideways
        flake_n = nb.noise(nb.vmath("MULTIPLY", co, (3.0, 3.0, 16.0)), 7.0, 3.0, 0.5)
        flakes = nb.smooth(flake_n, 0.52, 0.6)
        upper = nb.mix(nb.noise(co, 12.0, 3.0), "#8C4F31", "#A5643F")
        upper = nb.mix(nb.math("MULTIPLY", flakes, 0.45), upper, "#BF8A62")
        edge = nb.math("MULTIPLY", nb.smooth(flake_n, 0.47, 0.52), nb.math("SUBTRACT", 1.0, flakes))
        upper = nb.mix(nb.math("MULTIPLY", edge, 0.5), upper, nb.hsv(upper, 0.5, 1.0, 0.65))
        col = nb.mix(zone, lower, upper)
        plate_h = nb.math("ADD", plate, nb.math("MULTIPLY", nb.math("ADD", grain, nb.smooth(scaly, 0.0, 0.08)), 0.12))
        height = nb.out(nb.node("ShaderNodeMix", {"Factor_Float": zone, "A_Float": plate_h,
                                                  "B_Float": nb.math("MULTIPLY", flakes, 0.15)}, data_type="FLOAT"),
                        "Result_Float")
        rough = nb.remap(zone, 0.0, 1.0, 0.88, 0.7)
        _finish(nb, col, rough=rough, normal=nb.bump(height, 1.0, 0.03), spec=0.2)
    else:  # smooth
        streak = nb.noise(nb.vmath("MULTIPLY", co, (4.0, 4.0, 0.4)), 3.0, 6.0)
        col = nb.mix(streak, dark, light)
        lich = nb.smooth(nb.noise(co, 3.0, 5.0, 0.7), 0.6, 0.7)
        col = nb.mix(nb.math("MULTIPLY", lich, 0.6), col, "#8C9A5B")
        _finish(nb, col, rough=0.7, normal=nb.bump(nb.math("ADD", streak, n), 0.25, 0.01), spec=0.3)
    return m


def stem(name, color, tip=None):
    m, nb = _new(name)
    if nb is None:
        return m
    h = nb.attr("vd_height")
    sp, autumn, winter = nb.season()
    col = nb.mix(h, color, tip or color)
    col = nb.mix(nb.math("MULTIPLY", winter, 0.7), col, "#9C8556")
    _finish(nb, col, rough=0.55, translucency=0.2)
    return m


# ---------------------------------------------------------------------------
# ground

def rock(name, dark="#45423D", light="#77736A", moss=0.3):
    m, nb = _new(name)
    if nb is None:
        return m
    tc = nb.node("ShaderNodeTexCoord")
    co = nb.vmath("ADD", nb.out(tc, "Object"), nb.vmath("MULTIPLY", (nb.obj_random()), (17.0, 31.0, 7.0)))
    n = nb.noise(co, 6.0, 10.0, 0.6)
    vor = nb.voronoi(co, 9.0, "F1")
    col = nb.mix(n, dark, light)
    col = nb.mix(nb.math("MULTIPLY", nb.smooth(vor, 0.0, 0.3), 0.3), nb.hsv(col, 0.5, 0.8, 0.7), col)
    geo = nb.node("ShaderNodeNewGeometry")
    up = nb.out(nb.node("ShaderNodeSeparateXYZ", {"Vector": nb.out(geo, "Normal")}), "Z")
    moss_mask = nb.math("MULTIPLY", nb.smooth(nb.math("ADD", up, nb.math("MULTIPLY", nb.noise(co, 3.0), 0.6)),
                                              0.9, 1.2), moss)
    col = nb.mix(moss_mask, col, "#4E6B23")
    _finish(nb, col, rough=0.8, normal=nb.bump(nb.math("ADD", n, nb.math("MULTIPLY", vor, 0.5)), 0.5, 0.01),
            spec=0.3)
    return m


GROUNDS = {
    # name: (soil, grass, dry, grass amount, scale)
    "LAWN": ("#3B2E22", "#30491A", "#6E6038", 0.7),
    "MEADOW": ("#4A3A28", "#536B25", "#8E7B47", 0.55),
    "FOREST": ("#2E241A", "#3D4A1E", "#5C3F23", 0.25),
    "DRY": ("#6B573A", "#6E7134", "#A58E5A", 0.35),
}


def ground(kind):
    """Ground under a patch, so small gaps between plants never look bare."""
    soil, green, dry, amount = GROUNDS[kind]
    m, nb = _new(f"VD Ground {kind.title()}")
    if nb is None:
        return m
    tc = nb.node("ShaderNodeTexCoord")
    co = nb.out(tc, "Object")
    big = nb.noise(co, 0.6, 4.0, 0.55)
    small = nb.noise(co, 14.0, 8.0, 0.6)
    pebbles = nb.smooth(nb.voronoi(co, 40.0, "F1"), 0.0, 0.15)
    g = nb.smooth(nb.math("ADD", big, nb.math("MULTIPLY", small, 0.4)), 1.05 - amount, 1.25 - amount)
    col = nb.mix(g, soil, green)
    col = nb.mix(nb.math("MULTIPLY", nb.smooth(nb.noise(co, 2.5, 6.0), 0.55, 0.7), 0.7), col, dry)
    col = nb.mix(nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, pebbles), nb.math("SUBTRACT", 1.0, g)),
                 col, nb.hsv(soil, 0.5, 0.6, 1.6))
    col = nb.hsv(col, 0.5, 1.0, nb.remap(small, 0, 1, 0.7, 1.2))
    height = nb.math("ADD", small, nb.math("MULTIPLY", pebbles, 0.4))
    _finish(nb, col, rough=0.9, normal=nb.bump(height, 0.5, 0.02), spec=0.2)
    return m
