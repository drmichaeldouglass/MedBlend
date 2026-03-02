"""CT/MR import helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
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

    result = write_vdb_volume(ct_volume, spacing_values, "CT.vdb")
    if not result:
        return False
    _output_path, ct_object = result

    try:
        orientation = np.asarray(_image_orientation, dtype=float)
        row_dir = orientation[:3]
        col_dir = orientation[3:]
        normal_dir = np.cross(row_dir, col_dir)
        normal_norm = float(np.linalg.norm(normal_dir))
        if normal_norm > 0:
            normal_dir = normal_dir / normal_norm
        else:
            normal_dir = np.asarray([0.0, 0.0, 1.0], dtype=float)

        # Array axis 0 is flipped in extract_dicom_data, so the imported array origin
        # corresponds to the final source slice position.
        slice_positions = np.asarray(_slice_position, dtype=float)
        if slice_positions.ndim == 2 and slice_positions.shape[1] == 3 and len(slice_positions) > 0:
            array_origin = slice_positions[-1]
        else:
            array_origin = np.asarray(_image_origin, dtype=float)

        row_spacing = float(spacing[0])
        col_spacing = float(spacing[1])
        slice_step = float(slice_spacing)

        # Basis columns map [slice, row, col] index steps to patient-space millimetres.
        slice_axis = -normal_dir * slice_step
        row_axis = col_dir * row_spacing
        col_axis = row_dir * col_spacing
        basis = np.column_stack((slice_axis, row_axis, col_axis))

        frame_uid = getattr(selected_file, "FrameOfReferenceUID", "")
        ct_object["medblend_is_ct"] = True
        if frame_uid:
            ct_object["medblend_frame_of_reference_uid"] = str(frame_uid)
        ct_object["medblend_ct_origin_mm"] = [float(v) for v in array_origin]
        ct_object["medblend_ct_basis_mm"] = [float(v) for v in basis.reshape(-1)]
        ct_object["medblend_ct_spacing_mm"] = [float(v) for v in spacing_values]
    except Exception:
        # Metadata is best-effort and should not block import.
        pass

    apply_dicom_shader("Image Material")
    return True
