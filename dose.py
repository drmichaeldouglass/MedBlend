"""Dose import helpers."""

from __future__ import annotations

from pathlib import Path

import pydicom

from .dicom_util import is_dose_file
from .node_groups import apply_dicom_shader
from .ui_utils import show_message_box
from .volume_utils import write_vdb_volume


def load_dose(file_path: Path) -> bool:
    try:
        dataset = pydicom.dcmread(file_path)
    except Exception as exc:
        show_message_box(f"Unable to read file: {exc}", "Error", "ERROR")
        return False

    if not is_dose_file(dataset):
        show_message_box("Selected file is not an RT Dose file.", "Error", "ERROR")
        return False

    try:
        import numpy as np
    except Exception as exc:
        show_message_box(f"numpy is required to load dose data: {exc}", "Missing Dependency", "ERROR")
        return False

    try:
        pixel_data = dataset.pixel_array
    except Exception as exc:
        show_message_box(f"Unable to parse dose grid: {exc}", "Error", "ERROR")
        return False

    pixel_spacing = getattr(dataset, "PixelSpacing", [1.0, 1.0])
    dose_resolution = [
        float(pixel_spacing[0]),
        float(pixel_spacing[1]),
        float(getattr(dataset, "SliceThickness", 1.0)),
    ]

    dose_matrix = np.asarray(pixel_data)
    dose_matrix = np.flipud(dose_matrix)

    output_path = write_vdb_volume(dose_matrix, dose_resolution, "dose.vdb")
    if not output_path:
        return False

    apply_dicom_shader("Dose Material")
    return True
