"""RT structure set import helpers."""

from __future__ import annotations

from pathlib import Path

import pydicom

from .dicom_util import is_structure_file
from .node_groups import apply_dicom_shader
from .ui_utils import show_message_box
from .volume_utils import write_vdb_volume


def load_structures(file_path: Path) -> bool:
    structure_file_path = Path(file_path)
    directory_path = structure_file_path.parent

    try:
        from platipy.dicom.io.rtstruct_to_nifti import read_dicom_image, transform_point_set_from_dicom_struct
    except Exception as exc:
        show_message_box(f"platipy is required to load RT structures: {exc}", "Missing Dependency", "ERROR")
        return False

    try:
        import SimpleITK as sitk
    except Exception as exc:
        show_message_box(f"SimpleITK is required to load RT structures: {exc}", "Missing Dependency", "ERROR")
        return False

    try:
        dicom_image = read_dicom_image(directory_path)
    except Exception as exc:
        show_message_box(f"Failed to read reference images: {exc}", "Error", "ERROR")
        return False

    voxel_resolution = dicom_image.GetSpacing()

    try:
        dicom_structure = pydicom.dcmread(structure_file_path)
    except Exception as exc:
        show_message_box(f"Unable to read structure file: {exc}", "Error", "ERROR")
        return False

    if not is_structure_file(dicom_structure):
        show_message_box("Selected file is not an RT Structure Set.", "Error", "ERROR")
        return False

    try:
        struct_masks, struct_names = transform_point_set_from_dicom_struct(dicom_image, dicom_structure)
    except Exception:
        show_message_box(
            "Something is wrong with the structure file. Please check the file and try again.",
            "Error",
            "ERROR",
        )
        return False

    for mask, name in zip(struct_masks, struct_names):
        numpy_image = sitk.GetArrayFromImage(mask)
        spacing = (
            float(voxel_resolution[2]),
            float(voxel_resolution[0]),
            float(voxel_resolution[1]),
        )
        output_path = write_vdb_volume(numpy_image.astype(float), spacing, f"{name}.vdb")
        if not output_path:
            return False
        apply_dicom_shader("Structure Material")

    return True
