"""MedBlend Blender extension entry point."""

from __future__ import annotations

from .medblend import bl_info, register, unregister

__all__ = ["bl_info", "register", "unregister"]
