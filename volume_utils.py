"""Helpers for writing volume data to VDB."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import bpy

from .ui_utils import show_message_box


def resolve_temp_path(target_name: str) -> Path:
    base_dir = Path(bpy.app.tempdir or Path.cwd())
    return base_dir / target_name


def write_vdb_volume(array, spacing: Sequence[float], target_name: str) -> Optional[Path]:
    try:
        import openvdb
    except Exception as exc:
        show_message_box(f"openvdb is not available: {exc}", "Missing Dependency", "ERROR")
        return None

    try:
        grid = openvdb.FloatGrid()
        grid.copyFromArray(array.astype(float))
        grid.transform = openvdb.createLinearTransform(
            [
                [spacing[0] / 1000.0, 0, 0, 0],
                [0, spacing[1] / 1000.0, 0, 0],
                [0, 0, spacing[2] / 1000.0, 0],
                [0, 0, 0, 1],
            ]
        )
        grid.gridClass = openvdb.GridClass.FOG_VOLUME
        grid.name = "density"

        output_path = resolve_temp_path(target_name)
        openvdb.write(str(output_path), grid)
        bpy.ops.object.volume_import(filepath=str(output_path), files=[])
        return output_path
    except Exception as exc:
        show_message_box(f"Failed to create VDB volume: {exc}", "Error", "ERROR")
        return None
