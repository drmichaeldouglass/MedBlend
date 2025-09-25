"""Proton therapy helper functions."""

from __future__ import annotations

from typing import Any


def is_proton_plan(dataset: Any) -> bool:
    """Return ``True`` if *dataset* describes an ion (proton) plan."""

    modality = getattr(dataset, "Modality", "")
    return modality.upper() in {"RTION", "RTIONPLAN", "ION"}


__all__ = ["is_proton_plan"]
