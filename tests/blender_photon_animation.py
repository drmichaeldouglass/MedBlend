"""Run inside Blender with the packaged extension enabled (see extension.yml)."""

import math
import tempfile
from copy import deepcopy
from pathlib import Path

import bpy
from mathutils import Vector
from pydicom import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, RTPlanStorage, generate_uid


def dataset(**fields):
    ds = Dataset()
    for name, value in fields.items():
        setattr(ds, name, value)
    return ds


def write_plan(path, uid):
    mlc = dataset(
        RTBeamLimitingDeviceType="MLCX",
        NumberOfLeafJawPairs=2,
        LeafPositionBoundaries=[-15, -5, 15],
        SourceToBeamLimitingDeviceDistance=500,
    )
    jaw = dataset(
        RTBeamLimitingDeviceType="ASYMY",
        NumberOfLeafJawPairs=1,
        SourceToBeamLimitingDeviceDistance=400,
    )
    first = dataset(
        ControlPointIndex=0,
        IsocenterPosition=[100, 200, 300],
        GantryAngle=0,
        GantryRotationDirection="CW",
        BeamLimitingDeviceAngle=90,
        PatientSupportAngle=0,
        CumulativeMetersetWeight=0,
        BeamLimitingDevicePositionSequence=[
            dataset(RTBeamLimitingDeviceType="ASYMY", LeafJawPositions=[-25, 35]),
            dataset(
                RTBeamLimitingDeviceType="MLCX", LeafJawPositions=[-10, -20, 30, 40]
            ),
        ],
    )
    end = dataset(
        ControlPointIndex=1,
        GantryAngle=90,
        CumulativeMetersetWeight=1,
        BeamLimitingDevicePositionSequence=[
            dataset(RTBeamLimitingDeviceType="MLCX", LeafJawPositions=[10, 12, 18, 20])
        ],
    )
    beam = dataset(
        BeamNumber=1,
        RadiationType="PHOTON",
        SourceAxisDistance=1000,
        ReferencedPatientSetupNumber=1,
        BeamLimitingDeviceSequence=[mlc, jaw],
        ControlPointSequence=[first, end],
    )
    second = deepcopy(beam)
    second.BeamNumber = second.ReferencedPatientSetupNumber = 2
    second.BeamLimitingDeviceSequence[0].RTBeamLimitingDeviceType = "MLCY"
    second.ControlPointSequence[0].BeamLimitingDevicePositionSequence[
        1
    ].RTBeamLimitingDeviceType = "MLCY"
    second.ControlPointSequence[1].BeamLimitingDevicePositionSequence[
        0
    ].RTBeamLimitingDeviceType = "MLCY"
    second.ControlPointSequence[0].PatientSupportAngle = 90
    second.ControlPointSequence[0].BeamLimitingDeviceAngle = 0
    plan = dataset(
        SOPClassUID=RTPlanStorage,
        SOPInstanceUID=generate_uid(),
        FrameOfReferenceUID=uid,
        RTPlanLabel="Geometry",
        Modality="RTPLAN",
        RTPlanGeometry="PATIENT",
        BeamSequence=[beam, second],
        FractionGroupSequence=[
            dataset(
                FractionGroupNumber=1,
                ReferencedBeamSequence=[
                    dataset(ReferencedBeamNumber=1, BeamMeterset=25),
                    dataset(ReferencedBeamNumber=2, BeamMeterset=75),
                ],
            )
        ],
        PatientSetupSequence=[
            dataset(PatientSetupNumber=1, PatientPosition="HFS"),
            dataset(PatientSetupNumber=2, PatientPosition="FFS"),
        ],
    )
    plan.file_meta = FileMetaDataset()
    plan.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    plan.save_as(path, enforce_file_format=True)


def near(actual, expected):
    assert (actual - expected).length < 2e-6, (actual, expected)


def check_animation(scene, ct):
    iso = Vector((0.1, 0.2, 0.3))
    children = bpy.data.collections["Photon Plan Geometry"].children
    beam, second = children["Beam 1"], children["Beam 2"]
    a = beam.objects["MLCX A001"]
    b = beam.objects["MLCX B002"]
    y = second.objects["MLCY A001"]
    frames = list(beam["medblend_control_point_frames"])
    second_frames = list(second["medblend_control_point_frames"])
    assert frames == [1, 31] and second_frames == [32, 62]

    # Inner-edge midpoints and widths in metres, independently evaluated
    # on the actual Blender objects after CT placement and animation.
    for frame, angle, tip in [(1, 0, -0.005), (16, 45, 0), (31, 90, 0.005)]:
        scene.frame_set(frame)
        g = math.radians(angle)
        for corner, side in ((1, 0.0075), (2, 0.0025)):
            # At collimator 90, transverse row boundaries become -patient X.
            # Corner 1 lies on the lower boundary (-15 mm), corner 2 on -5.
            patient = iso + Vector(
                (
                    side * math.cos(g) + 0.5 * math.sin(g),
                    side * math.sin(g) - 0.5 * math.cos(g),
                    tip,
                )
            )
            near(a.matrix_world @ a.data.vertices[corner].co, ct.matrix_world @ patient)
        assert (
            not a.hide_viewport
            and not a.hide_render
            and y.hide_viewport
            and y.hide_render
        )
    scene.frame_set(1)
    near(
        b.matrix_world @ b.data.vertices[0].co,
        ct.matrix_world @ (iso + Vector((0.0025, -0.5, 0.02))),
    )
    scene.frame_set(62)
    # FFS, gantry 90, support 90. Local X -> patient +Y, Y -> -X, Z -> +Z.
    near(
        y.matrix_world @ y.data.vertices[2].co,
        ct.matrix_world @ (iso + Vector((-0.005, -0.0025, 0.5))),
    )
    assert (
        a.hide_viewport and a.hide_render and not y.hide_viewport and not y.hide_render
    )


def check_fluence(scene, ct):
    from bl_ext.user_default.medblend.volume_utils import _import_openvdb_module

    vdb = _import_openvdb_module()
    snapshots = bpy.data.collections["Cumulative Photon Fluence"].objects
    assert len(snapshots) == 2
    for frame, visible, expected in [
        (1, 0, 0),
        (32, 1, 0.25 * 0.625),
        (62, 1, 0.625),
        (34, 1, 0.25 * 0.625),
    ]:
        scene.frame_set(frame)
        displayed = [obj for obj in snapshots if not obj.hide_render]
        assert len(displayed) == visible
        assert all(obj.hide_viewport == obj.hide_render for obj in snapshots)
        if displayed:
            obj = displayed[0]
            assert obj.parent == ct and obj.active_material is not None
            grid = vdb.read(bpy.path.abspath(obj.data.filepath), "density")
            # Locate the DICOM isocentre in the on-disk grid via the moved CT
            # and Blender object, independently of the projector's array indices.
            local = obj.matrix_world.inverted() @ (
                ct.matrix_world @ Vector((0.1, 0.2, 0.3))
            )
            ijk = tuple(round(v) for v in grid.transform.worldToIndex(tuple(local)))
            assert abs(grid.getAccessor().getValue(ijk) - expected) < 0.01


with tempfile.TemporaryDirectory() as directory:
    scene = bpy.context.scene
    uid = generate_uid()
    ct = bpy.data.objects.new("Test CT", None)
    scene.collection.objects.link(ct)
    ct["medblend_is_ct"] = True
    ct["medblend_frame_of_reference_uid"] = uid
    ct["medblend_ct_basis_mm"] = [1, 0, 0, 0, 1, 0, 0, 0, 1]
    ct.location = (1, 2, 3)
    ct.rotation_euler.z = 0.7
    ct.scale = (1, 1.3, 2)
    bpy.context.view_layer.update()
    plan_path = Path(directory) / "test-plan.dcm"
    write_plan(plan_path, uid)
    assert bpy.ops.medblend.load_photon(
        filepath=str(plan_path), fluence=True, snapshots=3, voxel_mm=6
    ) == {"FINISHED"}
    assert bpy.ops.medblend.load_proton.get_rna_type()
    check_animation(scene, ct)
    check_fluence(scene, ct)
    # Check the saved rig after re-opening and moving the CT again.
    blend_path = str(Path(directory) / "plan.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    bpy.ops.wm.open_mainfile(filepath=blend_path)
    ct = bpy.data.objects["Test CT"]
    ct.location.y += 1
    check_animation(bpy.context.scene, ct)
    check_fluence(bpy.context.scene, ct)

print("Photon aperture animation passed")
