"""Utilities for loading optional third-party dependencies."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping


@dataclass(frozen=True)
class Dependency:
    """Metadata describing an optional runtime dependency."""

    import_name: str
    display_name: str


_DEPENDENCIES: Mapping[str, Dependency] = {
    "numpy": Dependency("numpy", "NumPy"),
    "pydicom": Dependency("pydicom", "pydicom"),
    "pyopenvdb": Dependency("pyopenvdb", "PyOpenVDB"),
    "platipy": Dependency("platipy", "platipy"),
    "SimpleITK": Dependency("SimpleITK", "SimpleITK"),
}


class DependencyError(RuntimeError):
    """Raised when one or more dependencies are unavailable."""

    def __init__(self, missing: Iterable[str]):
        self.missing: List[str] = sorted(set(missing))
        message = "Missing dependencies: " + ", ".join(self.missing)
        super().__init__(message)


_loaded_modules: MutableMapping[str, object] = {}


def _load_module(name: str) -> object:
    if name not in _DEPENDENCIES:
        raise KeyError(f"Unknown dependency '{name}'.")

    module = _loaded_modules.get(name)
    if module is not None:
        return module

    meta = _DEPENDENCIES[name]
    module = importlib.import_module(meta.import_name)
    _loaded_modules[name] = module
    return module


def ensure_dependencies(*names: str) -> Dict[str, object]:
    """Return the imported modules for *names* or raise :class:`DependencyError`."""

    modules: Dict[str, object] = {}
    missing: List[str] = []
    for name in names:
        try:
            modules[name] = _load_module(name)
        except Exception:  # pragma: no cover - Blender handles presentation
            display_name = _DEPENDENCIES.get(name, Dependency(name, name)).display_name
            missing.append(display_name)
    if missing:
        raise DependencyError(missing)
    return modules


def find_missing(names: Iterable[str]) -> List[str]:
    """Return a list of human readable names for missing *names*."""

    missing: List[str] = []
    for name in names:
        try:
            _load_module(name)
        except Exception:
            display_name = _DEPENDENCIES.get(name, Dependency(name, name)).display_name
            missing.append(display_name)
    return missing


__all__ = [
    "DependencyError",
    "ensure_dependencies",
    "find_missing",
]
