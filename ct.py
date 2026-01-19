"""CT/MR import helpers."""

from __future__ import annotations

from pathlib import Path

import pydicom

from .dicom_util import (
    check_dicom_image_type,
    extract_dicom_data,
    filter_by_series_uid,
    load_dicom_images,
    sort_by_instance_number,
)
from .node_groups import apply_dicom_shader
from .ui_utils import show_message_box
from .volume_utils import write_vdb_volume


def load_ct_series(file_path: Path) -> bool:
    try:
        selected_file = pydicom.dcmread(file_path)
    except Exception as exc:
        show_message_box(f"Unable to read file: {exc}", "Error", "ERROR")
        return False

    if not check_dicom_image_type(selected_file):
        show_message_box("Selected file is not a CT or MR DICOM.", "Error", "ERROR")
        return False

    series_uid = getattr(selected_file, "SeriesInstanceUID", None)
    if not series_uid:
        show_message_box("Missing SeriesInstanceUID on selected DICOM.", "Error", "ERROR")
        return False

    images = load_dicom_images(file_path.parent)
    filtered_images = filter_by_series_uid(images, series_uid)
    sorted_images = sort_by_instance_number(filtered_images)

    try:
        (
            ct_volume,
            spacing,
            _slice_position,
            slice_spacing,
            _image_origin,
            _image_orientation,
            _image_columns,
        ) = extract_dicom_data(sorted_images)
    except Exception as exc:
        show_message_box(str(exc), "Error", "ERROR")
        return False

    slice_spacing = slice_spacing or 1.0
    spacing_values = (float(slice_spacing), float(spacing[0]), float(spacing[1]))

    output_path = write_vdb_volume(ct_volume, spacing_values, "CT.vdb")
    if not output_path:
        return False

    apply_dicom_shader("Image Material")
    return True
