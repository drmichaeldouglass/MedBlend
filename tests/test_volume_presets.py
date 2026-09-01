"""Tests for the Slicer-style volume rendering presets."""

from __future__ import annotations

import pytest

import bpy
import MedBlend
from MedBlend import presets, volume_materials

CT_HU_RANGE = (-1024.0, 3071.0)


# ---------------------------------------------------------------------------
# Preset data
# ---------------------------------------------------------------------------


class TestPresetTable:
    def test_every_slicer_preset_is_present(self):
        names = [preset.name for preset in presets.VOLUME_PRESETS]

        assert len(names) == 31
        assert len(set(names)) == len(names)
        for expected in ("CT-Bone", "CT-Lung", "CT-MIP", "MR-Default", "MR-T2-Brain", "uCT-Skull"):
            assert expected in names

    def test_lookup_by_name(self):
        assert presets.get_preset("CT-Bone").name == "CT-Bone"
        assert presets.get_preset("not-a-preset") is None

    @pytest.mark.parametrize("preset", presets.VOLUME_PRESETS, ids=lambda p: p.name)
    def test_transfer_functions_are_usable(self, preset):
        for points, width in ((preset.color, 4), (preset.opacity, 2)):
            assert len(points) >= 2
            assert all(len(point) == width for point in points)
            scalars = [point[0] for point in points]
            assert scalars == sorted(scalars)
            for point in points:
                assert all(0.0 <= value <= 1.0 for value in point[1:])

    @pytest.mark.parametrize("preset", presets.VOLUME_PRESETS, ids=lambda p: p.name)
    def test_every_preset_has_a_description_and_window(self, preset):
        assert preset.description
        low, high = preset.window
        assert high > low

    def test_malformed_upstream_ranges_are_dropped(self):
        # Upstream ships "-250.0.0 1550.0" for CT-X-ray and the placeholder
        # "0 -1" for the micro-CT presets; neither can be used as a window.
        for name in ("CT-X-ray", "uCT-Bone-8bit", "uCT-Bone-16bit", "uCT-Skull"):
            preset = presets.get_preset(name)
            assert preset.effective_range is None
            assert preset.window == preset.scalar_range

    def test_only_ct_presets_are_treated_as_hounsfield(self):
        assert presets.get_preset("CT-Bone").is_absolute
        assert not presets.get_preset("MR-Default").is_absolute
        assert not presets.get_preset("uCT-Skull").is_absolute


class TestEnumItems:
    def test_import_items_offer_the_default_material_first(self):
        first = presets.IMPORT_PRESET_ENUM_ITEMS[0]
        assert first[0] == presets.NO_PRESET

    def test_items_are_unique_and_cover_every_preset(self):
        identifiers = [item[0] for item in presets.PRESET_ENUM_ITEMS if item is not None]

        assert identifiers == [preset.name for preset in presets.VOLUME_PRESETS]
        assert len(set(identifiers)) == len(identifiers)

    def test_modality_groups_are_separated(self):
        # ``None`` is Blender's separator; there is one between each family.
        assert None in presets.PRESET_ENUM_ITEMS
        assert all(
            item is None or (len(item) == 3 and all(isinstance(field, str) for field in item))
            for item in presets.PRESET_ENUM_ITEMS
        )

    def test_items_are_built_once(self):
        # Blender reads enum strings by reference, so rebuilding the items per
        # draw call is a known source of corrupted labels.
        assert presets.PRESET_ENUM_ITEMS is presets.PRESET_ENUM_ITEMS


# ---------------------------------------------------------------------------
# Transfer function maths
# ---------------------------------------------------------------------------


RAMP = ((0.0, 0.0), (10.0, 1.0), (20.0, 0.5))


class TestEvaluate:
    def test_values_are_held_constant_outside_the_control_points(self):
        assert presets.evaluate(RAMP, -100.0) == (0.0,)
        assert presets.evaluate(RAMP, 1000.0) == (0.5,)

    def test_control_points_are_returned_exactly(self):
        assert presets.evaluate(RAMP, 0.0) == (0.0,)
        assert presets.evaluate(RAMP, 10.0) == (1.0,)
        assert presets.evaluate(RAMP, 20.0) == (0.5,)

    def test_interpolation_is_linear(self):
        assert presets.evaluate(RAMP, 5.0)[0] == pytest.approx(0.5)
        assert presets.evaluate(RAMP, 15.0)[0] == pytest.approx(0.75)

    def test_a_repeated_scalar_reads_as_a_step(self):
        step = ((0.0, 0.0), (5.0, 0.0), (5.0, 1.0), (10.0, 1.0))
        assert presets.evaluate(step, 5.0) == (1.0,)
        assert presets.evaluate(step, 4.999)[0] == pytest.approx(0.0, abs=1e-3)

    def test_all_components_are_interpolated(self):
        color = ((0.0, 0.0, 0.0, 0.0), (10.0, 1.0, 0.5, 0.25))
        assert presets.evaluate(color, 5.0) == pytest.approx((0.5, 0.25, 0.125))

    def test_an_empty_function_is_rejected(self):
        with pytest.raises(ValueError):
            presets.evaluate((), 0.0)


class TestResample:
    def test_the_ends_span_the_whole_normalised_axis(self):
        stops = presets.resample(RAMP, 0.0, 20.0)

        assert stops[0][0] == 0.0
        assert stops[-1][0] == 1.0

    def test_interior_control_points_keep_their_relative_position(self):
        stops = presets.resample(RAMP, 0.0, 20.0)

        assert [position for position, _ in stops] == pytest.approx([0.0, 0.5, 1.0])
        assert [values[0] for _, values in stops] == pytest.approx([0.0, 1.0, 0.5])

    def test_a_window_narrower_than_the_function_evaluates_its_ends(self):
        # Clamping the original points into range instead would pile several
        # of them onto position 0 and lose the boundary value.
        stops = presets.resample(RAMP, 5.0, 15.0)

        assert [position for position, _ in stops] == pytest.approx([0.0, 0.5, 1.0])
        assert [values[0] for _, values in stops] == pytest.approx([0.5, 1.0, 0.75])

    def test_a_window_wider_than_the_function_holds_the_end_values(self):
        stops = presets.resample(RAMP, -20.0, 40.0)

        assert stops[0][1] == pytest.approx((0.0,))
        assert stops[-1][1] == pytest.approx((0.5,))

    def test_repeated_scalars_are_separated_so_a_ramp_can_hold_them(self):
        step = ((0.0, 0.0), (5.0, 1.0), (5.0, 0.0), (10.0, 1.0))
        positions = [position for position, _ in presets.resample(step, 0.0, 10.0)]

        assert positions == sorted(positions)
        assert len(set(positions)) == len(positions)

    @pytest.mark.parametrize("preset", presets.VOLUME_PRESETS, ids=lambda p: p.name)
    def test_every_preset_resamples_to_a_valid_ramp(self, preset):
        for points in (preset.color, preset.opacity):
            for window in (CT_HU_RANGE, preset.window):
                stops = presets.resample(points, *window)

                positions = [position for position, _ in stops]
                assert positions[0] == 0.0 and positions[-1] == 1.0
                assert all(a < b for a, b in zip(positions, positions[1:]))
                # Blender colour ramps hold at most 32 elements.
                assert len(stops) <= 32

    def test_a_collapsed_range_is_rejected(self):
        with pytest.raises(ValueError):
            presets.resample(RAMP, 5.0, 5.0)


class TestResolveWindow:
    def test_a_ct_preset_on_a_ct_volume_uses_hounsfield_units(self):
        window = presets.resolve_window(
            presets.get_preset("CT-Bone"), *CT_HU_RANGE, modality="CT"
        )
        assert window == CT_HU_RANGE

    def test_a_ct_preset_on_an_mr_volume_falls_back_to_fitting(self):
        preset = presets.get_preset("CT-Bone")
        window = presets.resolve_window(preset, 0.0, 4095.0, modality="MR")
        assert window == preset.window

    def test_an_mr_preset_is_stretched_over_the_data_range(self):
        # MR intensities are not calibrated, so the preset's authored window
        # is what gets mapped onto whatever the scan happens to contain.
        preset = presets.get_preset("MR-Default")
        assert presets.resolve_window(preset, 0.0, 4095.0, modality="MR") == preset.window

    def test_absolute_can_be_forced(self):
        preset = presets.get_preset("MR-Default")
        window = presets.resolve_window(
            preset, *CT_HU_RANGE, fit_mode=presets.FIT_ABSOLUTE, modality="MR"
        )
        assert window == CT_HU_RANGE

    def test_fitting_can_be_forced(self):
        preset = presets.get_preset("CT-Bone")
        window = presets.resolve_window(
            preset, *CT_HU_RANGE, fit_mode=presets.FIT_RANGE, modality="CT"
        )
        assert window == preset.window

    @pytest.mark.parametrize(
        "low,high",
        [(None, None), (0.0, None), (5.0, 5.0), (10.0, 0.0)],
        ids=["missing", "partial", "collapsed", "inverted"],
    )
    def test_an_unusable_intensity_range_falls_back_to_the_preset_window(self, low, high):
        preset = presets.get_preset("CT-Bone")
        window = presets.resolve_window(preset, low, high, fit_mode=presets.FIT_ABSOLUTE)
        assert window == preset.window

    def test_an_unknown_modality_still_trusts_hounsfield_units(self):
        # Volumes imported before the modality was recorded should keep
        # behaving as CT rather than silently switching to a fitted window.
        window = presets.resolve_window(presets.get_preset("CT-Bone"), *CT_HU_RANGE, modality="")
        assert window == CT_HU_RANGE


class TestColorHelpers:
    def test_srgb_endpoints_are_preserved(self):
        assert presets.srgb_to_linear(0.0) == 0.0
        assert presets.srgb_to_linear(1.0) == pytest.approx(1.0)

    def test_midtones_are_darkened(self):
        assert presets.srgb_to_linear(0.5) == pytest.approx(0.2140, abs=1e-4)

    def test_the_curve_is_monotonic(self):
        samples = [presets.srgb_to_linear(value / 32) for value in range(33)]
        assert all(a < b for a, b in zip(samples, samples[1:]))

    def test_the_viewport_colour_comes_from_the_most_opaque_point(self):
        # CT-Bone is most opaque at 641 HU, where its colour is bone beige.
        assert presets.representative_color(presets.get_preset("CT-Bone")) == pytest.approx(
            (0.905882, 0.815686, 0.552941, 1.0), abs=1e-5
        )


# ---------------------------------------------------------------------------
# Fakes for the Blender shader node API
# ---------------------------------------------------------------------------


_NODE_SOCKETS = {
    "ShaderNodeVolumeInfo": ([], ["Color", "Density", "Flame", "Temperature"]),
    "ShaderNodeMapRange": (
        ["Value", "From Min", "From Max", "To Min", "To Max", "Steps"],
        ["Result"],
    ),
    "ShaderNodeValToRGB": (["Fac"], ["Color", "Alpha"]),
    "ShaderNodeMath": (["Value", "Value", "Value"], ["Value"]),
    "ShaderNodeVectorMath": (["Vector", "Vector", "Vector", "Scale"], ["Vector", "Value"]),
    "ShaderNodeVolumePrincipled": (
        [
            "Color",
            "Color Attribute",
            "Density",
            "Density Attribute",
            "Anisotropy",
            "Absorption Color",
            "Emission Strength",
            "Emission Color",
            "Blackbody Intensity",
            "Blackbody Tint",
            "Temperature",
            "Temperature Attribute",
        ],
        ["Volume"],
    ),
    "ShaderNodeOutputMaterial": (["Surface", "Volume", "Displacement"], []),
}


class FakeSocket:
    def __init__(self, node, name):
        self.node = node
        self.name = name
        self.default_value = None


class FakeSockets:
    """Blender sockets are addressable by index and by name, duplicates and all."""

    def __init__(self, node, names):
        self._sockets = [FakeSocket(node, name) for name in names]

    def __len__(self):
        return len(self._sockets)

    def __iter__(self):
        return iter(self._sockets)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._sockets[key]
        for socket in self._sockets:
            if socket.name == key:
                return socket
        raise KeyError(key)


class FakeRampElement:
    def __init__(self, position, color=(0.0, 0.0, 0.0, 1.0)):
        self.position = position
        self.color = color


class FakeRampElements:
    def __init__(self):
        self._elements = [FakeRampElement(0.0), FakeRampElement(1.0, (1.0, 1.0, 1.0, 1.0))]

    def __len__(self):
        return len(self._elements)

    def __iter__(self):
        return iter(self._elements)

    def __getitem__(self, index):
        return self._elements[index]

    def new(self, position):
        element = FakeRampElement(position)
        self._elements.append(element)
        self._elements.sort(key=lambda item: item.position)
        return element

    def remove(self, element):
        if len(self._elements) == 1:
            raise RuntimeError("A colour ramp must keep at least one element")
        self._elements.remove(element)


class FakeColorRamp:
    def __init__(self):
        self.elements = FakeRampElements()
        self.color_mode = "RGB"
        self.interpolation = "LINEAR"


class FakeNode:
    def __init__(self, bl_idname):
        self.bl_idname = bl_idname
        self.name = bl_idname
        self.label = ""
        self.location = (0.0, 0.0)
        inputs, outputs = _NODE_SOCKETS[bl_idname]
        self.inputs = FakeSockets(self, inputs)
        self.outputs = FakeSockets(self, outputs)
        if bl_idname == "ShaderNodeValToRGB":
            self.color_ramp = FakeColorRamp()


class FakeNodes(list):
    def new(self, bl_idname):
        node = FakeNode(bl_idname)
        self.append(node)
        return node

    def get(self, name, default=None):
        return next((node for node in self if node.name == name), default)


class FakeLinks(list):
    def new(self, output, input_socket):
        self.append((output, input_socket))
        return self[-1]


class FakeNodeTree:
    def __init__(self):
        self.nodes = FakeNodes()
        self.links = FakeLinks()


class FakeMaterial:
    def __init__(self, name):
        self.name = name
        self.use_nodes = False
        self.node_tree = FakeNodeTree()
        self.diffuse_color = (1.0, 1.0, 1.0, 1.0)
        self.id_properties = {}

    def __setitem__(self, key, value):
        self.id_properties[key] = value

    def get(self, key, default=None):
        return self.id_properties.get(key, default)


class FakeMaterialRegistry:
    def __init__(self):
        self.by_name = {}

    def get(self, name, default=None):
        return self.by_name.get(name, default)

    def new(self, name):
        material = FakeMaterial(name)
        self.by_name[name] = material
        return material

    def __len__(self):
        return len(self.by_name)


class FakeVolume:
    def __init__(self, name="CT", **id_properties):
        self.name = name
        self.type = "VOLUME"
        self.data = type("Data", (), {"materials": []})()
        self.id_properties = dict(id_properties)

    def get(self, key, default=None):
        return self.id_properties.get(key, default)


@pytest.fixture
def materials(monkeypatch):
    registry = FakeMaterialRegistry()
    monkeypatch.setattr(bpy.data, "materials", registry, raising=False)
    return registry


def ct_volume(**overrides):
    properties = {
        "medblend_intensity_min": CT_HU_RANGE[0],
        "medblend_intensity_max": CT_HU_RANGE[1],
        "medblend_modality": "CT",
    }
    properties.update(overrides)
    return FakeVolume(**properties)


def node_named(material, name):
    return material.node_tree.nodes.get(name)


def linked_from(material, input_socket):
    return [output for output, target in material.node_tree.links if target is input_socket]


# ---------------------------------------------------------------------------
# Material construction
# ---------------------------------------------------------------------------


class TestBuildPresetNodeTree:
    @pytest.fixture
    def material(self, materials):
        preset = presets.get_preset("CT-Bone")
        return volume_materials.get_preset_material(preset, CT_HU_RANGE, 200.0, 1.0)

    def test_the_volume_grid_reaches_both_ramps_through_the_window(self, material):
        window = node_named(material, "Window")
        volume_info = next(
            node for node in material.node_tree.nodes if node.bl_idname == "ShaderNodeVolumeInfo"
        )

        assert linked_from(material, window.inputs["Value"]) == [volume_info.outputs["Density"]]
        for ramp_name in ("Color Transfer", "Scalar Opacity"):
            ramp = node_named(material, ramp_name)
            assert linked_from(material, ramp.inputs["Fac"]) == [window.outputs["Result"]]

    def test_the_window_starts_wide_open(self, material):
        window = node_named(material, "Window")

        assert window.clamp is True
        assert window.inputs["From Min"].default_value == 0.0
        assert window.inputs["From Max"].default_value == 1.0

    def test_the_ramps_carry_the_resampled_transfer_functions(self, material):
        preset = presets.get_preset("CT-Bone")
        for ramp_name, points in (
            ("Color Transfer", preset.color),
            ("Scalar Opacity", preset.opacity),
        ):
            elements = node_named(material, ramp_name).color_ramp.elements
            expected = presets.resample(points, *CT_HU_RANGE)

            assert len(elements) == len(expected)
            assert [element.position for element in elements] == pytest.approx(
                [position for position, _ in expected]
            )

    def test_colours_are_converted_out_of_srgb(self, material):
        elements = node_named(material, "Color Transfer").color_ramp.elements
        expected = presets.resample(presets.get_preset("CT-Bone").color, *CT_HU_RANGE)

        for element, (_, srgb) in zip(elements, expected):
            assert element.color[:3] == pytest.approx(
                tuple(presets.srgb_to_linear(value) for value in srgb)
            )

    def test_opacity_is_written_to_the_alpha_channel_unconverted(self, material):
        elements = node_named(material, "Scalar Opacity").color_ramp.elements
        expected = presets.resample(presets.get_preset("CT-Bone").opacity, *CT_HU_RANGE)

        for element, (_, values) in zip(elements, expected):
            assert element.color[3] == pytest.approx(values[0])

    def test_density_is_the_opacity_scaled_by_the_density_input(self, material):
        opacity = node_named(material, "Scalar Opacity")
        density = node_named(material, "Density Scale")
        principled = next(
            node
            for node in material.node_tree.nodes
            if node.bl_idname == "ShaderNodeVolumePrincipled"
        )

        assert density.operation == "MULTIPLY"
        assert density.inputs[1].default_value == pytest.approx(200.0)
        assert linked_from(material, density.inputs[0]) == [opacity.outputs["Alpha"]]
        assert linked_from(material, principled.inputs["Density"]) == [density.outputs["Value"]]

    def test_the_grid_is_not_applied_twice(self, material):
        # Principled Volume multiplies Density by its named grid, which would
        # apply the raw voxel value on top of the opacity function.
        principled = next(
            node
            for node in material.node_tree.nodes
            if node.bl_idname == "ShaderNodeVolumePrincipled"
        )
        assert principled.inputs["Density Attribute"].default_value == ""

    def test_emission_follows_the_opacity_so_empty_space_stays_dark(self, material):
        # Cycles does not scale emission by density, so an unmasked emission
        # colour would make the whole bounding box glow.
        emission = node_named(material, "Emission Color")
        color_ramp = node_named(material, "Color Transfer")
        opacity = node_named(material, "Scalar Opacity")

        assert emission.operation == "SCALE"
        assert linked_from(material, emission.inputs[0]) == [color_ramp.outputs["Color"]]
        assert linked_from(material, emission.inputs["Scale"]) == [opacity.outputs["Alpha"]]

    def test_the_shader_reaches_the_material_output(self, material):
        principled = next(
            node
            for node in material.node_tree.nodes
            if node.bl_idname == "ShaderNodeVolumePrincipled"
        )
        output = next(
            node
            for node in material.node_tree.nodes
            if node.bl_idname == "ShaderNodeOutputMaterial"
        )

        assert material.use_nodes is True
        assert linked_from(material, output.inputs["Volume"]) == [principled.outputs["Volume"]]
        assert linked_from(material, principled.inputs["Color"]) == [
            node_named(material, "Color Transfer").outputs["Color"]
        ]

    def test_slicer_shading_parameters_are_recorded_for_reference(self, material):
        preset = presets.get_preset("CT-Bone")

        assert material.get("medblend_preset") == "CT-Bone"
        assert material.get("medblend_slicer_ambient") == pytest.approx(preset.ambient)
        assert material.get("medblend_slicer_shade") == preset.shade

    @pytest.mark.parametrize("preset", presets.VOLUME_PRESETS, ids=lambda p: p.name)
    def test_every_preset_builds(self, materials, preset):
        material = volume_materials.get_preset_material(preset, preset.window)

        assert material.use_nodes is True
        assert len(material.node_tree.links) == 10


class TestMaterialReuse:
    def test_the_same_settings_hand_back_the_same_material(self, materials):
        preset = presets.get_preset("CT-Bone")
        first = volume_materials.get_preset_material(preset, CT_HU_RANGE, 200.0, 1.0)
        second = volume_materials.get_preset_material(preset, CT_HU_RANGE, 200.0, 1.0)

        assert first is second
        assert len(materials) == 1

    @pytest.mark.parametrize(
        "window,density,emission",
        [
            ((-1000.0, 3071.0), 200.0, 1.0),
            (CT_HU_RANGE, 400.0, 1.0),
            (CT_HU_RANGE, 200.0, 0.5),
        ],
        ids=["window", "density", "emission"],
    )
    def test_different_settings_get_their_own_material(self, materials, window, density, emission):
        # Retinting the shared material in place would change how a volume
        # already in the scene renders.
        preset = presets.get_preset("CT-Bone")
        first = volume_materials.get_preset_material(preset, CT_HU_RANGE, 200.0, 1.0)
        second = volume_materials.get_preset_material(preset, window, density, emission)

        assert first is not second
        assert len(materials) == 2

    def test_names_stay_within_blenders_limit(self, materials):
        for preset in presets.VOLUME_PRESETS:
            material = volume_materials.get_preset_material(preset, preset.window)
            assert len(material.name) <= volume_materials._MAX_DATABLOCK_NAME

    def test_reapplying_does_not_accumulate_copies(self, materials):
        preset = presets.get_preset("CT-Lung")
        for _ in range(5):
            volume_materials.get_preset_material(preset, CT_HU_RANGE)
        assert len(materials) == 1


class TestApplyVolumePreset:
    def test_a_ct_preset_uses_the_volumes_hounsfield_range(self, materials):
        obj = ct_volume()
        material = volume_materials.apply_volume_preset(obj, "CT-Bone")

        assert obj.data.materials == [material]
        assert material.get("medblend_preset_window") == pytest.approx(list(CT_HU_RANGE))

    def test_an_mr_volume_stretches_the_preset_over_its_data_range(self, materials):
        obj = FakeVolume(
            medblend_intensity_min=0.0,
            medblend_intensity_max=4095.0,
            medblend_modality="MR",
        )
        material = volume_materials.apply_volume_preset(obj, "MR-Default")

        assert material.get("medblend_preset_window") == pytest.approx(
            list(presets.get_preset("MR-Default").window)
        )

    def test_a_volume_without_a_recorded_range_still_gets_a_material(self, materials):
        material = volume_materials.apply_volume_preset(FakeVolume(), "CT-Bone")

        assert material is not None
        assert material.get("medblend_preset_window") == pytest.approx(
            list(presets.get_preset("CT-Bone").window)
        )

    def test_the_preset_replaces_the_material_already_in_the_slot(self, materials):
        # Only the first slot is used when rendering a volume, so appending
        # would leave the old material in charge.
        obj = ct_volume()
        obj.data.materials.append("Image Material")
        material = volume_materials.apply_volume_preset(obj, "CT-Bone")

        assert obj.data.materials == [material]

    def test_errors_are_routed_to_the_caller(self, materials, monkeypatch):
        shown = []
        monkeypatch.setattr(volume_materials, "show_message_box", lambda *a, **k: shown.append(a))
        errors = []

        assert volume_materials.apply_volume_preset(ct_volume(), "nope", on_error=errors.append) is None
        assert len(errors) == 1 and "nope" in errors[0]
        assert shown == []

    @pytest.mark.parametrize(
        "obj", [None, type("Mesh", (), {"type": "MESH"})()], ids=["missing", "not-a-volume"]
    )
    def test_only_volumes_can_take_a_preset(self, materials, obj):
        errors = []

        assert volume_materials.apply_volume_preset(obj, "CT-Bone", on_error=errors.append) is None
        assert len(errors) == 1

    def test_a_build_failure_is_reported_rather_than_raised(self, materials, monkeypatch):
        def explode(*_args, **_kwargs):
            raise RuntimeError("no such node type")

        monkeypatch.setattr(volume_materials, "build_preset_node_tree", explode)
        errors = []

        assert volume_materials.apply_volume_preset(ct_volume(), "CT-Bone", on_error=errors.append) is None
        assert len(errors) == 1 and "no such node type" in errors[0]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestPropertyRegistration:
    @pytest.mark.parametrize(
        "cls",
        [
            MedBlend.MEDBLEND_Preferences,
            MedBlend.MEDBLEND_VolumePresetSettings,
            MedBlend.MEDBLEND_OT_Apply_Volume_Preset,
            MedBlend.MEDBLEND_OT_Load_Ct,
        ],
        ids=lambda cls: cls.__name__,
    )
    def test_properties_are_declared_as_objects_blender_can_register(self, cls):
        # Blender reads bpy.props declarations out of __annotations__ and
        # silently ignores anything that is not a property, so a deferred
        # (PEP 563) annotation would drop every property in the module.
        annotations = cls.__dict__.get("__annotations__", {})

        assert annotations
        for name, value in annotations.items():
            assert not isinstance(value, str), f"{cls.__name__}.{name} is a stringified annotation"

    def test_the_preset_operators_share_the_panel_settings(self):
        settings = set(MedBlend.MEDBLEND_VolumePresetSettings.__dict__["__annotations__"])

        assert settings == {"preset", "fit_mode", "density_scale", "emission_strength"}
        assert settings <= set(MedBlend.MEDBLEND_OT_Apply_Volume_Preset.__dict__["__annotations__"])
        assert settings <= set(MedBlend.MEDBLEND_OT_Load_Ct.__dict__["__annotations__"])

    def test_the_import_operator_defaults_to_the_existing_material(self):
        preset = MedBlend.MEDBLEND_OT_Load_Ct.__dict__["__annotations__"]["preset"]
        assert preset.keywords["default"] == presets.NO_PRESET

    def test_the_panel_operator_defaults_to_a_real_preset(self):
        preset = MedBlend.MEDBLEND_OT_Apply_Volume_Preset.__dict__["__annotations__"]["preset"]
        assert presets.get_preset(preset.keywords["default"]) is not None

    def test_the_preset_classes_are_registered(self):
        assert MedBlend.MEDBLEND_VolumePresetSettings in MedBlend.classes
        assert MedBlend.MEDBLEND_OT_Apply_Volume_Preset in MedBlend.classes
        # The settings group has to exist before the Scene pointer to it.
        assert MedBlend.classes.index(MedBlend.MEDBLEND_VolumePresetSettings) < MedBlend.classes.index(
            MedBlend.MEDBLEND_OT_Apply_Volume_Preset
        )
