# SPDX-License-Identifier: GPL-3.0-or-later
"""Verdant: procedural grass, plants and trees with scattering and ready-made patches."""

from . import ops, props, thumbs, ui


def register():
    props.register()
    ops.register()
    ui.register()


def unregister():
    ui.unregister()
    thumbs.clear()
    ops.unregister()
    props.unregister()
