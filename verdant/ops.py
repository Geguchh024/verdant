# SPDX-License-Identifier: GPL-3.0-or-later
"""Operators: place assets, scatter them, add patches, manage layers."""

import random

import bpy
from bpy.props import IntProperty, StringProperty
from mathutils import Quaternion, Vector

from . import catalog, patches, scatter


def _chosen_collection(vp):
    """The species collection, or a single variant's collection."""
    if vp.variant == "RANDOM":
        return catalog.species_collection(vp.species)
    catalog.species_collection(vp.species)
    return catalog.variant_collection(vp.species, int(vp.variant))


def _mesh_targets(context):
    objs = [o for o in context.selected_objects if o.type == "MESH"]
    if not objs and context.active_object and context.active_object.type == "MESH":
        objs = [context.active_object]
    return objs


def _instance(context, sp_id, i):
    """A collection instance of one variant, linked to the active collection."""
    coll = catalog.variant_collection(sp_id, i)
    obj = bpy.data.objects.new(coll.name, None)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = coll
    obj.empty_display_size = 0.3
    obj["vd_placed"] = sp_id
    context.collection.objects.link(obj)
    return obj


def _view3d_under_mouse(context, event):
    """(region, region_3d) of the 3D viewport under the mouse, or (None, None)."""
    for area in context.window.screen.areas:
        if area.type != "VIEW_3D":
            continue
        for region in area.regions:
            if (region.type == "WINDOW" and region.x <= event.mouse_x < region.x + region.width
                    and region.y <= event.mouse_y < region.y + region.height):
                return region, area.spaces.active.region_3d
    return None, None


def place_plant(context, sp_id, variant, location, normal, rng, scale_random=0.25, align=False):
    """Place one plant at a surface point. variant < 0 picks a random variant."""
    sp = catalog.SPECIES_BY_ID[sp_id]
    i = rng.randrange(sp.variants) if variant < 0 else variant
    obj = _instance(context, sp.id, i)
    obj.location = location
    obj.scale = [rng.uniform(1.0 - scale_random, 1.0 + scale_random)] * 3
    obj.rotation_euler = surface_rotation(normal, rng.uniform(0.0, 6.283), align or sp.category == "GROUND")
    return obj


def surface_rotation(normal, spin, align):
    """Euler rotation: a turn around the up axis, optionally tilted onto the surface normal."""
    q = Quaternion((0.0, 0.0, 1.0), spin)
    if align:
        q = Vector((0.0, 0.0, 1.0)).rotation_difference(normal) @ q
    return q.to_euler()


class VD_OT_place(bpy.types.Operator):
    """Click on any surface to plant the chosen species there, or drag to paint several.
Right-click or Esc to finish"""
    bl_idname = "vd.place"
    bl_label = "Place on Surface"
    bl_options = {"REGISTER", "UNDO"}

    NAVIGATION = {"MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM",
                  "NDOF_MOTION"}

    def invoke(self, context, event):
        vp = context.scene.verdant
        sp = catalog.SPECIES_BY_ID[vp.species]
        catalog.species_collection(sp.id)  # generate up front so clicks are instant
        self.rng = random.Random()
        self.painting = False
        self.last = None
        self.count = 0
        self.spacing = vp.place_spacing or max(sp.scatter.get("Min Distance", 0.1) * 1.5, 0.05)
        context.window_manager.modal_handler_add(self)
        context.window.cursor_modal_set("PAINT_CROSS")
        context.workspace.status_text_set(
            f"Placing {sp.label}: click or drag on a surface  ·  Right-click / Esc to finish")
        return {"RUNNING_MODAL"}

    def _hit(self, context, event):
        from bpy_extras import view3d_utils
        region, rv3d = _view3d_under_mouse(context, event)
        if region is None:
            return None
        co = (event.mouse_x - region.x, event.mouse_y - region.y)
        origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, co)
        direction = view3d_utils.region_2d_to_vector_3d(region, rv3d, co)
        hit, loc, normal, _i, _obj, _m = context.scene.ray_cast(context.evaluated_depsgraph_get(), origin, direction)
        return (loc, normal) if hit else None

    def place(self, context, loc, normal):
        vp = context.scene.verdant
        variant = -1 if vp.variant == "RANDOM" else int(vp.variant)
        obj = place_plant(context, vp.species, variant, loc, normal, self.rng, vp.place_scale_random, vp.place_align)
        obj.select_set(True)
        self.last = loc.copy()
        self.count += 1
        return obj

    def modal(self, context, event):
        if event.type in self.NAVIGATION or (event.type == "LEFTMOUSE" and event.alt):
            return {"PASS_THROUGH"}
        if event.type in {"RIGHTMOUSE", "ESC"} and event.value == "PRESS":
            return self._finish(context)
        if event.type == "LEFTMOUSE":
            if event.value == "PRESS":
                hit = self._hit(context, event)
                if hit is None:  # not over a viewport (e.g. the sidebar): let the click through
                    return {"PASS_THROUGH"}
                self.painting = True
                self.place(context, *hit)
            elif event.value == "RELEASE":
                self.painting = False
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE" and self.painting:
            hit = self._hit(context, event)
            if hit and (self.last is None or (hit[0] - self.last).length >= self.spacing):
                self.place(context, *hit)
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}

    def _finish(self, context):
        context.window.cursor_modal_restore()
        context.workspace.status_text_set(None)
        self.report({"INFO"}, f"Placed {self.count} plant(s)")
        return {"FINISHED"} if self.count else {"CANCELLED"}


class VD_OT_add_asset(bpy.types.Operator):
    """Place the chosen plant at the 3D cursor"""
    bl_idname = "vd.add_asset"
    bl_label = "Add at Cursor"
    bl_options = {"REGISTER", "UNDO"}

    seed: IntProperty(name="Seed", default=0, description="Picks a variant when Random is chosen")

    def execute(self, context):
        vp = context.scene.verdant
        sp = catalog.SPECIES_BY_ID[vp.species]
        catalog.species_collection(sp.id)
        if vp.variant == "RANDOM":
            i = random.Random(self.seed + len(bpy.data.objects)).randrange(sp.variants)
        else:
            i = int(vp.variant)
        obj = _instance(context, sp.id, i)
        obj.location = context.scene.cursor.location
        obj.rotation_euler.z = random.Random(self.seed + i).uniform(0, 6.283)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


class VD_OT_scatter(bpy.types.Operator):
    """Scatter the chosen plant over the selected meshes as a new layer"""
    bl_idname = "vd.scatter"
    bl_label = "Scatter on Selected"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return bool(_mesh_targets(context))

    def execute(self, context):
        vp = context.scene.verdant
        sp = catalog.SPECIES_BY_ID[vp.species]
        coll = _chosen_collection(vp)
        for obj in _mesh_targets(context):
            values = dict(sp.scatter)
            if "vd_density" in obj.vertex_groups:
                values["Mask"] = "vd_density"
            scatter.add_layer(obj, coll, f"VD {sp.label}", **values)
        return {"FINISHED"}


class VD_OT_scatter_objects(bpy.types.Operator):
    """Scatter the selected objects over the active mesh (your own assets)"""
    bl_idname = "vd.scatter_objects"
    bl_label = "Scatter Selected Objects on Active"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        a = context.active_object
        return a is not None and a.type == "MESH" and len(context.selected_objects) > 1

    def execute(self, context):
        target = context.active_object
        sources = [o for o in context.selected_objects if o is not target]
        coll = bpy.data.collections.new(f"VD Custom {sources[0].name}")
        catalog.library().children.link(coll)
        for o in sources:
            coll.objects.link(o)
        scatter.add_layer(target, coll, f"VD {sources[0].name}", Density=2.0, **{"Min Distance": 0.2})
        self.report({"INFO"}, f"Scattering {len(sources)} object(s); each is placed by its origin")
        return {"FINISHED"}


class VD_OT_add_patch(bpy.types.Operator):
    """Add a ready-made vegetation patch at the 3D cursor"""
    bl_idname = "vd.add_patch"
    bl_label = "Add Patch"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        vp = context.scene.verdant
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        obj = patches.add_patch(context, vp.patch, vp.patch_size, vp.patch_shape, vp.patch_seed)
        for o in context.selected_objects:
            o.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        return {"FINISHED"}


class VD_OT_remove_layer(bpy.types.Operator):
    """Remove this scatter layer"""
    bl_idname = "vd.remove_layer"
    bl_label = "Remove Layer"
    bl_options = {"REGISTER", "UNDO"}

    modifier: StringProperty()

    def execute(self, context):
        obj = context.active_object
        mod = obj.modifiers.get(self.modifier) if obj else None
        if mod is None:
            return {"CANCELLED"}
        obj.modifiers.remove(mod)
        return {"FINISHED"}


class VD_OT_reseed_layer(bpy.types.Operator):
    """Pick a new random layout for this layer"""
    bl_idname = "vd.reseed_layer"
    bl_label = "New Seed"
    bl_options = {"REGISTER", "UNDO"}

    modifier: StringProperty()

    def execute(self, context):
        obj = context.active_object
        mod = obj.modifiers.get(self.modifier) if obj else None
        if mod is None:
            return {"CANCELLED"}
        scatter.set_value(mod, "Seed", random.randint(0, 99999))
        return {"FINISHED"}


classes = (VD_OT_place, VD_OT_add_asset, VD_OT_scatter, VD_OT_scatter_objects, VD_OT_add_patch, VD_OT_remove_layer,
           VD_OT_reseed_layer)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
