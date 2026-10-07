# SPDX-License-Identifier: GPL-3.0-or-later
"""Headless test suite.

    blender -b --factory-startup --python tests/run_tests.py

Exits with a non-zero status when any test fails.
"""

import os
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import bpy  # noqa: E402

import verdant  # noqa: E402

verdant.register()
from verdant import catalog, materials, patches, scatter  # noqa: E402

TMP = tempfile.mkdtemp(prefix="vd_tests_")
results = []


def test(fn):
    results.append(fn)
    return fn


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def instances_of(obj):
    """(source object, world location) for each instance obj generates.

    Depsgraph instances are only valid while iterating, so copy what we need.
    """
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return [(i.object.original, i.matrix_world.translation.copy()) for i in dg.object_instances
            if i.is_instance and i.parent and i.parent.original == obj]


def plane(size=4.0):
    bpy.ops.mesh.primitive_plane_add(size=size)
    return bpy.context.object


# ---------------------------------------------------------------------------

@test
def every_variant_builds():
    reset()
    for sp in catalog.SPECIES:
        coll = catalog.species_collection(sp.id)
        assert len(coll.children) == sp.variants, sp.id
        for child in coll.children:
            assert child.objects, f"{child.name} is empty"
            for o in child.objects:
                assert len(o.data.polygons) > 0, o.name
                assert o.data.materials and all(o.data.materials), o.name


@test
def generation_is_deterministic():
    reset()
    counts = [len(o.data.vertices) for o in catalog.variant_collection("OAK", 1).objects]
    reset()
    assert counts == [len(o.data.vertices) for o in catalog.variant_collection("OAK", 1).objects]


@test
def library_survives_save_and_reload():
    reset()
    obj = plane()
    scatter.add_layer(obj, catalog.species_collection("LAWN_GRASS"), Density=50.0)
    path = os.path.join(TMP, "lib.blend")
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert catalog.LIBRARY in bpy.data.collections
    assert len(instances_of(bpy.data.objects["Plane"])) > 0


@test
def scatter_layer_respects_inputs():
    reset()
    obj = plane(4.0)
    mod = scatter.add_layer(obj, catalog.species_collection("LAWN_GRASS"), Density=100.0,
                            **{"Min Distance": 0.0})
    n = len(instances_of(obj))
    assert 1200 < n < 2000, n  # 16 m2 at 100 per m2
    scatter.set_value(mod, "Viewport Amount", 0.5)
    n2 = len(instances_of(obj))
    assert 0.35 * n < n2 < 0.65 * n, (n, n2)
    assert scatter.get(mod, "Density") == 100.0


@test
def slope_limit():
    reset()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    cube = bpy.context.object
    scatter.add_layer(cube, catalog.species_collection("STONES"), Density=20.0, **{"Min Distance": 0.0})
    insts = instances_of(cube)
    assert insts, "nothing on the top face"
    # only the top face (z = 1) is flat enough at the default 45 degree limit
    assert all(loc.z > 0.99 for _o, loc in insts)


@test
def mask_and_invert():
    reset()
    obj = plane(4.0)
    vg = obj.vertex_groups.new(name="m")
    vg.add([0, 1, 2, 3], 0.0, "REPLACE")
    mod = scatter.add_layer(obj, catalog.species_collection("CLOVER"), Density=50.0, Mask="m")
    assert len(instances_of(obj)) == 0
    scatter.set_value(mod, "Invert Mask", True)
    assert len(instances_of(obj)) > 0


@test
def stacked_layers():
    reset()
    obj = plane(6.0)
    scatter.add_layer(obj, catalog.species_collection("MEADOW_GRASS"), Density=10.0)
    scatter.add_layer(obj, catalog.species_collection("STONES"), Density=2.0)
    assert len(scatter.layers(obj)) == 2
    names = {o.name.split(" ")[1] for o, _loc in instances_of(obj)}
    assert {"Meadow", "Stones"} <= names, names


@test
def every_patch_builds_and_scatters():
    reset()
    for i, p in enumerate(patches.PATCHES):
        obj = patches.add_patch(bpy.context, p.id, size=min(p.size, 8.0), shape="ROUND" if i % 2 else "SQUARE",
                                location=(i * 20.0, 0, 0))
        assert len(scatter.layers(obj)) == len(p.layers), p.id
        assert patches.MASK in obj.vertex_groups
        assert len(instances_of(obj)) > 0, p.id


@test
def operators_run():
    reset()
    vp = bpy.context.scene.verdant
    for cat, *_ in catalog.CATEGORIES:
        vp.category = cat
        assert catalog.SPECIES_BY_ID[vp.species].category == cat
    vp.category = "PLANTS"
    vp.species = "WILDFLOWERS"
    vp.variant = "1"
    assert bpy.ops.vd.add_asset() == {"FINISHED"}
    assert bpy.context.object.instance_collection.name.endswith("Poppy")
    obj = plane()
    assert bpy.ops.vd.scatter() == {"FINISHED"}
    mod, = scatter.layers(obj)
    assert scatter.get(mod, "Collection").name.endswith("Poppy")
    assert bpy.ops.vd.reseed_layer(modifier=mod.name) == {"FINISHED"}
    assert bpy.ops.vd.remove_layer(modifier=mod.name) == {"FINISHED"}
    assert not scatter.layers(obj)
    vp.patch = "MEADOW"
    assert vp.patch_size == patches.PATCH_BY_ID["MEADOW"].size
    vp.patch_size = 3.0
    assert bpy.ops.vd.add_patch() == {"FINISHED"}
    assert bpy.context.object.get("vd_patch") == "MEADOW"


@test
def place_on_surface():
    import random

    from mathutils import Vector

    from verdant import ops
    reset()
    rng = random.Random(3)
    up = ops.place_plant(bpy.context, "LAWN_GRASS", -1, Vector((1, 2, 0.5)), Vector((0, 0, 1)), rng)
    assert up.instance_collection.name.startswith("VD Lawn Grass")
    assert tuple(up.location) == (1, 2, 0.5)
    slope = Vector((0.0, 0.6, 0.8))
    # grass stays upright on a slope unless aligned
    g = ops.place_plant(bpy.context, "MEADOW_GRASS", 0, Vector(), slope, rng)
    assert abs((g.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized().z - 1.0) < 1e-4
    g2 = ops.place_plant(bpy.context, "MEADOW_GRASS", 0, Vector(), slope, rng, align=True)
    bpy.context.view_layer.update()
    assert ((g2.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized() - slope).length < 1e-3
    # ground debris always follows the surface
    s = ops.place_plant(bpy.context, "STONES", 1, Vector(), slope, rng)
    bpy.context.view_layer.update()
    assert ((s.matrix_world.to_3x3() @ Vector((0, 0, 1))).normalized() - slope).length < 1e-3


@test
def ui_icons_exist():
    import re
    valid = set(bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items.keys())
    used = set()
    for name in ("catalog.py", "props.py", "ui.py", "ops.py"):
        with open(os.path.join(ROOT, "verdant", name), encoding="utf-8") as f:
            src = f.read()
        used |= set(re.findall(r'icon="([A-Z0-9_]+)"', src))
        used |= set(re.findall(r'"([A-Z][A-Z0-9_]+)", \d+\)', src))  # enum item icons
    used |= {c[3] for c in catalog.CATEGORIES}
    bad = sorted(i for i in used if i not in valid and i not in {"SQUARE", "ROUND"})
    assert not bad, bad


@test
def panels_draw():
    """Draw every panel against a fake layout so a bad icon or property name fails here."""
    from verdant import ui

    class Fake:
        def __getattr__(self, name):
            def call(*args, **kw):
                icon = kw.get("icon")
                if isinstance(icon, str) and icon not in valid:
                    raise ValueError(f"bad icon {icon}")
                return Fake()
            return call

    valid = set(bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items.keys())
    reset()
    patches.add_patch(bpy.context, "LAWN", size=2.0)
    for cls in ui.classes:
        cls.draw(type("P", (), {"layout": Fake()})(), bpy.context)


@test
def scatter_own_objects():
    reset()
    bpy.ops.mesh.primitive_cube_add(size=0.2, location=(5, 5, 5))
    cube = bpy.context.object
    target = plane(4.0)
    cube.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    assert bpy.ops.vd.scatter_objects() == {"FINISHED"}
    insts = instances_of(target)
    assert insts and all(o == cube for o, _loc in insts)
    # Reset Children: instances sit on the surface, not offset by the source location
    assert all(abs(loc.z) < 0.5 for _o, loc in insts)


@test
def seasons():
    reset()
    leaves = [o for o in catalog.variant_collection("BIRCH", 0).objects if o.get("vd_deciduous")]
    needles = [o for o in catalog.variant_collection("SPRUCE", 0).objects if o.get("vd_evergreen")]
    assert leaves and needles
    obj = plane(20.0)
    scatter.add_layer(obj, catalog.species_collection("BIRCH"), Density=0.05, **{"Min Distance": 2.0})
    summer = len(instances_of(obj))
    sc = bpy.context.scene
    sc.verdant.season = "WINTER"
    assert all(o.hide_render and o.hide_viewport for o in leaves)
    assert not any(o.hide_render for o in needles)
    winter = len(instances_of(obj))
    assert winter < summer, (summer, winter)  # bare trees in winter
    g = bpy.data.node_groups[materials.SEASON_GROUP]
    assert g.nodes["Winter"].outputs[0].default_value == 1.0
    sc.verdant.season = "AUTUMN"
    assert not any(o.hide_render for o in leaves)
    assert g.nodes["Autumn"].outputs[0].default_value == 1.0
    sc.verdant.season = "WINTER"
    oak = catalog.variant_collection("OAK", 2)  # new assets pick up the current season
    assert all(o.hide_render for o in oak.objects if o.get("vd_deciduous"))


@test
def materials_have_no_images():
    reset()
    for sp in catalog.SPECIES:
        catalog.variant_collection(sp.id, 0)
    for kind in materials.GROUNDS:
        materials.ground(kind)
    for m in bpy.data.materials:
        if m.get("vd"):
            assert not any(n.bl_idname == "ShaderNodeTexImage" for n in m.node_tree.nodes), m.name


@test
def unregister_and_register_again():
    verdant.unregister()
    verdant.register()
    assert hasattr(bpy.types.Scene, "verdant")


# ---------------------------------------------------------------------------

def main():
    failed = 0
    for fn in results:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(results) - failed}/{len(results)} passed")
    sys.exit(1 if failed else 0)


main()
