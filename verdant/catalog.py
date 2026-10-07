# SPDX-License-Identifier: GPL-3.0-or-later
"""The asset catalog: species, their variants and the library collections.

Assets are generated on demand into collections that live outside the scene:

    Verdant Library            (fake user, never linked to a scene)
      VD Oak                   one collection per species
        VD Oak A               one collection per variant: bark + foliage
        VD Oak B

Scatter layers instance a species collection, so every variant is used.
Generation is seeded, so the same variant always looks the same.
"""

import random
import zlib
from dataclasses import dataclass, field

import bpy

from . import plants, trees

LIBRARY = "Verdant Library"

CATEGORIES = [
    ("GRASS", "Grass", "Lawn, meadow and ornamental grasses", "OUTLINER_OB_CURVES"),
    ("PLANTS", "Plants", "Wildflowers, clover and ferns", "OUTLINER_OB_POINTCLOUD"),
    ("TREES", "Trees", "Broadleaf trees, conifers and shrubs", "OUTLINER_OB_FORCE_FIELD"),
    ("GROUND", "Ground", "Stones and leaf litter", "MESH_ICOSPHERE"),
]


@dataclass
class Species:
    id: str
    label: str
    category: str
    builder: object
    variants: int
    description: str
    # default scatter settings, by scatter input name
    scatter: dict = field(default_factory=dict)
    variant_names: tuple = ()

    def variant_label(self, i):
        if self.variant_names:
            return self.variant_names[i]
        return chr(ord("A") + i)


SPECIES = [
    Species("LAWN_GRASS", "Lawn Grass", "GRASS", plants.lawn_grass, 3,
            "Short, dense, fine-bladed grass for lawns and parks",
            dict(Density=600.0, **{"Min Distance": 0.03, "Viewport Amount": 0.2})),
    Species("MEADOW_GRASS", "Meadow Grass", "GRASS", plants.meadow_grass, 3,
            "Knee-high grass clumps, some with seed heads",
            dict(Density=40.0, **{"Min Distance": 0.08, "Viewport Amount": 0.4})),
    Species("TALL_TUFT", "Tall Tuft", "GRASS", plants.tall_tuft, 2,
            "Large arching ornamental grass with feathery plumes",
            dict(Density=0.6, **{"Min Distance": 0.9})),
    Species("DRY_GRASS", "Dry Grass", "GRASS", plants.dry_grass, 2,
            "Straw-coloured grass for dry fields and verges",
            dict(Density=30.0, **{"Min Distance": 0.08, "Viewport Amount": 0.4})),
    Species("WILDFLOWERS", "Wildflowers", "PLANTS", plants.wildflower, 4,
            "Daisy, poppy, cornflower and buttercup",
            dict(Density=8.0, Patchiness=0.6, **{"Min Distance": 0.08}),
            variant_names=tuple(f[0] for f in plants.FLOWERS)),
    Species("CLOVER", "Clover", "PLANTS", plants.clover, 2,
            "Low trefoil patches; variant B is flowering",
            dict(Density=8.0, Patchiness=0.7, **{"Min Distance": 0.1})),
    Species("FERN", "Fern", "PLANTS", plants.fern, 3,
            "Arching forest ferns",
            dict(Density=1.0, Patchiness=0.6, **{"Min Distance": 0.5})),
    Species("OAK", "Oak", "TREES", trees.tree("OAK"), 3,
            "Broad, spreading oak with lobed leaves",
            dict(Density=0.01, **{"Min Distance": 7.0, "Scale Random": 0.2})),
    Species("BIRCH", "Birch", "TREES", trees.tree("BIRCH"), 3,
            "Slender white-barked birch with drooping twigs",
            dict(Density=0.03, **{"Min Distance": 3.5, "Scale Random": 0.2})),
    Species("MAPLE", "Maple", "TREES", trees.tree("MAPLE"), 3,
            "Rounded maple, red and orange in autumn",
            dict(Density=0.015, **{"Min Distance": 6.0, "Scale Random": 0.2})),
    Species("SPRUCE", "Spruce", "TREES", trees.tree("SPRUCE"), 3,
            "Conical spruce with hanging branchlets",
            dict(Density=0.03, **{"Min Distance": 3.5, "Scale Random": 0.25})),
    Species("PINE", "Scots Pine", "TREES", trees.tree("PINE"), 3,
            "Tall pine with copper upper bark and a high crown",
            dict(Density=0.02, **{"Min Distance": 4.5, "Scale Random": 0.2})),
    Species("SHRUB", "Shrub", "TREES", trees.tree("SHRUB"), 3,
            "Rounded multi-stem bush",
            dict(Density=0.15, **{"Min Distance": 1.6, "Scale Random": 0.3})),
    Species("STONES", "Stones", "GROUND", plants.stone, 3,
            "Pebbles, stones and small rocks",
            dict(Density=0.5, Patchiness=0.5, **{"Min Distance": 0.3, "Align to Normal": 0.7,
                                                   "Tilt": 1.0, "Scale Random": 0.5})),
    Species("LEAF_LITTER", "Leaf Litter", "GROUND", plants.leaf_litter, 3,
            "Fallen leaves and twigs",
            dict(Density=3.0, Patchiness=0.4, **{"Min Distance": 0.35, "Align to Normal": 1.0})),
]
SPECIES_BY_ID = {s.id: s for s in SPECIES}
CATEGORY_ICON = {c[0]: c[3] for c in CATEGORIES}


def library():
    lib = bpy.data.collections.get(LIBRARY)
    if lib is None:
        lib = bpy.data.collections.new(LIBRARY)
        lib.use_fake_user = True
        lib["vd_library"] = True
    return lib


def _species_name(sp):
    return f"VD {sp.label}"


def variant_name(sp, i):
    return f"VD {sp.label} {sp.variant_label(i)}"


def species_collection(sp_id):
    """The species collection with every variant generated."""
    sp = SPECIES_BY_ID[sp_id]
    lib = library()
    coll = bpy.data.collections.get(_species_name(sp))
    if coll is None:
        coll = bpy.data.collections.new(_species_name(sp))
        coll["vd_species"] = sp.id
    if coll.name not in lib.children:
        lib.children.link(coll)
    for i in range(sp.variants):
        v = variant_collection(sp_id, i)
        if v.name not in coll.children:
            coll.children.link(v)
    return coll


def variant_collection(sp_id, i):
    sp = SPECIES_BY_ID[sp_id]
    name = variant_name(sp, i)
    coll = bpy.data.collections.get(name)
    if coll is not None and coll.objects:
        return coll
    if coll is None:
        coll = bpy.data.collections.new(name)
        coll["vd_species"] = sp.id
        coll["vd_variant"] = i
    seed = zlib.crc32(sp.id.encode()) + i * 7919
    parts = sp.builder(random.Random(seed), i)
    for part in parts:
        part_name, mesh = part[0], part[1]
        flags = part[2] if len(part) > 2 else {}
        obj = bpy.data.objects.new(f"{name} {part_name.title()}", mesh)
        obj["vd_species"] = sp.id
        for k in flags:
            obj[f"vd_{k}"] = True
        coll.objects.link(obj)
    apply_season(coll.objects)
    return coll


def mix_collection(name, entries):
    """A collection whose children are the variant collections of several species.

    entries: species ids, or (species id, [variant indices]).
    """
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        library().children.link(coll)
    for e in entries:
        sp_id, idx = (e, None) if isinstance(e, str) else e
        sp = SPECIES_BY_ID[sp_id]
        species_collection(sp_id)
        for i in (idx if idx is not None else range(sp.variants)):
            v = variant_collection(sp_id, i)
            if v.name not in coll.children:
                coll.children.link(v)
    return coll


def current_season():
    scene = bpy.context.scene
    return getattr(getattr(scene, "verdant", None), "season", "SUMMER")


def apply_season(objects=None, season=None):
    """Hide deciduous foliage in winter."""
    season = season or current_season()
    winter = season == "WINTER"
    objs = objects if objects is not None else bpy.data.objects
    for o in objs:
        if o.get("vd_deciduous"):
            o.hide_render = winter
            o.hide_viewport = winter


def generated_species():
    return [s for s in SPECIES if bpy.data.collections.get(_species_name(s))]
