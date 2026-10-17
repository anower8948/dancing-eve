"""Builds the robot as a Panda3D scene graph and applies poses to it.

Node hierarchy (see character_rig for channel meanings)::

    root            ROOT_X/Y/Z, ROOT_H
     └ body_pivot   BODY_P, BODY_R           (rotation only)
        ├ body_scale  BODY_SQUASH            (squash/stretch affects the torso only)
        │   └ body, chest light
        ├ head_pivot  HEAD_*, HEAD_LIFT       (neck point, follows squash height)
        │   └ head shell, face, eye frames → tilt → gaze → blink
        ├ arm_l_pivot / arm_r_pivot           swing (pitch) / spread (roll)
    shadow          follows ROOT_X/Y, fades with height (not parented to root)
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from panda3d.core import (
    ColorBlendAttrib,
    DepthWriteAttrib,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexArrayFormat,
    GeomVertexData,
    GeomVertexFormat,
    LMatrix4f,
    NodePath,
    TransparencyAttrib,
    Vec3,
    Vec4,
)

from eve.character import character_geometry as geo
from eve.character.character_config import CharacterConfig
from eve.character.character_rig import Ch
from eve.character.facial_expressions import eye_state
from eve.character.materials import MaterialSpec, build_materials

# Sign conventions mapping rig channels onto Panda3D's HPR (verified visually; see
# docs/animation-system.md "Conventions").
ROLL_SIGN = 1.0
PITCH_SIGN = 1.0
SHADOW_Z = -0.92


def _linear(c: tuple[float, float, float]) -> Vec3:
    return Vec3(*(float(x) ** 2.2 for x in c))


_FORMAT: Any = None


def _vertex_format() -> Any:
    global _FORMAT
    if _FORMAT is None:
        array = GeomVertexArrayFormat()
        array.addColumn("vertex", 3, Geom.NT_float32, Geom.C_point)
        array.addColumn("normal", 3, Geom.NT_float32, Geom.C_normal)
        array.addColumn("color", 4, Geom.NT_float32, Geom.C_color)
        _FORMAT = GeomVertexFormat.registerFormat(GeomVertexFormat(array))
    return _FORMAT


def mesh_to_node(name: str, mesh: geo.Mesh) -> NodePath:
    """Upload a NumPy mesh into Panda3D vertex/index buffers (single memcpy each)."""
    n = mesh.vertices.shape[0]
    colors = mesh.colors if mesh.colors is not None else np.ones((n, 4), dtype=np.float32)
    interleaved = np.hstack([mesh.vertices, mesh.normals, colors]).astype(np.float32)
    vdata = GeomVertexData(name, _vertex_format(), Geom.UH_static)
    vdata.uncleanSetNumRows(n)
    memoryview(vdata.modifyArray(0)).cast("B")[:] = interleaved.tobytes()
    prim = GeomTriangles(Geom.UH_static)
    prim.setIndexType(Geom.NT_uint32)
    handle = prim.modifyVertices()
    handle.uncleanSetNumRows(mesh.indices.shape[0])
    memoryview(handle).cast("B")[:] = mesh.indices.astype(np.uint32).tobytes()
    geom = Geom(vdata)
    geom.addPrimitive(prim)
    node = GeomNode(name)
    node.addGeom(geom)
    return NodePath(node)


class EveCharacter:
    def __init__(self, parent: NodePath, config: CharacterConfig | None = None) -> None:
        self.config = cfg = config or CharacterConfig()
        self.materials = build_materials(cfg)
        meshes = geo.build_all(cfg)

        self.root = parent.attachNewNode("eve_root")
        self.body_pivot = self.root.attachNewNode("body_pivot")
        self.body_scale = self.body_pivot.attachNewNode("body_scale")
        body = mesh_to_node("body", meshes["body"])
        body.reparentTo(self.body_scale)
        self._apply_material(body, "shell")

        # Chest light on the front of the torso.
        zn = cfg.chest_light_height / cfg.body_top
        r = cfg.body_radius * math.sqrt(max(0.0, 1 - zn * zn)) * (1 + cfg.body_taper * zn)
        self.chest = self.body_scale.attachNewNode("chest")
        self.chest.setPos(0, -r - 0.004, cfg.chest_light_height)
        self.chest.setP(-math.degrees(math.atan2(cfg.chest_light_height, r)) * 0.4)
        chest_core = mesh_to_node("chest_core", meshes["chest"])
        chest_core.reparentTo(self.chest)
        self._apply_material(chest_core, "chest")
        chest_halo = mesh_to_node("chest_halo", meshes["chest_halo"])
        chest_halo.reparentTo(self.chest)
        chest_halo.setY(0.001)
        self._apply_material(chest_halo, "eye_halo", alpha=0.55)
        self._chest_nodes = (chest_core, chest_halo)

        # Head.
        self.head_pivot = self.body_pivot.attachNewNode("head_pivot")
        self.head = self.head_pivot.attachNewNode("head")
        self.head.setZ(cfg.head_center_height - cfg.neck_height)
        shell = mesh_to_node("head_shell", meshes["head"])
        shell.reparentTo(self.head)
        self._apply_material(shell, "shell")
        face = mesh_to_node("face", meshes["face"])
        face.reparentTo(self.head)
        self._apply_material(face, "face")

        self.eyes: list[dict[str, NodePath]] = []
        for side in (-1.0, 1.0):  # viewer's left eye, then right
            center, right, up, normal = geo.head_surface_frame(
                cfg, cfg.eye_elevation, side * cfg.eye_spacing, lift=1.02
            )
            frame = self.head.attachNewNode(f"eye_frame_{'l' if side < 0 else 'r'}")
            frame.setMat(
                LMatrix4f(
                    *right,
                    0.0,
                    *(-normal),
                    0.0,
                    *up,
                    0.0,
                    *center,
                    1.0,
                )
            )
            tilt = frame.attachNewNode("tilt")
            tilt.setR(-side * cfg.eye_tilt * ROLL_SIGN)  # outer ends slightly lower
            halo = mesh_to_node("halo", meshes["halo_l" if side < 0 else "halo_r"])
            halo.reparentTo(self.head)
            self._apply_material(halo, "eye_halo", alpha=0.6)
            look = tilt.attachNewNode("look")
            blink = look.attachNewNode("blink")
            oval = mesh_to_node("eye", meshes["eye"])
            oval.reparentTo(blink)
            self._apply_material(oval, "eye")
            arc = mesh_to_node("eye_arc", meshes["eye_arc"])
            arc.reparentTo(look)
            self._apply_material(arc, "eye")
            arc.hide()
            self.eyes.append({"look": look, "blink": blink, "oval": oval, "arc": arc, "halo": halo})
        self._eye_w, self._eye_h = geo.eye_size(cfg)

        # Arms.
        self.arms: list[NodePath] = []
        for side in (-1.0, 1.0):
            pivot = self.body_pivot.attachNewNode(f"arm_{'l' if side < 0 else 'r'}_pivot")
            pivot.setPos(side * cfg.shoulder_offset, 0.0, cfg.shoulder_height)
            arm = mesh_to_node("arm", meshes["arm"])
            arm.reparentTo(pivot)
            arm.setR(side * -4.0 * ROLL_SIGN)  # rest slightly outward-tilted
            self._apply_material(arm, "arm")
            self.arms.append(pivot)

        # Soft contact shadow below (separate from the root so it stays on the 'floor').
        self.shadow = mesh_to_node("shadow", meshes["shadow"])
        self.shadow.reparentTo(parent)  # a camera-facing flat ellipse reads as a floor shadow
        self._apply_material(self.shadow, "shadow", alpha=cfg.shadow_opacity)
        self.shadow.setBin("fixed", 0)

    # -- materials ----------------------------------------------------------------------
    def _apply_material(self, node: NodePath, key: str, alpha: float = 1.0) -> None:
        spec: MaterialSpec = self.materials[key]
        node.setShaderInput("u_base", _linear(spec.base_color))
        node.setShaderInput("u_params", Vec4(spec.specular, spec.shininess, spec.rim, spec.wrap))
        node.setShaderInput("u_emission", _linear(spec.emission) * (1.6 if spec.unlit else 1.0))
        node.setShaderInput("u_unlit", 1.0 if spec.unlit else 0.0)
        node.setShaderInput("u_alpha", alpha)
        if spec.translucent:
            node.setTransparency(TransparencyAttrib.M_none)
            node.setAttrib(
                ColorBlendAttrib.make(
                    ColorBlendAttrib.M_add, ColorBlendAttrib.O_one, ColorBlendAttrib.O_one_minus_incoming_alpha
                )
            )
            node.setAttrib(DepthWriteAttrib.make(DepthWriteAttrib.M_off))
            node.setBin("fixed", 10)

    # -- pose ---------------------------------------------------------------------------
    def apply_pose(self, pose: np.ndarray) -> None:
        cfg = self.config
        p = pose
        self.root.setPos(float(p[Ch.ROOT_X]), float(p[Ch.ROOT_Y]), float(p[Ch.ROOT_Z]))
        self.root.setH(float(p[Ch.ROOT_H]))
        self.body_pivot.setHpr(0.0, float(p[Ch.BODY_P]) * PITCH_SIGN, float(p[Ch.BODY_R]) * ROLL_SIGN)
        squash = float(p[Ch.BODY_SQUASH])
        stretch = 1.0 + squash
        side_scale = 1.0 / math.sqrt(max(stretch, 0.5))  # volume preservation
        self.body_scale.setScale(side_scale, side_scale, stretch)
        self.head_pivot.setPos(0.0, 0.0, cfg.neck_height * stretch + float(p[Ch.HEAD_LIFT]))
        self.head_pivot.setHpr(float(p[Ch.HEAD_H]), float(p[Ch.HEAD_P]) * PITCH_SIGN, float(p[Ch.HEAD_R]) * ROLL_SIGN)

        arm_l, arm_r = self.arms
        arm_l.setHpr(0.0, -float(p[Ch.ARM_L_SWING]) * PITCH_SIGN, float(p[Ch.ARM_L_SPREAD]) * ROLL_SIGN)
        arm_r.setHpr(0.0, -float(p[Ch.ARM_R_SWING]) * PITCH_SIGN, -float(p[Ch.ARM_R_SPREAD]) * ROLL_SIGN)

        eyes = eye_state(p)
        emission = _linear(cfg.eye_color) * (1.6 * eyes.glow)
        for i, eye in enumerate(self.eyes):
            openness = eyes.open_l if i == 0 else eyes.open_r
            eye["look"].setPos(eyes.look_x * self._eye_w * 2.0, 0.0, eyes.look_y * self._eye_h * 2.0)
            eye["blink"].setScale(1.0, 1.0, max(openness, 0.04))
            eye["oval"].setShaderInput("u_emission", emission)
            if eyes.happy > 0.05:
                eye["arc"].show()
                eye["arc"].setScale(1.0, 1.0, eyes.happy)
                eye["arc"].setShaderInput("u_emission", emission)
            else:
                eye["arc"].hide()
            eye["halo"].setShaderInput("u_alpha", 0.6 * min(1.0, eyes.glow) * (0.35 + 0.65 * max(openness, eyes.happy)))
        chest_core, chest_halo = self._chest_nodes
        chest_core.setShaderInput("u_emission", _linear(cfg.eye_color) * (1.2 * eyes.glow))
        chest_halo.setShaderInput("u_alpha", 0.35 + 0.4 * max(0.0, eyes.glow - 0.9))

        # Shadow: under the robot, smaller and fainter as it rises.
        height = float(p[Ch.ROOT_Z])
        spread = 1.0 + 0.6 * max(0.0, height)
        self.shadow.setPos(float(p[Ch.ROOT_X]), float(p[Ch.ROOT_Y]) + 0.3, SHADOW_Z)
        self.shadow.setScale(0.34 * spread, 1.0, 0.05 * spread)
        self.shadow.setShaderInput("u_alpha", cfg.shadow_opacity / spread**2)
