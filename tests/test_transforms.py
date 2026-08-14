"""Tests for patient-space placement and CT co-registration maths."""

from __future__ import annotations

import bpy
import numpy as np
import pytest
from mathutils import Matrix

from MedBlend.volume_utils import (
    _sanitize_filename,
    _unique_path,
    align_object_to_ct_frame,
    find_ct_anchor,
    set_object_patient_transform,
)


class FakeObject:
    """Stand-in for bpy.types.Object with custom properties and a transform."""

    def __init__(self, **properties):
        self._properties = dict(properties)
        self.matrix_world = Matrix()

    def get(self, key, default=None):
        return self._properties.get(key, default)

    def __getitem__(self, key):
        return self._properties[key]

    def __setitem__(self, key, value):
        self._properties[key] = value


def apply(matrix: Matrix, vector) -> np.ndarray:
    """Apply a 4x4 mathutils-style matrix to a 3-vector."""

    rows = matrix.rows
    point = [float(vector[0]), float(vector[1]), float(vector[2]), 1.0]
    return np.asarray([sum(rows[i][j] * point[j] for j in range(4)) for i in range(3)])


# Axial CT: 3 mm slices, 1 mm rows, 2 mm columns, anchored away from origin.
CT_ORIGIN = np.asarray([10.0, 20.0, 300.0])
CT_SPACING = np.asarray([3.0, 1.0, 2.0])  # (slice, row, col)
CT_BASIS = np.column_stack(
    (
        np.asarray([0.0, 0.0, -1.0]) * CT_SPACING[0],  # slice axis
        np.asarray([0.0, 1.0, 0.0]) * CT_SPACING[1],  # row axis
        np.asarray([1.0, 0.0, 0.0]) * CT_SPACING[2],  # col axis
    )
)


def make_ct_object(frame_uid: str = "1.2.840.frame") -> FakeObject:
    ct = FakeObject(
        medblend_is_ct=True,
        medblend_frame_of_reference_uid=frame_uid,
        medblend_ct_origin_mm=[float(v) for v in CT_ORIGIN],
        medblend_ct_basis_mm=[float(v) for v in CT_BASIS.reshape(-1)],
        medblend_ct_spacing_mm=[float(v) for v in CT_SPACING],
    )
    set_object_patient_transform(
        ct,
        CT_ORIGIN,
        np.asarray([0.0, 0.0, -1.0]),
        np.asarray([0.0, 1.0, 0.0]),
        np.asarray([1.0, 0.0, 0.0]),
    )
    return ct


class TestSetObjectPatientTransform:
    def test_maps_voxel_indices_to_patient_millimetres(self):
        ct = make_ct_object()
        for index in [(0, 0, 0), (2, 5, 7), (4, 1, 3)]:
            # The VDB grid already bakes spacing into its local coordinates.
            local = np.asarray(index, dtype=float) * CT_SPACING / 1000.0
            patient = CT_ORIGIN + CT_BASIS @ np.asarray(index, dtype=float)
            assert np.allclose(apply(ct.matrix_world, local), patient / 1000.0)

    def test_millimetres_are_converted_to_metres(self):
        obj = FakeObject()
        set_object_patient_transform(obj, [1000.0, -2000.0, 500.0], [1, 0, 0], [0, 1, 0], [0, 0, 1])
        assert obj.matrix_world.translation == pytest.approx((1.0, -2.0, 0.5))


class TestAlignObjectToCtFrame:
    def _dose_setup(self):
        dose_origin = np.asarray([-40.0, 5.0, 280.0])
        dose_spacing = np.asarray([5.0, 2.5, 2.5])  # (slice, row, col)
        dose_basis = np.column_stack(
            (
                np.asarray([0.0, 0.0, 1.0]) * dose_spacing[0],
                np.asarray([0.0, 1.0, 0.0]) * dose_spacing[1],
                np.asarray([1.0, 0.0, 0.0]) * dose_spacing[2],
            )
        )
        return dose_origin, dose_spacing, dose_basis

    def test_dose_voxels_land_on_their_patient_position(self):
        ct = make_ct_object()
        dose = FakeObject()
        dose_origin, dose_spacing, dose_basis = self._dose_setup()

        assert align_object_to_ct_frame(dose, ct, dose_origin, dose_basis, dose_spacing)

        for index in [(0, 0, 0), (3, 4, 6), (1, 9, 2)]:
            local = np.asarray(index, dtype=float) * dose_spacing / 1000.0
            patient = dose_origin + dose_basis @ np.asarray(index, dtype=float)
            assert np.allclose(apply(dose.matrix_world, local), patient / 1000.0, atol=1e-9)

    def test_alignment_follows_a_moved_ct(self):
        ct = make_ct_object()
        # The user drags the CT 1 m along +X after importing it.
        ct.matrix_world = Matrix.Translation((1.0, 0.0, 0.0)) @ ct.matrix_world

        dose = FakeObject()
        dose_origin, dose_spacing, dose_basis = self._dose_setup()
        assert align_object_to_ct_frame(dose, ct, dose_origin, dose_basis, dose_spacing)

        patient = dose_origin + dose_basis @ np.asarray([2.0, 3.0, 4.0])
        local = np.asarray([2.0, 3.0, 4.0]) * dose_spacing / 1000.0
        expected = patient / 1000.0 + np.asarray([1.0, 0.0, 0.0])
        assert np.allclose(apply(dose.matrix_world, local), expected, atol=1e-9)

    def test_returns_false_without_ct_metadata(self):
        assert not align_object_to_ct_frame(FakeObject(), FakeObject(), [0, 0, 0], np.eye(3), [1, 1, 1])

    def test_returns_false_for_non_positive_spacing(self):
        ct = make_ct_object()
        dose_origin, _, dose_basis = self._dose_setup()
        assert not align_object_to_ct_frame(FakeObject(), ct, dose_origin, dose_basis, [0.0, 1.0, 1.0])


class TestFindCtAnchor:
    def setup_method(self):
        self._saved = list(bpy.data.objects)
        bpy.data.objects.clear()

    def teardown_method(self):
        bpy.data.objects.clear()
        bpy.data.objects.extend(self._saved)

    def test_prefers_matching_frame_of_reference(self):
        other = FakeObject(medblend_is_ct=True, medblend_frame_of_reference_uid="other")
        wanted = FakeObject(medblend_is_ct=True, medblend_frame_of_reference_uid="wanted")
        bpy.data.objects.extend([other, wanted])
        assert find_ct_anchor("wanted") is wanted

    def test_no_match_for_frame_uid_returns_none(self):
        bpy.data.objects.append(FakeObject(medblend_is_ct=True, medblend_frame_of_reference_uid="a"))
        # Falling back to an unrelated CT would silently misregister the dose.
        assert find_ct_anchor("b") is None

    def test_blank_frame_uid_uses_most_recent_ct(self):
        first = FakeObject(medblend_is_ct=True, medblend_frame_of_reference_uid="a")
        second = FakeObject(medblend_is_ct=True, medblend_frame_of_reference_uid="b")
        bpy.data.objects.extend([first, second])
        assert find_ct_anchor("") is second

    def test_ignores_non_ct_objects(self):
        bpy.data.objects.append(FakeObject())
        assert find_ct_anchor("") is None


class TestTempPaths:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("PTV_70", "PTV_70"),
            ("Parotid (L)", "Parotid _L_"),
            ("../../etc/passwd", "_.._etc_passwd"),
            ("Bowel/Bag", "Bowel_Bag"),
            ("...", "volume"),
            ("", "volume"),
        ],
    )
    def test_roi_names_are_sanitised_into_filenames(self, raw, expected):
        # ROI names come from the planning system and may contain separators.
        assert _sanitize_filename(raw) == expected

    def test_existing_files_are_never_overwritten(self, tmp_path):
        (tmp_path / "CT.vdb").write_text("first")
        (tmp_path / "CT_1.vdb").write_text("second")
        assert _unique_path(tmp_path, "CT.vdb").name == "CT_2.vdb"

    def test_free_name_is_used_as_is(self, tmp_path):
        assert _unique_path(tmp_path, "dose.vdb").name == "dose.vdb"
