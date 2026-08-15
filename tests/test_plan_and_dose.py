"""Tests for RT Ion plan detection and RT Dose grid geometry."""

from __future__ import annotations

import math

import pydicom
import pytest
from pydicom.dataset import Dataset

import numpy as np

from MedBlend.dose import dose_grid_spacing
from MedBlend.plan import (
    RT_ION_PLAN_STORAGE_UID,
    _as_float_list,
    _beam_world_matrix,
    _patient_position,
    is_proton_plan,
)


def make_ion_plan(*, modality: str = "RTPLAN", sop_class: str | None = RT_ION_PLAN_STORAGE_UID) -> Dataset:
    ds = Dataset()
    ds.Modality = modality
    if sop_class is not None:
        ds.SOPClassUID = sop_class
    ds.IonBeamSequence = [Dataset()]
    return ds


class TestIsProtonPlan:
    def test_accepts_standard_rt_ion_plan(self):
        # Conformant RT Ion Plan files carry Modality "RTPLAN"; the ion variant
        # is identified by its SOP Class UID.
        assert is_proton_plan(make_ion_plan()) is True

    def test_accepts_rtplan_carrying_ion_beams_without_sop_class(self):
        assert is_proton_plan(make_ion_plan(sop_class=None)) is True

    def test_accepts_legacy_rtion_modality(self):
        ds = Dataset()
        ds.Modality = "RTION"
        assert is_proton_plan(ds) is True

    def test_rejects_photon_rt_plan(self):
        ds = Dataset()
        ds.Modality = "RTPLAN"
        ds.SOPClassUID = pydicom.uid.RTPlanStorage
        ds.BeamSequence = [Dataset()]
        assert is_proton_plan(ds) is False

    @pytest.mark.parametrize("modality", ["RTSTRUCT", "RTDOSE", "CT"])
    def test_rejects_other_modalities(self, modality):
        ds = Dataset()
        ds.Modality = modality
        assert is_proton_plan(ds) is False

    def test_rejects_dataset_without_modality(self):
        assert is_proton_plan(Dataset()) is False

    def test_modality_whitespace_and_case_are_tolerated(self):
        ds = Dataset()
        ds.Modality = " rtion "
        assert is_proton_plan(ds) is True


class TestPlanHelpers:
    def test_as_float_list_handles_sequences_and_scalars(self):
        assert _as_float_list([1, 2.5]) == [1.0, 2.5]
        assert _as_float_list(3) == [3.0]
        assert _as_float_list(None) == []
        assert _as_float_list("120") == []

    def test_patient_position_read_from_setup_sequence(self):
        ds = Dataset()
        setup = Dataset()
        setup.PatientPosition = "hfs"
        ds.PatientSetupSequence = [setup]
        assert _patient_position(ds) == "HFS"

    def test_patient_position_missing_is_blank(self):
        assert _patient_position(Dataset()) == ""

    def test_beam_matrix_places_isocentre_in_metres(self):
        control_point = Dataset()
        control_point.GantryAngle = 0.0
        control_point.PatientSupportAngle = 0.0
        control_point.IsocenterPosition = [10.0, -20.0, 300.0]
        matrix = _beam_world_matrix(control_point)
        assert matrix.translation == pytest.approx((0.01, -0.02, 0.3))

    def test_beam_matrix_applies_gantry_rotation(self):
        control_point = Dataset()
        control_point.GantryAngle = 90.0
        control_point.PatientSupportAngle = 0.0
        control_point.IsocenterPosition = [0.0, 0.0, 0.0]
        matrix = _beam_world_matrix(control_point)
        # 90 degrees about the patient superior-inferior axis (DICOM +Z).
        assert matrix.rows[0][0] == pytest.approx(math.cos(math.radians(90)), abs=1e-9)
        assert matrix.rows[1][0] == pytest.approx(math.sin(math.radians(90)), abs=1e-9)

    def test_beam_matrix_survives_missing_isocentre(self):
        # IsocenterPosition is Type 1C and float(None) used to crash the import.
        matrix = _beam_world_matrix(Dataset())
        assert matrix.translation == pytest.approx((0.0, 0.0, 0.0))

    def test_beam_matrix_survives_empty_angles(self):
        control_point = Dataset()
        control_point.GantryAngle = None
        control_point.PatientSupportAngle = None
        control_point.IsocenterPosition = None
        matrix = _beam_world_matrix(control_point)
        assert matrix.translation == pytest.approx((0.0, 0.0, 0.0))


def beam_axes(gantry: float, couch: float = 0.0):
    """The (spot_x, spot_y, spot_E) object axes in DICOM patient coordinates."""

    control_point = Dataset()
    control_point.GantryAngle = gantry
    control_point.PatientSupportAngle = couch
    control_point.IsocenterPosition = [0.0, 0.0, 0.0]
    basis = np.asarray(_beam_world_matrix(control_point).rows)[:3, :3]
    return basis[:, 0], basis[:, 1], basis[:, 2]


def beam_travel_direction(gantry: float, couch: float):
    """Reference direction of travel for an HFS patient, in DICOM patient mm."""

    g, t = math.radians(gantry), math.radians(couch)
    return np.array([-math.sin(g) * math.cos(t), math.cos(g), math.sin(g) * math.sin(t)])


class TestBeamOrientation:
    """The node group positions spots at local (spot_x, spot_y, spot_E), so the
    object's local axes are the IEC 61217 beam axes and must be oriented to the
    patient. An identity base frame left spot_y running anterior-posterior and
    pinned the energy axis to the patient's long axis at every gantry angle."""

    def test_gantry_zero_matches_the_iec_beam_frame(self):
        spot_x, spot_y, spot_e = beam_axes(0.0)
        assert spot_x == pytest.approx([1.0, 0.0, 0.0], abs=1e-9)   # patient left
        assert spot_y == pytest.approx([0.0, 0.0, 1.0], abs=1e-9)   # patient superior
        assert spot_e == pytest.approx([0.0, -1.0, 0.0], abs=1e-9)  # anterior, toward source

    def test_gantry_ninety_is_a_left_lateral_beam(self):
        _spot_x, spot_y, spot_e = beam_axes(90.0)
        # Source on the patient's left, and the scan plane still carries the
        # superior-inferior axis rather than rotating it away.
        assert spot_e == pytest.approx([1.0, 0.0, 0.0], abs=1e-9)
        assert spot_y == pytest.approx([0.0, 0.0, 1.0], abs=1e-9)

    @pytest.mark.parametrize(
        "gantry,couch",
        [(0, 0), (90, 0), (180, 0), (270, 0), (45, 0), (0, 90), (90, 90), (30, 20)],
    )
    def test_energy_axis_points_back_along_the_beam(self, gantry, couch):
        _spot_x, _spot_y, spot_e = beam_axes(gantry, couch)
        assert spot_e == pytest.approx(-beam_travel_direction(gantry, couch), abs=1e-9)

    @pytest.mark.parametrize("gantry,couch", [(0, 0), (90, 0), (45, 30), (200, 110)])
    def test_frame_stays_right_handed(self, gantry, couch):
        # A mirrored frame would flip the scan spot pattern left-to-right.
        spot_x, spot_y, spot_e = beam_axes(gantry, couch)
        assert np.cross(spot_x, spot_y) == pytest.approx(spot_e, abs=1e-9)

    def test_isocentre_translation_is_unaffected(self):
        control_point = Dataset()
        control_point.GantryAngle = 37.0
        control_point.PatientSupportAngle = 12.0
        control_point.IsocenterPosition = [10.0, -20.0, 300.0]
        assert _beam_world_matrix(control_point).translation == pytest.approx((0.01, -0.02, 0.3))


class TestDoseGridSpacing:
    def _dose(self, **attributes) -> Dataset:
        ds = Dataset()
        ds.Modality = "RTDOSE"
        ds.PixelSpacing = [2.5, 3.0]
        for key, value in attributes.items():
            setattr(ds, key, value)
        return ds

    def test_spacing_from_grid_frame_offsets(self):
        spacing, step = dose_grid_spacing(self._dose(GridFrameOffsetVector=[0.0, 3.0, 6.0, 9.0]))
        assert spacing == pytest.approx([3.0, 2.5, 3.0])
        assert step == pytest.approx(3.0)

    def test_descending_offsets_give_a_negative_step(self):
        # The grid runs opposite to the slice normal; spacing stays positive.
        spacing, step = dose_grid_spacing(self._dose(GridFrameOffsetVector=[0.0, -2.0, -4.0]))
        assert spacing[0] == pytest.approx(2.0)
        assert step == pytest.approx(-2.0)

    def test_empty_slice_thickness_does_not_raise(self):
        # SliceThickness is Type 2 and routinely empty; float(None) crashed here.
        spacing, step = dose_grid_spacing(self._dose(SliceThickness=None))
        assert spacing == pytest.approx([1.0, 2.5, 3.0])
        assert step == pytest.approx(1.0)

    def test_falls_back_to_slice_thickness_without_offsets(self):
        spacing, _ = dose_grid_spacing(self._dose(SliceThickness=4.0))
        assert spacing[0] == pytest.approx(4.0)

    def test_single_offset_falls_back_to_slice_thickness(self):
        spacing, _ = dose_grid_spacing(self._dose(GridFrameOffsetVector=[0.0], SliceThickness=5.0))
        assert spacing[0] == pytest.approx(5.0)

    def test_constant_offsets_fall_back_to_slice_thickness(self):
        spacing, _ = dose_grid_spacing(self._dose(GridFrameOffsetVector=[0.0, 0.0], SliceThickness=2.0))
        assert spacing[0] == pytest.approx(2.0)

    def test_missing_pixel_spacing_defaults_to_one_millimetre(self):
        ds = Dataset()
        ds.Modality = "RTDOSE"
        spacing, _ = dose_grid_spacing(ds)
        assert spacing == pytest.approx([1.0, 1.0, 1.0])

    def test_zero_pixel_spacing_is_rejected(self):
        spacing, _ = dose_grid_spacing(self._dose(PixelSpacing=[0.0, -1.0]))
        assert spacing[1:] == pytest.approx([1.0, 1.0])

    def test_non_uniform_offsets_use_the_median_step(self):
        spacing, _ = dose_grid_spacing(self._dose(GridFrameOffsetVector=[0.0, 3.0, 6.0, 20.0]))
        assert spacing[0] == pytest.approx(3.0)
