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
import os
import sys
from pathlib import Path
from typing import Any

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


SOFTWARE_MODULE = "p3tinydisplay"  # CPU rasteriser shipped in the Panda3D wheel
HOSTED_GL = "opengl-with-host-window"  # default GL pipe, buffer hosted by a hidden 1x1 window
MIN_TEST_COVERAGE = 0.02  # the robot covers ~19–28 % of the frame; less means a broken buffer


def pipe_candidates(platform: str | None = None, env: dict[str, str] | None = None) -> list[str | None]:
    """Display modules to try, best first. ``None`` = Panda's default (OpenGL).

    * Some drivers (notably on Windows) only create offscreen OpenGL buffers that share a
      context with a real window, so the next attempt hosts the buffer on a hidden 1×1
      window.
    * Linux adds headless EGL (works without an X server, e.g. pure Wayland or SSH).
    * Everyone falls back to the software rasteriser (VMs, Remote Desktop sessions with
      only GDI OpenGL 1.1, broken drivers). ``EVE_RENDERER=software`` forces it;
      ``EVE_RENDERER=hosted`` forces the hosted attempt (for testing).
    """
    platform = platform or sys.platform
    env = dict(os.environ) if env is None else env
    forced = env.get("EVE_RENDERER", "").lower()
    if forced == "software":
        return [SOFTWARE_MODULE]
    if forced == "hosted":
        return [HOSTED_GL]
    candidates: list[str | None] = [None, HOSTED_GL]
    if platform.startswith("linux"):
        candidates.append("p3headlessgl")
    candidates.append(SOFTWARE_MODULE)
    return candidates


class Panda3DRenderer(CharacterRenderer):
    def __init__(self, settings: RenderSettings | None = None, character: CharacterConfig | None = None) -> None:
        self.settings = settings or RenderSettings()
        self.character_config = character or CharacterConfig()
        self._engine: GraphicsEngine | None = None
        self._pipe = None
        self._buffer: Any = None
        self._texture: Texture | None = None
        self.scene: SceneManager | None = None
        self.character: EveCharacter | None = None
        self._frame: np.ndarray | None = None
        self.width = self.height = 0
        self.simplified_shading = False  # True when the GPU/driver has no GLSL
        self._hosted = False
        self._host: Any = None  # hidden host window for drivers that need one
        self._description = "Panda3D (not initialised)"

    # -- lifecycle ------------------------------------------------------------------------
    def initialize(self, width: int, height: int) -> None:
        _configure_panda()
        self._engine = GraphicsEngine.getGlobalPtr()
        selection = GraphicsPipeSelection.getGlobalPtr()
        self.scene = SceneManager(self.settings)
        self.character = EveCharacter(self.scene.scene, self.character_config)
        problems: list[str] = []
        for module in pipe_candidates():
            label = module or "default OpenGL"
            self._hosted = module == HOSTED_GL
            default = module in (None, HOSTED_GL)
            pipe = selection.makeDefaultPipe() if default else selection.makeModulePipe(module)
            if pipe is None:
                problems.append(f"{label}: no graphics pipe")
                continue
            self._pipe = pipe
            try:
                self._create_buffer(width, height)
            except RuntimeError as exc:
                problems.append(f"{label}: {exc}")
                self._release_host()
                continue
            self._engine.renderFrame()  # initialises the GSG so its capabilities are known
            gsg = self._buffer.getGsg() if self._buffer is not None else None
            if gsg is None or not gsg.isValid():
                problems.append(f"{label}: graphics context is not valid")
                self._release_buffer()
                continue
            if not gsg.getSupportsGlsl() and not self.simplified_shading:
                # Old/virtual GL (e.g. GDI OpenGL 1.1 over Remote Desktop) or the software
                # rasteriser: no shaders, so use simplified fixed-function shading.
                self.simplified_shading = True
                self.scene.use_fixed_function_lighting()
                self.character.use_fixed_function()
            # Trust nothing until a test frame actually shows the robot: some drivers hand
            # out buffers that "work" but stay blank.
            coverage = self._test_frame_coverage()
            if coverage < MIN_TEST_COVERAGE:
                problems.append(f"{label}: test frame was blank (coverage {coverage:.1%})")
                self._release_buffer()
                self._release_host()
                continue
            break
        else:
            raise RuntimeError("no usable renderer — " + "; ".join(problems))
        if problems:
            log.warning("renderer fallbacks used: %s", "; ".join(problems))
        assert self._buffer is not None and self._pipe is not None
        gsg = self._buffer.getGsg()
        shading = " — simplified shading (no GLSL)" if self.simplified_shading else ""
        interface = self._pipe.getInterfaceName()
        if "tiny" in interface.lower():
            details = "software rasteriser, no antialiasing"
        else:
            details = (
                f"{gsg.getDriverRenderer()} ({gsg.getDriverVersion()}), "
                f"MSAA {self._buffer.getFbProperties().getMultisamples()}x"
            )
        self._description = f"Panda3D {interface} — {details}{shading}"
        log.info("renderer: %s", self._description)

    def _make_host_window(self) -> Any:
        """A hidden, undecorated 1×1 window far off-screen whose GL context hosts the buffer."""
        assert self._engine is not None
        props = WindowProperties.size(1, 1)
        props.setUndecorated(True)
        props.setOrigin(-30000, -30000)
        props.setForeground(False)
        props.setTitle("Project EVE renderer")
        fbp = FrameBufferProperties()
        fbp.setRgbaBits(8, 8, 8, 8)
        fbp.setDepthBits(24)
        window = self._engine.makeOutput(
            self._pipe, "eve-host", -10, fbp, props, GraphicsPipe.BF_require_window | GraphicsPipe.BF_fb_props_optional
        )
        if window is None:
            raise RuntimeError("could not open a hidden host window")
        self._engine.openWindows()
        hide = WindowProperties()
        hide.setMinimized(True)
        window.requestProperties(hide)
        return window

    def _test_frame_coverage(self) -> float:
        """Fraction of pixels the robot covers in a neutral-pose test frame."""
        from eve.character.character_rig import neutral_pose

        try:
            frame = self.render(neutral_pose())
            frame = self.render(neutral_pose())  # some drivers deliver the first copy late
        except Exception:
            log.exception("test frame failed")
            return 0.0
        return float((frame.pixels[..., 3] > 0).mean())

    def _release_host(self) -> None:
        if self._engine is not None and self._host is not None:
            self._engine.removeWindow(self._host)
        self._host = None

    def _release_buffer(self) -> None:
        if self._engine is not None and self._buffer is not None:
            self._engine.removeWindow(self._buffer)
        self._buffer = None
        self._texture = None

    def _create_buffer(self, width: int, height: int) -> None:
        assert self._engine is not None and self.scene is not None
        width, height = max(16, int(width)), max(16, int(height))
        fbp = FrameBufferProperties()
        fbp.setRgbaBits(8, 8, 8, 8)
        fbp.setDepthBits(24)
        if self.settings.multisamples > 0:
            fbp.setMultisamples(self.settings.multisamples)
        if self._hosted and self._host is None:
            self._host = self._make_host_window()
        host = self._host if self._hosted else None
        gsg = host.getGsg() if host is not None else None

        engine = self._engine

        def make(props: FrameBufferProperties) -> Any:
            return engine.makeOutput(
                self._pipe,
                "eve-offscreen",
                -2,
                props,
                WindowProperties.size(width, height),
                # A "parasite" buffer draws into the host window instead of offscreen;
                # its RAM copy is blank, so it is never acceptable here.
                GraphicsPipe.BF_refuse_window | GraphicsPipe.BF_refuse_parasite,
                gsg,
                host,
            )

        buffer = make(fbp)
        if buffer is None and self.settings.multisamples > 0:
            log.warning("MSAA offscreen buffer unavailable; retrying without antialiasing")
            fbp.setMultisamples(0)
            buffer = make(fbp)
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
        self._release_host()
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
