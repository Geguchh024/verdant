# SPDX-License-Identifier: GPL-3.0-or-later
"""Scene settings: library browser state, patch options and the season."""

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, PointerProperty

from . import catalog, materials, patches, thumbs

# Blender needs the enum item lists to stay alive while it shows them
_items_cache = {}


def _species_items(self, context):
    items = []
    for i, sp in enumerate(s for s in catalog.SPECIES if s.category == self.category):
        icon = thumbs.icon(f"SP_{sp.id}") or catalog.CATEGORY_ICON[sp.category]
        items.append((sp.id, sp.label, sp.description, icon, i))
    _items_cache["species"] = items
    return items


def _variant_items(self, context):
    sp = catalog.SPECIES_BY_ID.get(self.species)
    items = [("RANDOM", "Mixed", "Scatter every variant, or place a random one", "MOD_NOISE", 0)]
    if sp:
        for i in range(sp.variants):
            items.append((str(i), sp.variant_label(i), f"Variant {sp.variant_label(i)} only", "NONE", i + 1))
    _items_cache["variants"] = items
    return items


def _patch_items(self, context):
    items = [(p.id, p.label, p.description, thumbs.icon(f"PATCH_{p.id}") or "MESH_GRID", i)
             for i, p in enumerate(patches.PATCHES)]
    _items_cache["patches"] = items
    return items


def _season_update(self, context):
    materials.set_season(self.season)
    catalog.apply_season(season=self.season)


def _category_update(self, context):
    first = next(s for s in catalog.SPECIES if s.category == self.category)
    self.species = first.id


def _patch_update(self, context):
    self.patch_size = patches.PATCH_BY_ID[self.patch].size


class VD_SceneProps(bpy.types.PropertyGroup):
    category: EnumProperty(name="Category", items=[c[:4] + (i,) for i, c in enumerate(catalog.CATEGORIES)],
                           update=_category_update)
    species: EnumProperty(name="Species", items=_species_items)
    variant: EnumProperty(name="Variant", items=_variant_items)
    patch: EnumProperty(name="Patch", items=_patch_items, update=_patch_update)
    patch_size: FloatProperty(name="Size", default=4.0, min=0.5, soft_max=200.0, unit="LENGTH",
                              description="Width of the patch")
    patch_shape: EnumProperty(name="Shape", items=[
        ("SQUARE", "Square", "Square patch, tiles with others", "MESH_PLANE", 0),
        ("ROUND", "Round", "Round patch with a natural wavy edge", "MESH_CIRCLE", 1),
    ])
    place_spacing: FloatProperty(name="Paint Spacing", default=0.0, min=0.0, soft_max=10.0, unit="LENGTH",
                                 description="Distance between plants while dragging. 0 uses the species default")
    place_scale_random: FloatProperty(name="Scale Random", default=0.25, min=0.0, max=1.0,
                                      description="Random size variation of placed plants")
    place_align: BoolProperty(name="Align to Surface", default=False,
                              description="Tilt placed plants to follow the surface instead of growing straight up")
    patch_seed: IntProperty(name="Seed", default=0, min=0, description="Varies the ground shape and plant layout")
    season: EnumProperty(name="Season", items=[
        ("SPRING", "Spring", "Fresh light greens", 0),
        ("SUMMER", "Summer", "Full green", 1),
        ("AUTUMN", "Autumn", "Autumn colours and drier grass", 2),
        ("WINTER", "Winter", "Bare broadleaf trees and dry grass", 3),
    ], default="SUMMER", update=_season_update)


def register():
    bpy.utils.register_class(VD_SceneProps)
    bpy.types.Scene.verdant = PointerProperty(type=VD_SceneProps)


def unregister():
    del bpy.types.Scene.verdant
    bpy.utils.unregister_class(VD_SceneProps)
