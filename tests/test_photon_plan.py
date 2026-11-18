"""Conventional RT Plan parsing and segment direction regressions."""

import pytest
from pydicom.dataset import Dataset

from MedBlend.photon_plan import _advance_angle, _control_points, _devices, _setup


def dataset(**fields):
    ds = Dataset()
    for name, value in fields.items():
        setattr(ds, name, value)
    return ds


def test_sparse_control_points_keep_each_devices_last_position():
    jaw = dataset(RTBeamLimitingDeviceType="ASYMX", NumberOfLeafJawPairs=1)
    mlc = dataset(
        RTBeamLimitingDeviceType="MLCY",
        NumberOfLeafJawPairs=2,
        LeafPositionBoundaries=[-9, -3, 5],
        SourceToBeamLimitingDeviceDistance=450,
    )
    jaw_tips = dataset(RTBeamLimitingDeviceType="ASYMX", LeafJawPositions=[-100, 80])
    mlc_tips = dataset(RTBeamLimitingDeviceType="MLCY", LeafJawPositions=[-4, -2, 3, 8])
    first = dataset(
        IsocenterPosition=[50, -80, 120],
        GantryAngle=350,
        GantryRotationDirection="CW",
        BeamLimitingDeviceAngle=5,
        PatientSupportAngle=20,
        BeamLimitingDevicePositionSequence=[mlc_tips, jaw_tips],
    )
    next_jaw = dataset(RTBeamLimitingDeviceType="ASYMX", LeafJawPositions=[-90, 60])
    last = dataset(GantryAngle=10, BeamLimitingDevicePositionSequence=[next_jaw])
    beam = dataset(
        SourceAxisDistance=1000,
        BeamLimitingDeviceSequence=[jaw, mlc],
        ControlPointSequence=[first, last],
    )
    notes = []
    devices = _devices(beam, notes)
    assert len(notes) == 1 and "ASYMX" in notes[0]
    assert devices["MLCY"].scale == pytest.approx(0.00045)
    assert devices["MLCY"].height == pytest.approx(0.55)
    start, end = _control_points(beam, devices)
    assert end.angles == (370, 5, 20)
    assert end.isocentre == start.isocentre
    assert end.tips["MLCY"] == start.tips["MLCY"] == (-4, -2, 3, 8)
    assert start.tips["ASYMX"] == (-100, 80)
    assert end.tips["ASYMX"] == (-90, 60)

    mlc_tips.LeafJawPositions = [1, 2]
    with pytest.raises(ValueError, match="4 values"):
        _control_points(beam, devices)
    first.BeamLimitingDevicePositionSequence = [jaw_tips]
    with pytest.raises(ValueError, match="missing initial.*MLCY"):
        _control_points(beam, devices)


@pytest.mark.parametrize(
    ("start", "end", "direction", "increasing", "expected"),
    [
        (350, 10, "CW", "CW", 370),
        (10, 350, "CC", "CW", -10),
        (10, 350, "CW", "CW", 350),
        (5, 5, "CW", "CW", 365),
        (5, 5, "NONE", "CW", 5),
        (170, 160, "CC", "CC", 520),
        (10, 350, "CW", "CC", -10),
        (350, 10, "CC", "CC", 370),
    ],
)
def test_machine_rotation(start, end, direction, increasing, expected):
    assert _advance_angle(start, end, direction, increasing) == expected


def test_setup_matches_the_beams_reference():
    plan = dataset(
        PatientSetupSequence=[
            dataset(PatientSetupNumber=1, PatientPosition="HFS"),
            dataset(PatientSetupNumber=2, PatientPosition="FFP"),
        ]
    )
    assert _setup(plan, dataset(ReferencedPatientSetupNumber=2), []) == "FFP"
    with pytest.raises(ValueError, match="ambiguous"):
        _setup(plan, Dataset(), [])


def test_invalid_boundaries_and_missing_sad():
    leaf = dataset(
        RTBeamLimitingDeviceType="MLCX",
        NumberOfLeafJawPairs=2,
        LeafPositionBoundaries=[2, 0, 4],
    )
    beam = dataset(BeamLimitingDeviceSequence=[leaf])
    with pytest.raises(ValueError, match="increase"):
        _devices(beam, [])
    leaf.LeafPositionBoundaries = [-2, 0, 4]
    notes = []
    device = _devices(beam, notes)["MLCX"]
    assert (device.scale, device.height) == (0.001, 0)
    assert "isocentre" in notes[0]


def test_empty_optional_control_point_values_are_treated_as_unspecified():
    """Present-but-empty optional attributes read as None and mean "not given"."""

    jaw = dataset(RTBeamLimitingDeviceType="ASYMX", NumberOfLeafJawPairs=1)
    tips = dataset(RTBeamLimitingDeviceType="ASYMX", LeafJawPositions=[-50, 50])
    first = dataset(
        IsocenterPosition=[1, 2, 3],
        GantryAngle=0,
        BeamLimitingDeviceAngle=0,
        PatientSupportAngle=0,
        GantryPitchAngle=None,
        TableTopPitchAngle=None,
        TableTopRollAngle=None,
        TableTopEccentricAngle=None,
        BeamLimitingDevicePositionSequence=[tips],
    )
    last = dataset(IsocenterPosition=None, TableTopEccentricAngle=None)
    beam = dataset(BeamLimitingDeviceSequence=[jaw], ControlPointSequence=[first, last])
    devices = _devices(beam, [])

    start, end = _control_points(beam, devices)
    assert start.isocentre == end.isocentre == (1, 2, 3)

    # A value that is actually given is still checked.
    last.TableTopEccentricAngle = 5
    with pytest.raises(ValueError, match="TableTopEccentricAngle"):
        _control_points(beam, devices)
    last.TableTopEccentricAngle = None

    # The first control point has nothing to inherit an isocentre from.
    first.IsocenterPosition = None
    with pytest.raises(ValueError, match="IsocenterPosition"):
        _control_points(beam, devices)
