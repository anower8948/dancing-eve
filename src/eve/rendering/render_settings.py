"""Rendering options."""

from __future__ import annotations

from dataclasses import dataclass

# Vertical extent of the scene (in character units) that fits the window, and the window
# aspect ratio (width / height). Chosen so arms raised overhead and side drift stay in view.
VIEW_HEIGHT = 2.25
WINDOW_ASPECT = 1.0  # wide enough for arms raised sideways while side-stepping


@dataclass
class RenderSettings:
    multisamples: int = 4  # MSAA samples (0 disables)
    field_of_view: float = 20.0  # vertical degrees; narrow = flattering, near-orthographic
    show_shadow: bool = True
    target_fps: int = 60
