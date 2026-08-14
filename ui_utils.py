"""UI helpers for MedBlend."""

from __future__ import annotations

import bpy


def show_message_box(message: str = "", title: str = "Message", icon: str = "INFO") -> None:
    """Show a popup, falling back to the console when no window is available.

    ``popup_menu`` requires an interactive window manager, so it raises in
    background/headless runs. Import failures must still be reported there
    rather than masking the original problem with a UI error.
    """

    def draw(self, _context):
        for line in str(message).splitlines() or [""]:
            self.layout.label(text=line)

    try:
        bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)
    except Exception:
        print(f"MedBlend [{title}] {message}")
