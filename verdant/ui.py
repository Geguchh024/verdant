# SPDX-License-Identifier: GPL-3.0-or-later
"""Sidebar panels: Library, Patches, Scatter Layers and Season."""

import bpy

from . import catalog, scatter

# inputs shown for every layer; the rest live under "More"
MAIN = ("Density", "Viewport Amount", "Scale", "Patchiness")
MORE = ("Min Distance", "Scale Random", "Rotation Random", "Tilt", "Align to Normal", "Max Slope",
        "Patch Size", "Mask", "Invert Mask", "Seed")


class VD_PT_base:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Verdant"


class VD_PT_library(VD_PT_base, bpy.types.Panel):
    bl_label = "Library"
    bl_idname = "VD_PT_library"

    def draw(self, context):
        vp = context.scene.verdant
        col = self.layout.column()
        col.row(align=True).prop(vp, "category", expand=True, icon_only=False)
        col.template_icon_view(vp, "species", show_labels=True, scale=7.0, scale_popup=5.0)
        sp = catalog.SPECIES_BY_ID.get(vp.species)
        if sp:
            box = col.box()
            box.label(text=sp.label, icon=catalog.CATEGORY_ICON[sp.category])
            box.label(text=sp.description)
        col.prop(vp, "variant")
        row = col.row()
        row.scale_y = 1.4
        row.operator("vd.place", icon="BRUSH_DATA")
        sub = col.column(align=True)
        sub.prop(vp, "place_spacing")
        sub.prop(vp, "place_scale_random", slider=True)
        sub.prop(vp, "place_align")
        row = col.row(align=True)
        row.operator("vd.add_asset", icon="PIVOT_CURSOR")
        row.operator("vd.scatter", icon="STICKY_UVS_DISABLE")
        col.separator()
        col.operator("vd.scatter_objects", icon="OUTLINER_OB_GROUP_INSTANCE")


class VD_PT_patches(VD_PT_base, bpy.types.Panel):
    bl_label = "Patches"
    bl_idname = "VD_PT_patches"

    def draw(self, context):
        vp = context.scene.verdant
        col = self.layout.column()
        col.template_icon_view(vp, "patch", show_labels=True, scale=7.0, scale_popup=5.0)
        col.prop(vp, "patch_size")
        col.row().prop(vp, "patch_shape", expand=True)
        col.prop(vp, "patch_seed")
        row = col.row()
        row.scale_y = 1.3
        row.operator("vd.add_patch", icon="MESH_GRID")


class VD_PT_layers(VD_PT_base, bpy.types.Panel):
    bl_label = "Scatter Layers"
    bl_idname = "VD_PT_layers"

    def draw(self, context):
        obj = context.active_object
        layout = self.layout
        mods = scatter.layers(obj) if obj else []
        if not mods:
            layout.label(text="Select an object with scatter layers", icon="INFO")
            return
        for mod in mods:
            box = layout.box()
            head = box.row(align=True)
            head.prop(mod, "show_expanded", text="", emboss=False,
                      icon="DOWNARROW_HLT" if mod.show_expanded else "RIGHTARROW")
            head.prop(mod, "name", text="")
            head.prop(mod, "show_viewport", text="")
            head.prop(mod, "show_render", text="")
            op = head.operator("vd.reseed_layer", text="", icon="FILE_REFRESH")
            op.modifier = mod.name
            op = head.operator("vd.remove_layer", text="", icon="X")
            op.modifier = mod.name
            if not mod.show_expanded:
                continue
            col = box.column(align=True)
            scatter.draw_input(col, mod, "Collection")
            for key in MAIN:
                scatter.draw_input(col, mod, key)
            sub = box.column(align=True)
            for key in MORE:
                if key == "Mask":
                    owner, prop = scatter.slot(mod, key)
                    sub.prop_search(owner, prop, obj, "vertex_groups", text="Mask")
                else:
                    scatter.draw_input(sub, mod, key)


class VD_PT_season(VD_PT_base, bpy.types.Panel):
    bl_label = "Season"
    bl_idname = "VD_PT_season"

    def draw(self, context):
        self.layout.row().prop(context.scene.verdant, "season", expand=True)


classes = (VD_PT_library, VD_PT_patches, VD_PT_layers, VD_PT_season)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
