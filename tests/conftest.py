"""Test bootstrap: import MedBlend outside Blender using lightweight stubs.

The add-on modules import ``bpy``/``mathutils`` at module scope, which only
exist inside Blender. ``tests/stubs`` provides just enough of that surface for
the pure DICOM/geometry code to be imported and exercised by pytest.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
ADDON_DIR = TESTS_DIR.parent

# Stubs must resolve before anything else on the path.
sys.path.insert(0, str(TESTS_DIR / "stubs"))


def _load_addon_package(name: str = "MedBlend"):
    """Import the add-on as ``name`` regardless of the checkout folder name."""

    if name in sys.modules:
        return sys.modules[name]

    spec = importlib.util.spec_from_file_location(
        name,
        ADDON_DIR / "__init__.py",
        submodule_search_locations=[str(ADDON_DIR)],
    )
    module = importlib.util.module_from_spec(spec)
    # Register before executing so the package's own relative imports resolve.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load_addon_package()
