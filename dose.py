"""Dose import helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom

from .dicom_util import float_or, is_dose_file, positive_float_or
from .node_groups import apply_dicom_shader
from .ui_utils import show_message_box
from .volume_utils import (
    align_object_to_ct_frame,
    find_ct_anchor,
    set_object_patient_transform,
    write_vdb_volume,
)


def dose_grid_spacing(dataset: pydicom.Dataset) -> tuple[list[float], float]:
    """Return ``([slice, row, col] spacing in mm, signed slice step)``.

    Every scalar goes through ``float_or``/``positive_float_or``: DICOM Type 2
    attributes such as ``SliceThickness`` are routinely present but empty, and
    a bare ``float(None)`` would raise straight out of the operator as an
    unhandled traceback. The sign of the slice step is kept separately because
    ``GridFrameOffsetVector`` may run opposite to the slice normal.
    """

    pixel_spacing = getattr(dataset, "PixelSpacing", None) or [1.0, 1.0]
    row_spacing = positive_float_or(pixel_spacing[0] if len(pixel_spacing) > 0 else None, 1.0)
    col_spacing = positive_float_or(pixel_spacing[1] if len(pixel_spacing) > 1 else None, 1.0)

    raw_offsets = getattr(dataset, "GridFrameOffsetVector", None) or []
    try:
        offsets = np.asarray([float(value) for value in raw_offsets], dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("GridFrameOffsetVector contains a non-numeric value.") from exc

    if offsets.size and not np.all(np.isfinite(offsets)):
        raise ValueError("GridFrameOffsetVector contains a non-finite value.")

    signed_slice_step = None
    slice_spacing = positive_float_or(getattr(dataset, "SliceThickness", None), 1.0)
    if offsets.size >= 2:
        offset_deltas = np.diff(offsets)
        if np.any(np.abs(offset_deltas) <= 1e-6):
            raise ValueError("GridFrameOffsetVector contains duplicate dose plane positions.")
        if np.any(np.sign(offset_deltas) != np.sign(offset_deltas[0])):
            raise ValueError("GridFrameOffsetVector is not monotonic.")

        signed_slice_step = float(np.median(offset_deltas))
        if not np.allclose(offset_deltas, signed_slice_step, rtol=1e-4, atol=1e-3):
            spacing_text = ", ".join(f"{value:.3g}" for value in offset_deltas[:6])
            if len(offset_deltas) > 6:
                spacing_text += ", ..."
            raise ValueError(
                "Dose plane spacing is non-uniform "
                f"({spacing_text} mm). MedBlend cannot represent non-uniform "
                "GridFrameOffsetVector positions in a linearly transformed VDB volume."
            )
        slice_spacing = float(abs(signed_slice_step))
    if signed_slice_step is None:
        signed_slice_step = slice_spacing

    return [slice_spacing, row_spacing, col_spacing], signed_slice_step


def dose_grid_scaling(dataset: pydicom.Dataset) -> float:
    """Return a finite, positive DoseGridScaling value.

    DoseGridScaling is required whenever RT Dose pixel data is present. A
    fabricated default can turn stored integers into plausible-looking but
    numerically incorrect doses, so malformed files are rejected instead.
    """

    raw_scaling = getattr(dataset, "DoseGridScaling", None)
    try:
        scaling = float(raw_scaling)
    except (TypeError, ValueError) as exc:
        raise ValueError("DoseGridScaling is missing or non-numeric.") from exc
    if not np.isfinite(scaling) or scaling <= 0:
        raise ValueError("DoseGridScaling must be finite and greater than zero.")
    return scaling


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
        pixel_data = dataset.pixel_array
    except Exception as exc:
        show_message_box(f"Unable to parse dose grid: {exc}", "Error", "ERROR")
        return False

    try:
        dose_resolution, signed_slice_step = dose_grid_spacing(dataset)
        dose_grid_scale = dose_grid_scaling(dataset)
    except ValueError as exc:
        show_message_box(str(exc), "Error", "ERROR")
        return False
    slice_spacing, row_spacing, col_spacing = dose_resolution

    dose_matrix = np.asarray(pixel_data, dtype=np.float32)
    dose_matrix = dose_matrix * np.float32(dose_grid_scale)
    if dose_matrix.ndim == 2:
        dose_matrix = dose_matrix[np.newaxis, ...]
    elif dose_matrix.ndim != 3:
        show_message_box(
            f"Unsupported dose grid with {dose_matrix.ndim} dimensions; expected a 2D or 3D grid.",
            "Error",
            "ERROR",
        )
        return False

    raw_offsets = getattr(dataset, "GridFrameOffsetVector", None) or []
    if dose_matrix.shape[0] > 1 and len(raw_offsets) != dose_matrix.shape[0]:
        show_message_box(
            "GridFrameOffsetVector must contain one position for every dose plane "
            f"({len(raw_offsets)} offsets for {dose_matrix.shape[0]} planes).",
            "Error",
            "ERROR",
        )
        return False

    result = write_vdb_volume(dose_matrix, dose_resolution, "dose.vdb")
    if not result:
        return False
    _output_path, dose_object = result

    placement_error = None
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
        ct_obj = find_ct_anchor(frame_uid)
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
    except Exception as exc:
        # The grid is already imported; keep it rather than discarding a usable
        # dose distribution, but do not let a misplaced dose look co-registered.
        placement_error = str(exc)

    if placement_error:
        show_message_box(
            "The dose grid was imported but could not be placed in DICOM patient "
            f"coordinates ({placement_error}). It sits at the scene origin and "
            "will not line up with the image volume.",
            "Warning",
            "ERROR",
        )

    dose_object["medblend_dose_max"] = float(np.max(dose_matrix)) if dose_matrix.size else 0.0
    dose_object["medblend_dose_units"] = str(getattr(dataset, "DoseUnits", "") or "")

    apply_dicom_shader("Dose Material", dose_object)
    return True
