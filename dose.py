"""Dose import helpers."""

from __future__ import annotations

from pathlib import Path

import bpy
import pydicom

from .dicom_util import is_dose_file
from .node_groups import apply_dicom_shader
from .ui_utils import show_message_box
from .volume_utils import align_object_to_ct_frame, set_object_patient_transform, write_vdb_volume


def _find_ct_anchor(frame_uid: str):
    ct_candidates = [obj for obj in bpy.data.objects if bool(obj.get("medblend_is_ct"))]
    if frame_uid:
        ct_candidates = [obj for obj in ct_candidates if obj.get("medblend_frame_of_reference_uid", "") == frame_uid]
    if not ct_candidates:
        return None
    return ct_candidates[-1]


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
    row_spacing = float(pixel_spacing[0]) if len(pixel_spacing) > 0 else 1.0
    col_spacing = float(pixel_spacing[1]) if len(pixel_spacing) > 1 else 1.0

    offsets = np.asarray(getattr(dataset, "GridFrameOffsetVector", []), dtype=float)
    signed_slice_step = None
    if offsets.size >= 2:
        offset_deltas = np.diff(offsets)
        non_zero = np.abs(offset_deltas) > 1e-6
        if np.any(non_zero):
            signed_slice_step = float(np.median(offset_deltas[non_zero]))
            slice_spacing = float(abs(signed_slice_step))
        else:
            slice_spacing = float(getattr(dataset, "SliceThickness", 1.0))
    else:
        slice_spacing = float(getattr(dataset, "SliceThickness", 1.0))
    if slice_spacing <= 0:
        slice_spacing = 1.0
    if signed_slice_step is None:
        signed_slice_step = slice_spacing

    dose_resolution = [slice_spacing, row_spacing, col_spacing]

    dose_matrix = np.asarray(pixel_data, dtype=float)
    dose_grid_scaling = float(getattr(dataset, "DoseGridScaling", 1.0) or 1.0)
    if dose_grid_scaling <= 0:
        show_message_box("DoseGridScaling is invalid; expected a positive value.", "Error", "ERROR")
        return False
    dose_matrix *= dose_grid_scaling
    if dose_matrix.ndim == 2:
        dose_matrix = dose_matrix[np.newaxis, ...]

    result = write_vdb_volume(dose_matrix, dose_resolution, "dose.vdb")
    if not result:
        return False
    _output_path, dose_object = result

    try:
        dose_origin = np.asarray(getattr(dataset, "ImagePositionPatient", [0.0, 0.0, 0.0]), dtype=float)
        orientation = np.asarray(getattr(dataset, "ImageOrientationPatient", [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]), dtype=float)
        row_dir = orientation[:3]
        col_dir = orientation[3:]
        normal_dir = np.cross(row_dir, col_dir)
        normal_norm = float(np.linalg.norm(normal_dir))
        if normal_norm > 0:
            normal_dir = normal_dir / normal_norm
        else:
            normal_dir = np.asarray([0.0, 0.0, 1.0], dtype=float)

        # Keep origin anchored to ImagePositionPatient (frame 0).
        # GridFrameOffsetVector is still used for slice direction/spacing.

        row_axis_dir = col_dir
        col_axis_dir = row_dir
        slice_axis_dir = normal_dir * (1.0 if signed_slice_step >= 0 else -1.0)
        dose_basis = np.column_stack(
            (
                slice_axis_dir * slice_spacing,
                row_axis_dir * row_spacing,
                col_axis_dir * col_spacing,
            )
        )

        # Align dose into the same scene frame used by imported CT data.
        frame_uid = str(getattr(dataset, "FrameOfReferenceUID", ""))
        ct_obj = _find_ct_anchor(frame_uid)
        aligned = False
        if ct_obj:
            aligned = align_object_to_ct_frame(
                dose_object,
                ct_obj,
                dose_origin,
                dose_basis,
                dose_resolution,
            )
        if not aligned:
            set_object_patient_transform(
                dose_object,
                dose_origin,
                slice_axis_dir,
                row_axis_dir,
                col_axis_dir,
            )
    except Exception:
        # Best-effort spatial alignment only; fallback keeps legacy behaviour.
        pass

    apply_dicom_shader("Dose Material")
    return True
