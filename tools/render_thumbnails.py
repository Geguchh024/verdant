# SPDX-License-Identifier: GPL-3.0-or-later
"""Render preview thumbnails for every species and patch.

    blender -b --factory-startup --python tools/render_thumbnails.py [-- [--res N] [--out DIR] [NAME ...]]

Writes PNGs into verdant/thumbs (SP_<ID>.png and PATCH_<ID>.png). NAME
filters by species or patch id. --res and --out are handy for larger
review renders.
"""

import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import verdant  # noqa: E402

verdant.register()
from verdant import catalog, patches, thumbs  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
RES = 256
OUT = thumbs.DIR
SEASON = "SUMMER"
ENGINE = "CYCLES"
names = []
i = 0
while i < len(argv):
    if argv[i] == "--res":
        RES = int(argv[i + 1])
        i += 2
    elif argv[i] == "--out":
        OUT = argv[i + 1]
        i += 2
    elif argv[i] == "--engine":
        ENGINE = argv[i + 1].upper()
        i += 2
    elif argv[i] == "--season":
        SEASON = argv[i + 1]
        i += 2
    else:
        names.append(argv[i].upper())
        i += 1


def wanted(key):
    return not names or any(n in key for n in names)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.verdant.season = SEASON
    sc.render.engine = "CYCLES" if ENGINE == "CYCLES" else "BLENDER_EEVEE"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 48
    sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 6
    sc.cycles.transparent_max_bounces = 8
    sc.render.resolution_x = sc.render.resolution_y = RES
    sc.render.resolution_percentage = 100
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = -0.2

    world = bpy.data.worlds.new("sky")
    sc.world = world
    nt = world.node_tree
    sky = nt.nodes.new("ShaderNodeTexSky")
    if hasattr(sky, "sun_disc"):
        sky.sun_disc = False  # the sun lamp lights the scene; a second, much brighter sun blows out highlights
    if hasattr(sky, "sun_elevation"):
        sky.sun_elevation = math.radians(45)
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.12
    nt.links.new(sky.outputs[0], bg.inputs["Color"])

    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy = 5.0
    sun.angle = math.radians(2.0)
    sun.color = (1.0, 0.95, 0.88)
    so = bpy.data.objects.new("sun", sun)
    sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(45), 0, math.radians(35))
    return sc


def camera(sc, target, distance, height_deg=18.0, lens=50.0, azimuth=-35.0):
    cam = bpy.data.cameras.new("cam")
    cam.lens = lens
    cam.clip_end = 1000
    co = bpy.data.objects.new("cam", cam)
    sc.collection.objects.link(co)
    az, el = math.radians(azimuth), math.radians(height_deg)
    co.location = target + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * distance
    co.rotation_euler = (target - co.location).to_track_quat("-Z", "Y").to_euler()
    sc.camera = co


def ground(sc, size, kind):
    bpy.ops.mesh.primitive_plane_add(size=size)
    g = bpy.context.object
    g.data.materials.append(verdant.materials.ground(kind))
    return g


def render(sc, key):
    os.makedirs(OUT, exist_ok=True)
    sc.render.filepath = os.path.join(OUT, key + ".png")
    bpy.ops.render.render(write_still=True)
    print("wrote", sc.render.filepath)


GROUND_FOR = {"GRASS": "MEADOW", "PLANTS": "MEADOW", "TREES": "LAWN", "GROUND": "FOREST"}

for sp in catalog.SPECIES:
    key = f"SP_{sp.id}"
    if not wanted(key):
        continue
    sc = reset()
    coll = catalog.variant_collection(sp.id, 0)
    inst = bpy.data.objects.new("asset", None)
    inst.instance_type = "COLLECTION"
    inst.instance_collection = coll
    sc.collection.objects.link(inst)
    lo = Vector((min(v[i] for o in coll.objects for v in o.bound_box) for i in range(3)))
    hi = Vector((max(v[i] for o in coll.objects for v in o.bound_box) for i in range(3)))
    size = max(hi - lo)
    ground(sc, size * 6, GROUND_FOR[sp.category])
    centre = (lo + hi) / 2
    camera(sc, centre, size * 2.0, 12.0 if sp.category == "TREES" else 25.0)
    render(sc, key)

for p in patches.PATCHES:
    key = f"PATCH_{p.id}"
    if not wanted(key):
        continue
    sc = reset()
    obj = patches.add_patch(bpy.context, p.id, location=(0, 0, 0))
    sc.render.film_transparent = True
    trees = p.size > 15
    camera(sc, Vector((0, 0, p.size * (0.15 if trees else 0.0))), p.size * (1.7 if trees else 1.05),
           28.0 if trees else 35.0, 40.0)
    render(sc, key)
