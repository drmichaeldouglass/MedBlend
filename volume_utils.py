"""Helpers for writing volume data to VDB."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

import bpy
import numpy as np
from mathutils import Matrix

from .ui_utils import show_message_box


def _default_temp_base_dir() -> Path:
    temp_dir = bpy.app.tempdir
    if temp_dir:
        return Path(temp_dir)

    cache_dir = getattr(bpy.app, "cachedir", "")
    if cache_dir:
        return Path(cache_dir)

    return Path.cwd()


def _get_vdb_temp_dir() -> Optional[Path]:
    try:
        addon = bpy.context.preferences.addons.get(__package__)
        if not addon:
            return None
        prefs = addon.preferences
        if not getattr(prefs, "vdb_temp_dir", ""):
            return None
        resolved = bpy.path.abspath(prefs.vdb_temp_dir)
        return Path(resolved)
    except Exception:
        # Preferences are unavailable in some background/headless contexts.
        return None


#: Device names that cannot be opened as files on Windows, with or without an
#: extension. An ROI legitimately called "CON" or "AUX" would otherwise write
#: to the console/device rather than to a file.
_WINDOWS_RESERVED_STEMS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{digit}" for digit in range(1, 10)}
    | {f"LPT{digit}" for digit in range(1, 10)}
)

#: Leaves room for the "_<counter>" that _unique_path appends, well inside the
#: 255-byte component limit that every filesystem MedBlend runs on enforces.
_MAX_STEM_BYTES = 120


def _sanitize_filename(name: str) -> str:
    """Make ``name`` safe to use as a file name, preserving its extension.

    Only the stem is rewritten. Sanitising the whole name would let an ROI
    called ``...`` collapse to a file with no ``.vdb`` extension at all, which
    Blender then cannot recognise as a volume.
    """

    stem, dot, suffix = name.rpartition(".")
    # Only split off something that is actually an extension. An ROI called
    # "../../etc/passwd" has a trailing dot-segment that is not one, and
    # carrying it through unsanitised would put separators back in the name.
    if not dot or not suffix.isalnum() or len(suffix) > 8:
        stem, suffix = name, ""

    cleaned = "".join(char if (char.isalnum() or char in "._- ") else "_" for char in stem)
    # UTF-8 byte limits matter for non-ASCII ROI names. Ignore only a partial
    # trailing code point when truncating, preserving every complete character.
    cleaned_bytes = cleaned.strip(". ").encode("utf-8")[:_MAX_STEM_BYTES]
    cleaned = cleaned_bytes.decode("utf-8", errors="ignore").strip(". ")
    if not cleaned:
        cleaned = "volume"
    elif cleaned.split(".", 1)[0].rstrip(" ").upper() in _WINDOWS_RESERVED_STEMS:
        # Windows reserves the device component even with multiple suffixes.
        cleaned = f"_volume_{cleaned}"

    return f"{cleaned}.{suffix}" if suffix else cleaned


def _unique_path(base_dir: Path, target_name: str) -> Path:
    """Return a path that does not overwrite an existing VDB file.

    Blender volume objects read their data from disk, so overwriting a file
    from a previous import would silently change the contents of volumes
    already in the scene.
    """

    candidate = base_dir / target_name
    if not candidate.exists():
        return candidate

    stem = candidate.stem
    suffix = candidate.suffix
    counter = 1
    while True:
        candidate = base_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


#: Custom property marking a Volume datablock whose VDB file MedBlend wrote,
#: so saving a scene only relocates files this add-on is responsible for.
GENERATED_VDB_KEY = "medblend_generated_vdb"


def blend_vdb_dir(blend_path) -> Optional[Path]:
    """The folder kept beside a saved .blend for its generated VDB files.

    ``scan.blend`` gets ``scan_vdb/`` next to it, so the pair can be moved or
    archived together and Blender's relative paths keep resolving.
    """

    if not blend_path:
        return None
    blend_path = Path(str(blend_path))
    return blend_path.parent / f"{blend_path.stem}_vdb"


def _is_inside(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def relocate_session_volumes(blend_path) -> list[Path]:
    """Copy generated VDB files out of the session temp directory on save.

    Blender volume objects read their voxels from the VDB file on disk, and
    Blender deletes its session temporary directory on exit. A scene imported
    before its first save therefore pointed at files that were gone by the
    next time it was opened, leaving every volume empty. Called from a
    ``save_pre`` handler with the path being saved to, this copies each such
    file into :func:`blend_vdb_dir` and repoints the datablock, so the paths
    written into the .blend outlive the session.

    Returns the new file paths. A file that cannot be copied is left where it
    is and reported, rather than failing the save.
    """

    destination_dir = blend_vdb_dir(blend_path)
    session_dir = getattr(bpy.app, "tempdir", "")
    if destination_dir is None or not session_dir:
        return []

    try:
        session_dir = Path(session_dir).resolve()
        # Saves into the session directory itself are Blender's own scratch
        # files; relocating next to those would not outlive the session.
        if _is_inside(Path(str(blend_path)).resolve(), session_dir):
            return []
    except OSError:
        return []

    relocated: dict[Path, Path] = {}
    errors: list[str] = []
    for volume in list(getattr(bpy.data, "volumes", ())):
        try:
            if not volume.get(GENERATED_VDB_KEY) or getattr(volume, "library", None):
                continue
            source = Path(bpy.path.abspath(volume.filepath)).resolve()
            if not _is_inside(source, session_dir) or not source.is_file():
                continue

            destination = relocated.get(source)
            if destination is None:
                destination_dir.mkdir(parents=True, exist_ok=True)
                destination = _unique_path(destination_dir, source.name)
                shutil.copy2(source, destination)
                relocated[source] = destination
            volume.filepath = str(destination)
        except Exception as exc:
            errors.append(f"{getattr(volume, 'name', '?')}: {exc}")

    if errors:
        show_message_box(
            "Some volume files could not be copied next to the .blend file and "
            "will be missing when it is reopened: " + "; ".join(errors[:3]),
            "Warning",
            "ERROR",
        )
    return list(relocated.values())


def resolve_temp_path(target_name: str) -> Path:
    # A scene that is already saved gets its volumes written straight into the
    # folder beside it; an unsaved one uses the session directory and is moved
    # there by relocate_session_volumes on its first save.
    base_dir = (
        _get_vdb_temp_dir()
        or blend_vdb_dir(getattr(bpy.data, "filepath", ""))
        or _default_temp_base_dir()
    )

    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        show_message_box(
            f"Failed to create VDB directory '{base_dir}': {exc}",
            "Error",
            "ERROR",
        )
        base_dir = _default_temp_base_dir()
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except Exception as fallback_exc:
            raise RuntimeError(
                f"Failed to create fallback VDB directory '{base_dir}': {fallback_exc}"
            ) from fallback_exc

    return _unique_path(base_dir, _sanitize_filename(target_name))


#: Custom property recording the order CT volumes were imported in.
CT_IMPORT_INDEX_KEY = "medblend_ct_import_index"


def next_ct_import_index() -> int:
    """Return an import index one past the highest already in the scene."""

    highest = 0
    for obj in bpy.data.objects:
        try:
            highest = max(highest, int(obj.get(CT_IMPORT_INDEX_KEY, 0)))
        except (TypeError, ValueError):
            continue
    return highest + 1


def find_ct_anchor(frame_uid: str) -> Optional[bpy.types.Object]:
    """Return the most recently imported CT object matching ``frame_uid``.

    ``bpy.data.objects`` is ordered by name rather than by creation, and the
    names MedBlend generates do not sort in import order past nine imports
    ("CT_10" precedes "CT_9"), so the recorded import index decides instead.
    """

    ct_candidates = [obj for obj in bpy.data.objects if bool(obj.get("medblend_is_ct"))]
    if frame_uid:
        ct_candidates = [
            obj for obj in ct_candidates if obj.get("medblend_frame_of_reference_uid", "") == frame_uid
        ]
    if not ct_candidates:
        return None

    def _import_order(entry) -> tuple[int, int]:
        position, obj = entry
        try:
            return int(obj.get(CT_IMPORT_INDEX_KEY, 0)), position
        except (TypeError, ValueError):
            return 0, position

    # Position breaks ties for CT objects carrying no index - volumes imported
    # by an older MedBlend, or tagged by hand.
    return max(enumerate(ct_candidates), key=_import_order)[1]


def _link_object_to_context_collection(obj: bpy.types.Object) -> None:
    collection = bpy.context.collection or bpy.context.scene.collection
    collection.objects.link(obj)
    # Making the new object active and selected is a convenience, not part of
    # the import. Both raise for a collection excluded from the view layer, and
    # letting that escape would make the caller treat a written volume as a
    # failure - and re-import the same file through the operator fallback.
    try:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
    except (RuntimeError, ReferenceError, AttributeError):
        pass


def set_object_patient_transform(
    obj: bpy.types.Object,
    origin_mm: Sequence[float],
    slice_dir: Sequence[float],
    row_dir: Sequence[float],
    col_dir: Sequence[float],
) -> None:
    rot = Matrix(
        (
            (float(slice_dir[0]), float(row_dir[0]), float(col_dir[0]), 0.0),
            (float(slice_dir[1]), float(row_dir[1]), float(col_dir[1]), 0.0),
            (float(slice_dir[2]), float(row_dir[2]), float(col_dir[2]), 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )
    rot.translation = (
        float(origin_mm[0]) / 1000.0,
        float(origin_mm[1]) / 1000.0,
        float(origin_mm[2]) / 1000.0,
    )
    obj.matrix_world = rot


def _affine_matrix(linear, translation) -> Matrix:
    """Build a 4x4 ``Matrix`` from a 3x3 linear part and a translation."""

    matrix = Matrix(
        (
            (float(linear[0, 0]), float(linear[0, 1]), float(linear[0, 2]), 0.0),
            (float(linear[1, 0]), float(linear[1, 1]), float(linear[1, 2]), 0.0),
            (float(linear[2, 0]), float(linear[2, 1]), float(linear[2, 2]), 0.0),
            (0.0, 0.0, 0.0, 1.0),
        )
    )
    matrix.translation = tuple(float(value) for value in translation)
    return matrix


def ct_patient_to_world(ct_obj: bpy.types.Object) -> Optional[Matrix]:
    """Return the matrix taking DICOM patient coordinates, in metres, to world space.

    The mapping goes through ``ct_obj``'s current world matrix, so anything
    placed with it stays registered to the CT even after the user has moved,
    rotated or scaled the CT object. Returns ``None`` when the CT carries no
    recorded geometry - its placement failed, or it predates these properties.
    """

    ct_basis_flat = ct_obj.get("medblend_ct_basis_mm")
    if not ct_basis_flat or len(ct_basis_flat) != 9:
        return None

    try:
        ct_basis = np.asarray(ct_basis_flat, dtype=float).reshape((3, 3))
        ct_origin = np.asarray(ct_obj.get("medblend_ct_origin_mm", [0.0, 0.0, 0.0]), dtype=float)
        ct_spacing = np.asarray(ct_obj.get("medblend_ct_spacing_mm", [1.0, 1.0, 1.0]), dtype=float)
        if ct_origin.shape != (3,) or ct_spacing.shape != (3,) or np.any(ct_spacing <= 0):
            return None

        # Patient millimetres -> CT index -> CT object-local metres. Patient
        # input is in metres here, so the millimetre scale cancels out of the
        # linear part and only remains on the origin.
        mm_to_local = np.diag(ct_spacing / 1000.0) @ np.linalg.inv(ct_basis)
        linear = mm_to_local * 1000.0
        translation = -(mm_to_local @ ct_origin)
        if not (np.all(np.isfinite(linear)) and np.all(np.isfinite(translation))):
            return None
        return ct_obj.matrix_world @ _affine_matrix(linear, translation)
    except Exception:
        return None


def align_object_to_ct_frame(
    obj: bpy.types.Object,
    ct_obj: bpy.types.Object,
    origin_mm: Sequence[float],
    basis_mm: Sequence[Sequence[float]],
    spacing_mm: Sequence[float],
) -> bool:
    patient_to_world = ct_patient_to_world(ct_obj)
    if patient_to_world is None:
        return False

    try:
        source_origin = np.asarray(origin_mm, dtype=float)
        source_basis = np.asarray(basis_mm, dtype=float).reshape((3, 3))
        source_spacing = np.asarray(spacing_mm, dtype=float)
        if np.any(source_spacing <= 0):
            return False

        # VDB-local metres -> source index -> patient metres. The grid bakes
        # spacing into its local coordinates, so dividing it back out leaves
        # the basis directions with the millimetre scale cancelled.
        linear = source_basis @ np.diag(1.0 / source_spacing)
        local_to_patient = _affine_matrix(linear, source_origin / 1000.0)
        obj.matrix_world = patient_to_world @ local_to_patient
    except Exception:
        return False

    return True


def _new_volume_data(output_path: Path) -> bpy.types.Volume:
    """Create a Volume datablock pointing at ``output_path``.

    ``bpy.data.volumes`` does not expose ``load()`` on every Blender build, so
    fall back to creating an empty Volume and pointing its ``filepath`` at the
    file - Blender reads the grids lazily from there either way.
    """

    loader = getattr(bpy.data.volumes, "load", None)
    if callable(loader):
        try:
            return loader(str(output_path))
        except Exception:
            pass

    volume_data = bpy.data.volumes.new(output_path.stem)
    volume_data.filepath = str(output_path)
    return volume_data


def _import_volume_data_api(output_path: Path) -> bpy.types.Object:
    """Import a VDB file using Blender data API to avoid context-sensitive operators."""

    volume_data = _new_volume_data(output_path)
    obj = bpy.data.objects.new(output_path.stem, volume_data)
    _link_object_to_context_collection(obj)
    return obj


def _import_volume_operator_fallback(output_path: Path) -> bpy.types.Object:
    """Fallback for Blender builds where data API loading is unavailable."""

    before_names = {obj.name for obj in bpy.data.objects}
    result = bpy.ops.object.volume_import(
        filepath=str(output_path),
        directory=str(output_path.parent),
        files=[{"name": output_path.name}],
    )
    if "FINISHED" not in result:
        raise RuntimeError("Volume import operator did not finish successfully")

    active_obj = bpy.context.view_layer.objects.active
    if active_obj and active_obj.name not in before_names:
        return active_obj

    # Fall back to matching by object type and expected base name.
    candidates = [obj for obj in bpy.data.objects if obj.name not in before_names and obj.type == "VOLUME"]
    if candidates:
        return candidates[-1]
    raise RuntimeError("Unable to resolve imported volume object from operator fallback")


def _import_openvdb_module():
    last_exc = None
    for module_name in ("openvdb", "pyopenvdb"):
        try:
            return __import__(module_name)
        except Exception as exc:
            last_exc = exc

    raise ModuleNotFoundError(
        "Neither 'openvdb' nor 'pyopenvdb' could be imported. "
        "Ensure Blender ships a compatible OpenVDB Python module."
    ) from last_exc


def write_vdb_volume(
    array,
    spacing: Sequence[float],
    target_name: str,
    on_error: Optional[Callable[[str], None]] = None,
) -> Optional[Tuple[Path, bpy.types.Object]]:
    """Write ``array`` to a VDB file and return ``(path, imported object)``.

    ``on_error`` receives the failure message instead of a popup being shown.
    A caller importing many volumes in a loop - one per ROI of a structure set
    - can then collect the failures and report them once, rather than stacking
    a separate dialog for every ROI that failed.
    """

    def fail(message: str, title: str = "Error") -> None:
        if on_error is not None:
            on_error(message)
        else:
            show_message_box(message, title, "ERROR")
        return None

    if len(spacing) != 3:
        return fail(f"Expected 3 spacing values (x, y, z), got {len(spacing)}.")
    if any(value <= 0 for value in spacing):
        return fail("Spacing values must be positive to create a VDB volume.")

    # FloatGrid stores single precision; converting up front halves peak memory
    # and avoids dtype-strict copyFromArray builds rejecting float64.
    try:
        voxels = np.ascontiguousarray(array, dtype=np.float32)
    except Exception as exc:
        return fail(f"Voxel data could not be converted for VDB export: {exc}")
    if voxels.ndim != 3 or voxels.size == 0:
        return fail(f"Expected a non-empty 3D voxel array, got shape {tuple(voxels.shape)}.")

    try:
        openvdb = _import_openvdb_module()
    except Exception as exc:
        return fail(f"openvdb is not available: {exc}", "Missing Dependency")

    try:
        grid = openvdb.FloatGrid()
        grid.copyFromArray(voxels)
        # copyFromArray activates every voxel, including the empty background
        # that dominates structure masks and air around a CT. Pruning collapses
        # those uniform regions, which shrinks the file and speeds up rendering.
        try:
            grid.prune(0.0)
        except Exception:
            pass
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

        output_path = resolve_temp_path(target_name)
        openvdb.write(str(output_path), grid)

        try:
            imported_obj = _import_volume_data_api(output_path)
        except Exception:
            imported_obj = _import_volume_operator_fallback(output_path)

        try:
            imported_obj.data[GENERATED_VDB_KEY] = True
            # A file written beside a saved .blend is referenced relative to
            # it, so the two can be moved together. Blender only rewrites
            # absolute paths on Save As, not on a plain save.
            blend_dir = blend_vdb_dir(getattr(bpy.data, "filepath", ""))
            if blend_dir is not None and _is_inside(output_path.resolve(), blend_dir.resolve()):
                imported_obj.data.filepath = bpy.path.relpath(str(output_path))
        except Exception:
            # Only costs portability of the saved scene, not the import.
            pass

        return output_path, imported_obj
    except Exception as exc:
        return fail(f"Failed to create VDB volume: {exc}")
