# SPDX-License-Identifier: GPL-3.0-or-later
"""Scatter layers: a geometry-nodes modifier that instances a collection on a surface.

Each layer is one ``VD Scatter`` modifier, so layers stack: grass, then
flowers, then trees. The surface itself is kept. Instances are never
realised, so even millions of grass blades stay light in memory.

Controls: density and minimum spacing (Poisson disk), a viewport fraction,
random scale, rotation and tilt, alignment to the surface normal, a slope
limit, a mask (vertex group or any float attribute) and noise-based
patchiness for natural clumping.
"""

import math

import bpy

GROUP = "VD Scatter"
GROUP_VERSION = 1

# name, socket type, default, min, max, subtype, description
INPUTS = [
    ("Collection", "NodeSocketCollection", None, None, None, None, "Collection to scatter; each child is a variant"),
    ("Density", "NodeSocketFloat", 10.0, 0.0, 100000.0, None, "Instances per square metre"),
    ("Min Distance", "NodeSocketFloat", 0.05, 0.0, 100.0, "DISTANCE", "Minimum spacing between instances"),
    ("Viewport Amount", "NodeSocketFloat", 1.0, 0.0, 1.0, "FACTOR", "Share of instances shown in the viewport"),
    ("Seed", "NodeSocketInt", 0, 0, 100000, None, "Random seed"),
    ("Scale", "NodeSocketFloat", 1.0, 0.0, 100.0, None, "Instance scale"),
    ("Scale Random", "NodeSocketFloat", 0.3, 0.0, 1.0, "FACTOR", "Random scale variation"),
    ("Rotation Random", "NodeSocketFloat", 1.0, 0.0, 1.0, "FACTOR", "Random turn around the up axis"),
    ("Tilt", "NodeSocketFloat", 0.15, 0.0, 1.0, "FACTOR", "Random lean, up to 35 degrees"),
    ("Align to Normal", "NodeSocketFloat", 0.0, 0.0, 1.0, "FACTOR", "Follow the surface, not straight up"),
    ("Max Slope", "NodeSocketFloat", math.radians(45.0), 0.0, math.pi, "ANGLE", "No instances on steeper faces"),
    ("Mask", "NodeSocketString", "", None, None, None, "Vertex group or float attribute used as density"),
    ("Invert Mask", "NodeSocketBool", False, None, None, None, "Grow where the mask is low"),
    ("Patchiness", "NodeSocketFloat", 0.0, 0.0, 1.0, "FACTOR", "Grow in natural clumps instead of evenly"),
    ("Patch Size", "NodeSocketFloat", 2.0, 0.01, 1000.0, "DISTANCE", "Size of the clumps"),
]
INPUT_NAMES = [i[0] for i in INPUTS]


def _avail(sockets):
    return [s for s in sockets if not getattr(s, "is_unavailable", not getattr(s, "enabled", True))]


def _sock(sockets, key):
    av = _avail(sockets)
    if isinstance(key, int):
        return av[key]
    for s in av:
        if s.identifier == key or s.name == key:
            return s
    raise KeyError(key)


class GB:
    """Minimal geometry-node builder."""

    def __init__(self, tree):
        self.tree = tree

    def node(self, idname, inputs=None, x=0, y=0, **props):
        n = self.tree.nodes.new(idname)
        n.location = (x, y)
        for k, v in props.items():
            setattr(n, k, v)
        for k, v in (inputs or {}).items():
            s = _sock(n.inputs, k)
            if isinstance(v, bpy.types.NodeSocket):
                self.tree.links.new(v, s)
            else:
                s.default_value = v
        return n

    def math(self, op, a, b=0.0, x=0, y=0):
        n = self.node("ShaderNodeMath", {0: a}, x, y, operation=op)
        if len(_avail(n.inputs)) > 1:
            s = _sock(n.inputs, 1)
            if isinstance(b, bpy.types.NodeSocket):
                self.tree.links.new(b, s)
            else:
                s.default_value = b
        return _sock(n.outputs, 0)

    def rand(self, dtype, lo, hi, seed, x=0, y=0):
        n = self.node("FunctionNodeRandomValue", None, x, y, data_type=dtype)
        for key, v in (("Min", lo), ("Max", hi), ("Seed", seed)):
            s = _sock(n.inputs, key)
            if isinstance(v, bpy.types.NodeSocket):
                self.tree.links.new(v, s)
            else:
                s.default_value = v
        return _sock(n.outputs, 0)


def _build(tree):
    tree.nodes.clear()
    tree.interface.clear()
    tree.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    for name, stype, default, lo, hi, subtype, desc in INPUTS:
        s = tree.interface.new_socket(name, in_out="INPUT", socket_type=stype)
        s.description = desc
        if subtype:
            s.subtype = subtype
        if default is not None:
            s.default_value = default
        if lo is not None:
            s.min_value, s.max_value = lo, hi
    tree.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

    g = GB(tree)
    gi = g.node("NodeGroupInput", x=-1400)
    I = {s.name: s for s in gi.outputs if s.name}  # noqa: E741
    go = g.node("NodeGroupOutput", x=800)

    # density factor: mask * patches * viewport share
    attr = g.node("GeometryNodeInputNamedAttribute", {"Name": I["Mask"]}, -1100, -300, data_type="FLOAT")
    inv = g.math("SUBTRACT", 1.0, _sock(attr.outputs, "Attribute"), -900, -350)
    m_sel = g.node("GeometryNodeSwitch", {"Switch": I["Invert Mask"], "False": _sock(attr.outputs, "Attribute"),
                                          "True": inv}, -700, -300, input_type="FLOAT")
    mask = g.node("GeometryNodeSwitch", {"Switch": _sock(attr.outputs, "Exists"), "False": 1.0,
                                         "True": _sock(m_sel.outputs, 0)}, -500, -300, input_type="FLOAT")

    pos = g.node("GeometryNodeInputPosition", x=-1100, y=-550)
    inv_size = g.math("DIVIDE", 1.0, I["Patch Size"], -1100, -650)
    noise = g.node("ShaderNodeTexNoise", {"Vector": _sock(pos.outputs, 0), "Scale": inv_size, "Detail": 3.0},
                   -900, -550)
    clump = g.node("ShaderNodeMapRange", {"Value": _sock(noise.outputs, "Fac"), "From Min": 0.48, "From Max": 0.58},
                   -700, -550, interpolation_type="SMOOTHSTEP")
    patch = g.node("ShaderNodeMix", {"Factor_Float": I["Patchiness"], "A_Float": 1.0,
                                     "B_Float": _sock(clump.outputs, "Result")}, -500, -550, data_type="FLOAT")

    isvp = g.node("GeometryNodeIsViewport", x=-700, y=-800)
    vp = g.node("GeometryNodeSwitch", {"Switch": _sock(isvp.outputs, 0), "False": 1.0, "True": I["Viewport Amount"]},
                -500, -800, input_type="FLOAT")
    f1 = g.math("MULTIPLY", _sock(mask.outputs, 0), _sock(patch.outputs, "Result_Float"), -300, -400)
    factor = g.math("MULTIPLY", f1, _sock(vp.outputs, 0), -150, -500)

    # slope limit, per face
    nrm = g.node("GeometryNodeInputNormal", x=-1100, y=-100)
    nz = g.node("ShaderNodeSeparateXYZ", {"Vector": _sock(nrm.outputs, "Normal")}, -900, -100)
    cos = g.math("COSINE", I["Max Slope"], 0.0, -900, -200)
    flat = g.node("FunctionNodeCompare", {"A": _sock(nz.outputs, "Z"), "B": cos}, -700, -100,
                  data_type="FLOAT", operation="GREATER_EQUAL")
    # Compare has hidden epsilon sockets; set A/B on the visible float ones
    dist = g.node("GeometryNodeDistributePointsOnFaces", None, 0, 0, distribute_method="POISSON")
    links = tree.links
    links.new(I["Geometry"], _sock(dist.inputs, "Mesh"))
    links.new(_sock(flat.outputs, 0), _sock(dist.inputs, "Selection"))
    links.new(I["Min Distance"], _sock(dist.inputs, "Distance Min"))
    links.new(I["Density"], _sock(dist.inputs, "Density Max"))
    links.new(factor, _sock(dist.inputs, "Density Factor"))
    links.new(I["Seed"], _sock(dist.inputs, "Seed"))

    # rotation: blend between up and the surface normal, then spin and tilt
    up_mix = g.node("ShaderNodeMix", {"Factor_Float": I["Align to Normal"], "A_Vector": (0.0, 0.0, 1.0),
                                      "B_Vector": _sock(dist.outputs, "Normal")}, 200, -300, data_type="VECTOR")
    align = g.node("FunctionNodeAlignRotationToVector", {"Vector": _sock(up_mix.outputs, "Result_Vector")},
                   380, -300, axis="Z")
    seed1 = g.math("ADD", I["Seed"], 11.0, 0, -500)
    seed2 = g.math("ADD", I["Seed"], 23.0, 0, -600)
    seed3 = g.math("ADD", I["Seed"], 37.0, 0, -700)
    seed4 = g.math("ADD", I["Seed"], 51.0, 0, -800)
    spin = g.math("MULTIPLY", g.rand("FLOAT", 0.0, 2 * math.pi, seed1, 200, -500), I["Rotation Random"], 380, -500)
    tilt_amt = g.math("MULTIPLY", I["Tilt"], math.radians(35.0), 200, -900)
    tx = g.math("MULTIPLY", g.rand("FLOAT", -1.0, 1.0, seed2, 200, -600), tilt_amt, 380, -600)
    ty = g.math("MULTIPLY", g.rand("FLOAT", -1.0, 1.0, seed3, 200, -700), tilt_amt, 380, -700)
    euler = g.node("ShaderNodeCombineXYZ", {"X": tx, "Y": ty, "Z": spin}, 560, -600)
    e2r = g.node("FunctionNodeEulerToRotation", {"Euler": _sock(euler.outputs, 0)}, 700, -600)
    rot = g.node("FunctionNodeRotateRotation", {"Rotation": _sock(align.outputs, 0),
                                                "Rotate By": _sock(e2r.outputs, 0)}, 560, -300,
                 rotation_space="LOCAL")

    lo = g.math("SUBTRACT", 1.0, I["Scale Random"], 200, -1000)
    hi = g.math("ADD", 1.0, I["Scale Random"], 200, -1100)
    sc = g.math("MULTIPLY", g.rand("FLOAT", lo, hi, seed4, 380, -1000), I["Scale"], 560, -1000)

    info = g.node("GeometryNodeCollectionInfo", {"Collection": I["Collection"], "Separate Children": True,
                                                 "Reset Children": True}, 200, 200, transform_space="ORIGINAL")
    pick = g.rand("INT", 0, 100000, I["Seed"], 200, 400)
    iop = g.node("GeometryNodeInstanceOnPoints", {"Pick Instance": True}, 600, 0)
    links.new(_sock(dist.outputs, "Points"), _sock(iop.inputs, "Points"))
    links.new(_sock(info.outputs, 0), _sock(iop.inputs, "Instance"))
    links.new(pick, _sock(iop.inputs, "Instance Index"))
    links.new(_sock(rot.outputs, 0), _sock(iop.inputs, "Rotation"))
    links.new(sc, _sock(iop.inputs, "Scale"))

    join = g.node("GeometryNodeJoinGeometry", None, 800, 100)
    links.new(I["Geometry"], join.inputs[0])
    links.new(_sock(iop.outputs, 0), join.inputs[0])
    links.new(_sock(join.outputs, 0), go.inputs[0])
    go.location = (1000, 100)
    tree["vd_version"] = GROUP_VERSION


def scatter_group():
    g = bpy.data.node_groups.get(GROUP)
    if g is None or g.bl_idname != "GeometryNodeTree":
        g = bpy.data.node_groups.new(GROUP, "GeometryNodeTree")
        _build(g)
    return g


def input_ids(group=None):
    group = group or scatter_group()
    return {it.name: it.identifier for it in group.interface.items_tree
            if it.item_type == "SOCKET" and it.in_out == "INPUT"}


def is_layer(mod):
    return mod.type == "NODES" and mod.node_group is not None and mod.node_group.name.startswith(GROUP)


def layers(obj):
    return [m for m in obj.modifiers if is_layer(m)]


def slot(mod, key):
    """(owner, property) holding a modifier input.

    Blender 5 keeps inputs in mod.properties.inputs.<id>.value; earlier
    versions store them as ID properties on the modifier itself.
    """
    ident = input_ids(mod.node_group)[key]
    props = getattr(mod, "properties", None)
    if props is not None and hasattr(props, "inputs"):
        return getattr(props.inputs, ident), "value"
    return mod, f'["{ident}"]'


def get(mod, key):
    owner, prop = slot(mod, key)
    if prop.startswith("["):
        return owner[prop[2:-2]]
    return getattr(owner, prop)


def set_value(mod, key, value):
    owner, prop = slot(mod, key)
    if prop.startswith("["):
        owner[prop[2:-2]] = value
    else:
        setattr(owner, prop, value)
    mod.id_data.update_tag()


def draw_input(layout, mod, key, text=None):
    owner, prop = slot(mod, key)
    layout.prop(owner, prop, text=text if text is not None else key)


def add_layer(obj, collection, name=None, **values):
    """Add a scatter layer to obj. values are keyed by scatter input name."""
    group = scatter_group()
    mod = obj.modifiers.new(name or f"VD {collection.name.removeprefix('VD ')}", "NODES")
    mod.node_group = group
    ids = input_ids(group)
    set_value(mod, "Collection", collection)
    set_value(mod, "Seed", (len(layers(obj)) - 1) * 101)
    for k, v in values.items():
        if k not in ids:
            raise KeyError(f"unknown scatter input {k!r}")
        set_value(mod, k, v)
    return mod
