"""Renderer abstraction: pose in, premultiplied-alpha image out.

The desktop window only ever sees ``FrameImage``; it never imports the 3D engine. A
different engine (or a pre-rendered sprite renderer) can replace Panda3D by implementing
``CharacterRenderer``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np


@dataclass
class FrameImage:
    """Top-down rows, BGRA byte order (== QImage.Format_ARGB32_Premultiplied on
    little-endian machines), premultiplied alpha."""

    pixels: np.ndarray  # (height, width, 4) uint8, C-contiguous
    width: int
    height: int

    @property
    def stride(self) -> int:
        return self.width * 4


class CharacterRenderer(ABC):
    @abstractmethod
    def initialize(self, width: int, height: int) -> None:
        """Create graphics resources for a ``width`` × ``height`` pixel frame."""

    @abstractmethod
    def resize(self, width: int, height: int) -> None: ...

    @abstractmethod
    def render(self, pose: np.ndarray) -> FrameImage:
        """Render one frame for ``pose`` (see character_rig.Ch)."""

    @abstractmethod
    def dispose(self) -> None:
        """Release all graphics resources. Idempotent."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable renderer/driver info for diagnostics."""
