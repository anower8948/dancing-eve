"""Scene setup: camera framing and the shader. Lighting lives in the shader (view space)."""

from __future__ import annotations

import logging
import math

from panda3d.core import AmbientLight, Camera, DirectionalLight, NodePath, PerspectiveLens, Point3, Shader

from eve.rendering import shaders
from eve.rendering.render_settings import VIEW_HEIGHT, RenderSettings

log = logging.getLogger(__name__)

# The character's visual centre (between body bottom and head top), in character units.
FRAME_CENTER_Z = 0.06


class SceneManager:
    def __init__(self, settings: RenderSettings) -> None:
        self.settings = settings
        self.scene = NodePath("eve_scene")
        self.lens = PerspectiveLens()
        self.camera_node = Camera("eve_camera", self.lens)
        self.camera = self.scene.attachNewNode(self.camera_node)
        self._frame(1.0)
        self.shader = Shader.make(Shader.SL_GLSL, shaders.VERTEX, shaders.FRAGMENT)
        if self.shader is None:
            raise RuntimeError("GLSL shader failed to compile")
        self.scene.setShader(self.shader)
        # Defaults so every node has all inputs even before a material is applied.
        self.scene.setShaderInput("u_base", (0.8, 0.8, 0.8))
        self.scene.setShaderInput("u_params", (0.4, 48.0, 0.2, 0.35))
        self.scene.setShaderInput("u_emission", (0.0, 0.0, 0.0))
        self.scene.setShaderInput("u_unlit", 0.0)
        self.scene.setShaderInput("u_alpha", 1.0)

    def _frame(self, aspect: float) -> None:
        fov = self.settings.field_of_view
        distance = (VIEW_HEIGHT / 2.0) / math.tan(math.radians(fov / 2.0))
        self.lens.setNearFar(distance - 3.0, distance + 3.0)
        hfov = 2.0 * math.degrees(math.atan(math.tan(math.radians(fov / 2.0)) * aspect))
        self.lens.setFov(hfov, fov)
        self.camera.setPos(0.0, -distance, FRAME_CENTER_Z)
        self.camera.lookAt(0.0, 0.0, FRAME_CENTER_Z)

    def use_fixed_function_lighting(self) -> None:
        """Fallback when GLSL is unavailable: Panda's built-in lights approximate the
        shader's key/fill/ambient setup (attached to the camera, like the shader's
        view-space lights)."""
        self.scene.setShaderOff(100)
        ambient = AmbientLight("ambient")
        ambient.setColor((0.34, 0.35, 0.38, 1.0))
        key = DirectionalLight("key")
        key.setColor((0.95, 0.93, 0.9, 1.0))
        key.setSpecularColor((0.9, 0.9, 0.9, 1.0))
        fill = DirectionalLight("fill")
        fill.setColor((0.32, 0.36, 0.45, 1.0))
        for light in (ambient, key, fill):
            node = self.camera.attachNewNode(light)
            if light is key:
                node.lookAt(Point3(0.55, 1.0, -0.6))
            elif light is fill:
                node.lookAt(Point3(-0.85, 1.0, -0.05))
            self.scene.setLight(node)

    def set_aspect(self, width: int, height: int) -> None:
        self._frame(width / max(1, height))
