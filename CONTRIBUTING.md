# Contributing

Thanks for helping. Below is everything you need to work on the add-on.

## Project layout

```
verdant/                   the add-on (this folder is what gets zipped)
  __init__.py              registration
  blender_manifest.toml    extension manifest (id, version, license)
  meshkit.py               MeshBuilder: tubes, blades, leaves, needles, sprays
  materials.py             procedural shaders and the shared VD Season group
  plants.py                grass, flowers, clover, fern, stones, leaf litter
  trees.py                 branching tree generator and species presets
  catalog.py               species list, library collections, seasons
  scatter.py               the VD Scatter geometry-node group and layer helpers
  patches.py               ready-made patches (ground + layers)
  props.py / ops.py / ui.py   properties, operators, sidebar panels
  thumbs.py, thumbs/       preview thumbnails
tools/render_thumbnails.py renders the preview thumbnails
tests/run_tests.py         headless test suite
docs/images/               images used in the README
```

## Running from source

Point Blender at the repo instead of installing the zip. Add the repo root to
*Preferences → File Paths → Script Directories*, or symlink `verdant` into your
user extensions folder. Then enable the add-on.

## Tests

```
blender -b --factory-startup --python tests/run_tests.py
```

The script exits with a non-zero status if any test fails. Please run it before
opening a pull request.

## Building the zip

Run this from the repo root:

```
blender --command extension build --source-dir verdant --output-dir dist
```

## Adding a species

1. Write a generator `fn(rng, variant)` in `plants.py`. For a tree, add a preset
   to `trees.SPECIES` instead.
   - Use only the seeded `rng` so a variant always looks the same.
   - Return a list of `(part_name, mesh)` or `(part_name, mesh, flags)` tuples.
   - Use the flag `deciduous` for foliage that should disappear in winter.
   - Build meshes with `MeshBuilder` so the shaders get `vd_height` and `vd_rand`.
2. Register it in `catalog.SPECIES` with a category, a variant count and default
   scatter values.
3. Render its thumbnail:
   `blender -b --factory-startup --python tools/render_thumbnails.py -- SP_YOUR_ID`

## Tree presets

Each level in `trees.SPECIES[...]["levels"]` controls one branching order:

- `n`: children per parent.
- `len`: length relative to the parent.
- `down`: angle away from the parent, in degrees.
- `curve`: bend along the branch; positive bends upward.
- `gravity`: droop.
- `whorl`: branches per ring. Use it for conifers.
- `planar`: spread children sideways, like spruce branchlets.

Foliage uses one of three kinds: `leaves` (an outline function), `spray` (a
conifer shoot) or `needles`.

Watch the vertex count. Trees are instanced, so 150k–350k vertices per variant
is fine.

## Changing the scatter group

The `VD Scatter` group is built once per file and reused. Files that already
contain the group keep their old copy. When you change the group:

- Bump `GROUP_VERSION` in `scatter.py`. It is stored on the group, so a future
  upgrade step can find outdated copies.
- Only add inputs at the end. Never rename or reorder existing inputs, because
  users' layers store values by input.
