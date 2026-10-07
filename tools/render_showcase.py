# SPDX-License-Identifier: GPL-3.0-or-later
"""Render showcase images: a wide landscape and one 16:9 render per patch.

    blender -b --factory-startup --python tools/render_showcase.py -- [hero] [patches] [--samples N] [--scale F]

Writes docs/images/showcase/hero.png (2400 x 1200) and
docs/images/showcase/patches/<id>.png (1280 x 720, transparent background). Lighting comes from the
Open Sky add-on when the open-sky repo sits next to this one; otherwise a
plain sky texture is used. Renders on the GPU when one is available.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
OPEN_SKY = os.path.abspath(os.path.join(ROOT, "..", "open-sky"))
if os.path.isdir(OPEN_SKY):
    sys.path.insert(0, OPEN_SKY)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import verdant  # noqa: E402

verdant.register()
from verdant import catalog, patches, scatter  # noqa: E402

try:
    import open_sky  # noqa: E402

    open_sky.register()
    from open_sky import rig  # noqa: E402
except ImportError:
    rig = None

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
SAMPLES = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 128
SCALE = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 1.0
jobs = [a for a in argv if a in ("hero", "patches")] or ["hero", "patches"]
only = [a.upper() for a in argv if a not in ("hero", "patches") and not a.startswith("--")
        and not a.replace(".", "").isdigit()]
OUT = os.path.join(ROOT, "docs", "images", "showcase")


def reset(sun_el, sun_az, haze=0.3, clouds=0.0):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for kind in ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI"):
        try:
            prefs.compute_device_type = kind
            prefs.get_devices()
            for d in prefs.devices:
                d.use = True
            break
        except TypeError:
            continue
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "GPU"
    sc.cycles.samples = SAMPLES
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6
    sc.cycles.transparent_max_bounces = 8
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    if rig is not None:
        world = rig.create(sc)
        node = rig.sky_node(world)
        for k, v in {"Haze Density": haze, "Cloud Coverage": clouds, "Ground": 0.0}.items():
            if k in node.inputs:
                node.inputs[k].default_value = v
        rig.set_sun_angles(rig.sun_object(world), math.radians(sun_el), math.radians(sun_az))
    else:
        world = bpy.data.worlds.new("sky")
        sc.world = world
        sky = world.node_tree.nodes.new("ShaderNodeTexSky")
        world.node_tree.links.new(sky.outputs[0], world.node_tree.nodes["Background"].inputs[0])
        world.node_tree.nodes["Background"].inputs[1].default_value = 0.3
        sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
        sun.data.energy = 4.0
        sun.rotation_euler = (math.radians(90 - sun_el), 0, math.radians(180 - sun_az))
        sc.collection.objects.link(sun)
    return sc


def camera(sc, loc, target, lens):
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    cam.data.lens = lens
    cam.data.clip_end = 2000
    sc.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam


def plant(sp_id, variant, loc, rot=0.0, scale=1.0):
    coll = catalog.variant_collection(sp_id, variant)
    catalog.species_collection(sp_id)
    o = bpy.data.objects.new(coll.name, None)
    o.instance_type = "COLLECTION"
    o.instance_collection = coll
    o.location = loc
    o.rotation_euler.z = rot
    o.scale = (scale,) * 3
    bpy.context.scene.collection.objects.link(o)


def save(sc, path, w, h):
    sc.render.resolution_x, sc.render.resolution_y = int(w * SCALE), int(h * SCALE)
    sc.render.resolution_percentage = 100
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("wrote", path)


def hero():
    """Low over a wildflower field at golden hour, birches and an oak behind, conifers far off."""
    sc = reset(sun_el=13.0, sun_az=-70.0, haze=0.4)
    ctx = bpy.context
    patches.add_patch(ctx, "FLOWERS", size=34.0, seed=3, location=(0, 19.5, 0))
    far = patches.add_patch(ctx, "MEADOW", size=120.0, seed=5, location=(0, 90, -0.25))
    # the far meadow's finest layers are too small to see from here
    for mod in scatter.layers(far):
        name = scatter.get(mod, "Collection").name
        if name == "VD Lawn Grass":
            scatter.set_value(mod, "Density", 25.0)
        elif name == "VD Meadow Grass":
            scatter.set_value(mod, "Density", 18.0)
    for x, y, v, s in ((-13, 40, 0, 1.0), (-4, 50, 2, 0.95), (19, 47, 1, 1.05)):
        plant("OAK", v, (x, y, -0.2), x * 0.3, s)
    for x, y, v in ((7, 27, 0), (10.5, 30, 1), (4.5, 33, 2), (13, 35, 0), (-21, 31, 1)):
        plant("BIRCH", v, (x, y, -0.15), x * 0.7, 0.95)
    for x, y, v in ((30, 58, 0), (-30, 56, 1), (-42, 66, 2)):
        plant("MAPLE", v, (x, y, -0.2), x, 1.0)
    for i in range(30):
        x = -80 + i * 5.5 + (i * 7919 % 11) * 0.4
        y = 105 + (i * 104729 % 17)
        plant("SPRUCE" if i % 3 else "PINE", i % 3, (x, y, -0.3), i * 1.3, 0.85 + (i % 5) * 0.08)
    for x, y, v in ((-5, 24, 0), (17, 25, 2), (-15, 28, 1)):
        plant("SHRUB", v, (x, y, -0.1), x, 1.1)
    camera(sc, (0.8, 0.0, 1.15), (0.0, 30.0, 3.2), 30.0)
    sc.view_settings.exposure = 0.3
    save(sc, os.path.join(OUT, "hero.png"), 2400, 1200)


def patch_shots():
    for p in patches.PATCHES:
        if only and p.id not in only:
            continue
        sc = reset(sun_el=38.0, sun_az=-50.0, haze=0.2)
        sc.render.film_transparent = True  # composited onto a backdrop by the website's sync script
        sc.view_settings.exposure = 0.5
        patches.add_patch(bpy.context, p.id, seed=1, location=(0, 0, 0))
        s = p.size
        if s > 15:  # tree patches: step back and look over the canopy
            camera(sc, (0.7 * s, -1.75 * s, 1.15 * s), (0, 0, 0.12 * s), 40.0)
        else:
            camera(sc, (0.6 * s, -1.3 * s, 1.05 * s), (0, 0.03 * s, -0.04 * s), 40.0)
        save(sc, os.path.join(OUT, "patches", p.id.lower().replace("_", "-") + ".png"), 1280, 720)


if "hero" in jobs:
    hero()
if "patches" in jobs:
    patch_shots()
