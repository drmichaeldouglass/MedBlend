"""Shared UI helpers."""

from __future__ import annotations

import bpy


def show_message(message: str, *, title: str = "MedBlend", icon: str = 'INFO') -> None:
    """Display *message* to the user in a popup."""

    lines = [line.strip() for line in message.splitlines() if line.strip()]

    def draw(self, context):  # pragma: no cover - requires Blender UI
        for line in lines:
            self.layout.label(text=line)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


__all__ = ["show_message"]
