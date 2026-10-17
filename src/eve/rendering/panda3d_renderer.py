"""Panda3D offscreen renderer.

Panda3D renders into an offscreen framebuffer with an alpha channel; the image is copied
to RAM each frame and painted by the Qt companion window, which owns transparency,
always-on-top and input. This avoids embedding a native GL window inside Qt — the least
portable part of a Panda3D+Qt integration — and works identically on macOS, Windows and
X11/XWayland. Measured readback cost on an Apple M2: ~0.5 ms/frame at 320×400.

Must be used from the GUI (main) thread.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
from panda3d.core import (
    FrameBufferProperties,
    GraphicsEngine,
    GraphicsOutput,
    GraphicsPipe,
    GraphicsPipeSelection,
    Texture,
    WindowProperties,
    loadPrcFileData,
)

from eve.character.character_config import CharacterConfig
from eve.character.eve_character import EveCharacter
from eve.rendering.render_settings import RenderSettings
from eve.rendering.renderer_interface import CharacterRenderer, FrameImage
from eve.rendering.scene_manager import SceneManager

log = logging.getLogger(__name__)

_PRC_LOADED = False


def _configure_panda() -> None:
    global _PRC_LOADED
    if _PRC_LOADED:
        return
    if getattr(sys, "frozen", False):
        # Packaged app: the GL display module sits next to panda3d.core.
        import panda3d.core as p3d_core

        loadPrcFileData("eve-frozen", f"plugin-path {Path(p3d_core.__file__).parent.as_posix()}")
    loadPrcFileData(
        "eve",
        "\n".join(
            [
                "window-type none",
                "audio-library-name null",
                "sync-video false",
                "notify-level warning",
                "notify-level-glgsg warning",
                "default-directnotify-level warning",
                "gl-check-errors false",
                "model-cache-dir",
            ]
        ),
    )
    _PRC_LOADED = True


class Panda3DRenderer(CharacterRenderer):
    def __init__(self, settings: RenderSettings | None = None, character: CharacterConfig | None = None) -> None:
        self.settings = settings or RenderSettings()
        self.character_config = character or CharacterConfig()
        self._engine: GraphicsEngine | None = None
        self._pipe = None
        self._buffer = None
        self._texture: Texture | None = None
        self.scene: SceneManager | None = None
        self.character: EveCharacter | None = None
        self._frame: np.ndarray | None = None
        self.width = self.height = 0
        self._description = "Panda3D (not initialised)"

    # -- lifecycle ------------------------------------------------------------------------
    def initialize(self, width: int, height: int) -> None:
        _configure_panda()
        self._engine = GraphicsEngine.getGlobalPtr()
        self._pipe = GraphicsPipeSelection.getGlobalPtr().makeDefaultPipe()
        if self._pipe is None:
            raise RuntimeError("Panda3D could not open a graphics pipe (no OpenGL driver?)")
        self.scene = SceneManager(self.settings)
        self.character = EveCharacter(self.scene.scene, self.character_config)
        self._create_buffer(width, height)
        gsg = self._buffer.getGsg()
        self._description = (
            f"Panda3D {self._pipe.getInterfaceName()} — {gsg.getDriverRenderer()} "
            f"({gsg.getDriverVersion()}), MSAA {self._buffer.getFbProperties().getMultisamples()}x"
        )
        log.info("renderer: %s", self._description)

    def _create_buffer(self, width: int, height: int) -> None:
        assert self._engine is not None and self.scene is not None
        width, height = max(16, int(width)), max(16, int(height))
        fbp = FrameBufferProperties()
        fbp.setRgbaBits(8, 8, 8, 8)
        fbp.setDepthBits(24)
        if self.settings.multisamples > 0:
            fbp.setMultisamples(self.settings.multisamples)
        buffer = self._engine.makeOutput(
            self._pipe, "eve-offscreen", -2, fbp, WindowProperties.size(width, height), GraphicsPipe.BF_refuse_window
        )
        if buffer is None and self.settings.multisamples > 0:
            log.warning("MSAA offscreen buffer unavailable; retrying without antialiasing")
            fbp.setMultisamples(0)
            buffer = self._engine.makeOutput(
                self._pipe,
                "eve-offscreen",
                -2,
                fbp,
                WindowProperties.size(width, height),
                GraphicsPipe.BF_refuse_window,
            )
        if buffer is None:
            raise RuntimeError("Panda3D could not create an offscreen buffer")
        texture = Texture("eve-frame")
        buffer.addRenderTexture(texture, GraphicsOutput.RTM_copy_ram)
        buffer.setClearColorActive(True)
        buffer.setClearColor((0.0, 0.0, 0.0, 0.0))
        region = buffer.makeDisplayRegion()
        region.setCamera(self.scene.camera)
        self.scene.set_aspect(width, height)
        self._buffer = buffer
        self._texture = texture
        self.width, self.height = width, height
        self._frame = np.zeros((height, width, 4), dtype=np.uint8)

    def resize(self, width: int, height: int) -> None:
        if (int(width), int(height)) == (self.width, self.height) or self._engine is None:
            return
        if self._buffer is not None:
            self._engine.removeWindow(self._buffer)
            self._buffer = None
        self._create_buffer(width, height)

    def dispose(self) -> None:
        if self._engine is not None and self._buffer is not None:
            self._engine.removeWindow(self._buffer)
            self._engine.renderFrame()  # lets Panda release GL objects
        self._buffer = None
        self._texture = None
        if self.scene is not None:
            self.scene.scene.removeNode()
        self.scene = None
        self.character = None

    # -- per frame ------------------------------------------------------------------------
    def render(self, pose: np.ndarray) -> FrameImage:
        assert self._engine is not None and self.character is not None and self._texture is not None
        assert self._frame is not None
        self.character.apply_pose(pose)
        self._engine.renderFrame()
        ram = self._texture.getRamImageAs("BGRA")
        if ram is None or len(ram) < self.width * self.height * 4:
            return FrameImage(self._frame, self.width, self.height)
        src = np.frombuffer(memoryview(ram), dtype=np.uint8).reshape(self.height, self.width, 4)
        np.copyto(self._frame, src[::-1])  # OpenGL rows are bottom-up
        return FrameImage(self._frame, self.width, self.height)

    @property
    def description(self) -> str:
        return self._description
