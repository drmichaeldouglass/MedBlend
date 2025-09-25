"""MedBlend Blender extension package."""

from __future__ import annotations

import bpy

from .operators.load_ct import MEDBLEND_OT_load_ct
from .operators.load_dose import MEDBLEND_OT_load_dose
from .operators.load_proton import MEDBLEND_OT_load_proton
from .operators.load_structures import MEDBLEND_OT_load_structures
from .ui.panel import MEDBLEND_PT_panel

bl_info = {
    "name": "MedBlend",
    "description": "Medical DICOM and proton therapy visualisation tools",
    "author": "Michael Douglass",
    "version": (2, 0, 0),
    "blender": (4, 5, 0),
    "location": "3D Viewport > Sidebar > Medical",
    "doc_url": "https://github.com/drmichaeldouglass/MedBlend",
    "support": "COMMUNITY",
    "category": "3D View",
}

_CLASSES = (
    MEDBLEND_PT_panel,
    MEDBLEND_OT_load_ct,
    MEDBLEND_OT_load_dose,
    MEDBLEND_OT_load_structures,
    MEDBLEND_OT_load_proton,
)


def register() -> None:
    """Register MedBlend classes with Blender."""
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister() -> None:
    """Unregister MedBlend classes from Blender."""
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)


__all__ = [
    "register",
    "unregister",
]
