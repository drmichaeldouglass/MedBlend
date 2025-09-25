"""Shared constants for MedBlend."""

from __future__ import annotations

from pathlib import Path

ADDON_ROOT = Path(__file__).resolve().parent
ASSETS_DIR = ADDON_ROOT / "assets"

__all__ = [
    "ADDON_ROOT",
    "ASSETS_DIR",
]
