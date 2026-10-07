# SPDX-License-Identifier: GPL-3.0-or-later
"""Ready-made vegetation patches: a ground plane with stacked scatter layers.

A patch is an ordinary mesh with a ground material and VD Scatter
modifiers, so everything stays editable: resize it, sculpt it, paint the
``vd_density`` vertex group, or tweak any layer in the Verdant panel.
"""

import math
import random
from dataclasses import dataclass, field

import bmesh
import bpy
from mathutils import Vector, noise

from . import catalog, materials, scatter

MASK = "vd_density"


@dataclass
class Layer:
    species: object          # species id, or a list of ids / (id, [variants]) for a mix
    values: dict = field(default_factory=dict)
    name: str = ""


@dataclass
class Patch:
    id: str
    label: str
    description: str
    ground: str
    size: float
    relief: float
    layers: list


def L(species, name="", **values):
    return Layer(species, {k.replace("_", " ").title().replace("To", "to"): v for k, v in values.items()}, name)


PATCHES = [
    Patch("LAWN", "Lawn", "Mown lawn with a little clover and the odd daisy", "LAWN", 4.0, 0.02, [
        L("LAWN_GRASS", density=650.0, min_distance=0.028, viewport_amount=0.2),
        L("CLOVER", density=5.0, min_distance=0.12, patchiness=0.8, patch_size=1.2, scale=0.7),
        L([("WILDFLOWERS", [0])], "VD Daisies", density=1.5, min_distance=0.1, patchiness=0.7, scale=0.35),
    ]),
    Patch("MEADOW", "Meadow", "Knee-high grass with seed heads and scattered flowers", "MEADOW", 6.0, 0.06, [
        L("MEADOW_GRASS", density=45.0, min_distance=0.07, viewport_amount=0.35),
        L("LAWN_GRASS", density=180.0, min_distance=0.04, viewport_amount=0.15, scale=1.4),
        L("DRY_GRASS", density=6.0, min_distance=0.15, patchiness=0.6, patch_size=3.0),
        L("WILDFLOWERS", density=6.0, min_distance=0.08, patchiness=0.6, patch_size=2.5),
        L("CLOVER", density=3.0, min_distance=0.12, patchiness=0.7),
    ]),
    Patch("FLOWERS", "Wildflower Field", "Dense, colourful wildflowers in grass", "MEADOW", 6.0, 0.05, [
        L("MEADOW_GRASS", density=30.0, min_distance=0.08, viewport_amount=0.35),
        L("LAWN_GRASS", density=150.0, min_distance=0.04, viewport_amount=0.15, scale=1.3),
        L("WILDFLOWERS", density=40.0, min_distance=0.05, patchiness=0.4, patch_size=1.5, viewport_amount=0.5),
        L("CLOVER", density=4.0, min_distance=0.12, patchiness=0.6),
    ]),
    Patch("FOREST_FLOOR", "Forest Floor", "Ferns, fallen leaves, stones and shrubs", "FOREST", 8.0, 0.15, [
        L("LEAF_LITTER", density=5.0, min_distance=0.3, align_to_normal=1.0, patchiness=0.3),
        L("FERN", density=1.2, min_distance=0.5, patchiness=0.65, patch_size=3.0),
        L("MEADOW_GRASS", density=6.0, min_distance=0.1, patchiness=0.75, patch_size=2.0, viewport_amount=0.5),
        L("STONES", density=0.25, min_distance=0.4, align_to_normal=0.7, tilt=1.0, scale=0.7, scale_random=0.5,
          patchiness=0.5),
        L("SHRUB", density=0.015, min_distance=2.5, scale_random=0.3),
    ]),
    Patch("PARK", "Park", "Lawn with a few broadleaf trees", "LAWN", 24.0, 0.15, [
        L("LAWN_GRASS", density=500.0, min_distance=0.03, viewport_amount=0.05),
        L("CLOVER", density=4.0, min_distance=0.12, patchiness=0.8, viewport_amount=0.5, scale=0.7),
        L(["OAK", "MAPLE", "BIRCH"], "VD Park Trees", density=0.012, min_distance=7.0, scale_random=0.2),
        L("SHRUB", density=0.01, min_distance=3.0, patchiness=0.6),
    ]),
    Patch("CONIFER", "Conifer Forest", "Spruce and pine over ferns and needle-strewn ground", "FOREST", 30.0, 0.5, [
        L(["SPRUCE", "PINE"], "VD Conifers", density=0.03, min_distance=3.5, scale_random=0.25),
        L("FERN", density=0.6, min_distance=0.6, patchiness=0.7, patch_size=4.0, viewport_amount=0.5),
        L("DRY_GRASS", density=3.0, min_distance=0.15, patchiness=0.7, patch_size=3.0, viewport_amount=0.4),
        L("STONES", density=0.15, min_distance=0.5, align_to_normal=0.7, tilt=1.0, scale_random=0.6,
          patchiness=0.5),
    ]),
    Patch("DRY", "Dry Grassland", "Sun-dried grass, tufts and stones", "DRY", 8.0, 0.1, [
        L("DRY_GRASS", density=35.0, min_distance=0.08, viewport_amount=0.35),
        L("MEADOW_GRASS", density=6.0, min_distance=0.1, patchiness=0.7),
        L("TALL_TUFT", density=0.25, min_distance=1.2, patchiness=0.5, scale=0.8),
        L("STONES", density=0.8, min_distance=0.3, align_to_normal=0.7, tilt=1.0, scale_random=0.5,
          patchiness=0.4),
    ]),
]
PATCH_BY_ID = {p.id: p for p in PATCHES}


def _ground_mesh(name, size, shape, relief, seed):
    """A gently uneven grid. Round patches get a wavy edge.

    Writes the ``vd_density`` vertex group, which fades to zero at the edge
    so plants thin out naturally instead of stopping at a hard line.
    """
    res = int(min(max(size * 6, 24), 180))
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=res, y_segments=res, size=size / 2)
    off = Vector((seed * 13.7 % 100, seed * 7.3 % 100, 0.0))
    half = size / 2
    fade = min(max(size * 0.08, 0.15), 2.0)

    def edge_dist(co):
        if shape == "ROUND":
            ang = math.atan2(co.y, co.x)
            wobble = 1.0 + 0.12 * noise.noise(Vector((math.cos(ang), math.sin(ang), 0)) * 1.5 + off)
            return half * 0.95 * wobble - co.length
        return half - max(abs(co.x), abs(co.y))

    if shape == "ROUND":
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if edge_dist(v.co) < -size / res], context="VERTS")
    weights = []
    for v in bm.verts:
        p = Vector((v.co.x, v.co.y, 0.0))
        v.co.z = relief * noise.fractal(p / max(size * 0.35, 1.0) + off, 0.5, 2.0, 4)
        e = edge_dist(p) / fade + 0.25 * noise.noise(p * 2.0 + off)
        weights.append(min(max(e, 0.0), 1.0))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    return me, weights


def add_patch(context, patch_id, size=None, shape="SQUARE", seed=0, location=None):
    p = PATCH_BY_ID[patch_id]
    size = size or p.size
    me, weights = _ground_mesh(f"VD {p.label}", size, shape, p.relief * size / p.size, seed)
    me.materials.append(materials.ground(p.ground))
    obj = bpy.data.objects.new(f"VD {p.label}", me)
    obj["vd_patch"] = p.id
    context.collection.objects.link(obj)
    obj.location = location if location is not None else context.scene.cursor.location
    vg = obj.vertex_groups.new(name=MASK)
    for i, w in enumerate(weights):
        if w > 0:
            vg.add([i], w, "REPLACE")

    rng = random.Random(seed)
    for layer in p.layers:
        if isinstance(layer.species, str):
            coll = catalog.species_collection(layer.species)
            sp = catalog.SPECIES_BY_ID[layer.species]
            values = dict(sp.scatter)
            name = f"VD {sp.label}"
        else:
            coll = catalog.mix_collection(layer.name, layer.species)
            values = {}
            name = layer.name
        values.update(layer.values)
        values["Mask"] = MASK
        mod = scatter.add_layer(obj, coll, name, **values)
        scatter.set_value(mod, "Seed", rng.randint(0, 99999))
    return obj
