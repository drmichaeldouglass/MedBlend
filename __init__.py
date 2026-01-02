"""MedBlend - DICOM import tools for Blender."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, Sequence

import bpy
import bpy.utils.previews
import numpy as np
import openvdb
import pydicom
import SimpleITK as sitk
from bpy_extras.io_utils import ImportHelper

from .dicom_util import (
    check_dicom_image_type,
    extract_dicom_data,
    filter_by_series_uid,
    is_dose_file,
    is_structure_file,
    load_dicom_images,
    sort_by_instance_number,
)
from .node_groups import apply_dicom_shader, apply_proton_spots_geo_nodes
from .blender_utils import add_data_fields, create_object
from .proton import is_proton_plan
from platipy.dicom.io.rtstruct_to_nifti import (
    read_dicom_image,
    transform_point_set_from_dicom_struct,
)


bl_info = {
    "name": "MedBlend",
    "author": "Michael Douglass",
    "version": (2, 0, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Medical",
    "description": "Import DICOM images, dose, structures, and proton plans",
    "category": "3D View",
}


addon_keymaps = {}
_icons = None


def show_message_box(message: str = "", title: str = "Message", icon: str = "INFO") -> None:
    def draw(self, _context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def _resolve_temp_path(target_name: str) -> Path:
    base_dir = Path(bpy.app.tempdir or Path.cwd())
    return base_dir / target_name


def _write_vdb_volume(array: np.ndarray, spacing: Sequence[float], target_name: str) -> Path:
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

    output_path = _resolve_temp_path(target_name)
    openvdb.write(str(output_path), grid)
    bpy.ops.object.volume_import(filepath=str(output_path), files=[])
    return output_path


def _load_ct_series(file_path: Path) -> bool:
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
    except ValueError as exc:
        show_message_box(str(exc), "Error", "ERROR")
        return False

    slice_spacing = slice_spacing or 1.0
    spacing_values = (float(slice_spacing), float(spacing[0]), float(spacing[1]))
    _write_vdb_volume(ct_volume, spacing_values, "CT.vdb")
    apply_dicom_shader("Image Material")
    return True


def _load_dose(file_path: Path) -> bool:
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

    pixel_spacing = getattr(dataset, "PixelSpacing", [1.0, 1.0])
    dose_resolution = [
        float(pixel_spacing[0]),
        float(pixel_spacing[1]),
        float(getattr(dataset, "SliceThickness", 1.0)),
    ]

    dose_matrix = np.asarray(pixel_data)
    dose_matrix = np.flipud(dose_matrix)

    _write_vdb_volume(dose_matrix, dose_resolution, "dose.vdb")
    apply_dicom_shader("Dose Material")
    return True


def _load_structures(file_path: Path) -> bool:
    structure_file_path = Path(file_path)
    directory_path = structure_file_path.parent

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
        _write_vdb_volume(numpy_image.astype(float), spacing, f"{name}.vdb")
        apply_dicom_shader("Structure Material")

    return True


def _load_proton_plan(file_path: Path) -> bool:
    try:
        dataset = pydicom.dcmread(file_path)
    except Exception as exc:
        show_message_box(f"Unable to read file: {exc}", "Error", "ERROR")
        return False

    if not is_proton_plan(dataset):
        show_message_box("Selected file is not an RT Ion proton plan.", "Error", "ERROR")
        return False

    for beam_index, beam in enumerate(dataset.IonBeamSequence):
        control_points = beam.IonControlPointSequence
        num_control_points = len(control_points)

        x_vals: list[float] = []
        y_vals: list[float] = []
        energies: list[float] = []
        spot_weights: list[float] = []

        for idx in range(0, num_control_points, 2):
            positions = control_points[idx].ScanSpotPositionMap
            weights = control_points[idx].ScanSpotMetersetWeights
            for pos_index in range(0, len(positions), 2):
                x_vals.append(positions[pos_index] / 1000.0)
                y_vals.append(positions[pos_index + 1] / 1000.0)
                energies.append(float(control_points[idx].NominalBeamEnergy) / 1000.0)
                weight_index = int(pos_index / 2)
                spot_weights.append(weights[weight_index])

        mesh = bpy.data.meshes.new(name=f"proton_spots_{beam_index}")
        data_fields = ["spot_x", "spot_y", "spot_E", "spot_weight"]
        add_data_fields(mesh, data_fields)

        count = len(spot_weights)
        mesh.vertices.add(count)

        for row in range(count):
            mesh.attributes["spot_x"].data[row].value = x_vals[row]
            mesh.attributes["spot_y"].data[row].value = y_vals[row]
            mesh.attributes["spot_E"].data[row].value = energies[row]
            mesh.attributes["spot_weight"].data[row].value = spot_weights[row]
            mesh.vertices[row].co = (0.01 * row, 0.0, 0.0)

        mesh.update()
        mesh.validate()

        if mesh.vertices:
            obj = create_object(mesh, mesh.name)
            gantry_angle = float(control_points[0].GantryAngle) if hasattr(control_points[0], "GantryAngle") else 0.0
            iso_center = np.asarray(control_points[0].IsocenterPosition) / 1000.0
            obj.rotation_euler[1] = gantry_angle * math.pi / 180.0
            obj.location = (iso_center[0], iso_center[1], iso_center[2])
            apply_proton_spots_geo_nodes(node_tree_name="Proton_Spots")

    return True


class SNA_PT_MEDBLEND_70A7C(bpy.types.Panel):
    bl_label = "MedBlend"
    bl_idname = __package__
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Medical"

    def draw(self, _context):
        layout = self.layout
        layout.label(text="Images")
        layout.operator("medblend.load_ct", text="Load DICOM Images", icon="FILEBROWSER")
        layout.label(text="Dose")
        layout.operator("medblend.load_dose", text="Load DICOM Dose", icon="FILEBROWSER")
        layout.label(text="Structures")
        layout.operator("medblend.load_structures", text="Load DICOM Structures", icon="FILEBROWSER")
        layout.label(text="Proton Spots")
        layout.operator("medblend.load_proton", text="Load Proton Plan", icon="FILEBROWSER")


class SNA_OT_Load_Ct_Fc7B9(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_ct"
    bl_label = "Load CT"
    bl_description = "Load a CT Dataset"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.dcm", options={"HIDDEN"})

    def execute(self, _context):
        success = _load_ct_series(Path(self.filepath))
        return {"FINISHED"} if success else {"CANCELLED"}


class SNA_OT_Load_Proton_1Dbc6(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_proton"
    bl_label = "Load Proton"
    bl_description = "Load Proton Spots and Weights"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.dcm", options={"HIDDEN"})

    def execute(self, _context):
        success = _load_proton_plan(Path(self.filepath))
        return {"FINISHED"} if success else {"CANCELLED"}


class SNA_OT_Load_Dose_7629F(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_dose"
    bl_label = "Load Dose"
    bl_description = "Load a DICOM Dose File"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.dcm", options={"HIDDEN"})

    def execute(self, _context):
        success = _load_dose(Path(self.filepath))
        return {"FINISHED"} if success else {"CANCELLED"}


class SNA_OT_Load_Structures_5Ebc9(bpy.types.Operator, ImportHelper):
    bl_idname = "medblend.load_structures"
    bl_label = "Load Structures"
    bl_description = "Load a DICOM Structure Set"
    bl_options = {"REGISTER", "UNDO"}
    filter_glob: bpy.props.StringProperty(default="*.dcm", options={"HIDDEN"})

    def execute(self, _context):
        success = _load_structures(Path(self.filepath))
        return {"FINISHED"} if success else {"CANCELLED"}


classes: Iterable[type] = (
    SNA_PT_MEDBLEND_70A7C,
    SNA_OT_Load_Ct_Fc7B9,
    SNA_OT_Load_Proton_1Dbc6,
    SNA_OT_Load_Dose_7629F,
    SNA_OT_Load_Structures_5Ebc9,
)


def register():
    global _icons
    _icons = bpy.utils.previews.new()
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    global _icons
    bpy.utils.previews.remove(_icons)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

