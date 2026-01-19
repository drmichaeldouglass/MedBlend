"""UI helpers for MedBlend."""

from __future__ import annotations

import bpy


def show_message_box(message: str = "", title: str = "Message", icon: str = "INFO") -> None:
    def draw(self, _context):
        self.layout.label(text=message)

    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)
