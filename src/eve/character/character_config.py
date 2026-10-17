"""Character proportions, colours and (future) external-model configuration.

The default character is fully procedural. ``model_path`` is the extension point for a
properly licensed replacement model (e.g. a .bam/.egg/.gltf converted for Panda3D): if it
is set, the renderer loads it and looks for nodes named in ``ExternalModelJoints``
instead of generating geometry. See docs/rendering.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExternalModelJoints:
    body: str = "body"
    head: str = "head"
    arm_left: str = "arm_l"
    arm_right: str = "arm_r"
    eye_left: str = "eye_l"
    eye_right: str = "eye_r"


@dataclass(frozen=True)
class CharacterConfig:
    # Body: an egg-shaped torso, wider near the top, tapering to a rounded point.
    body_radius: float = 0.36
    body_top: float = 0.36  # height of the top above the body origin
    body_bottom: float = 0.6  # depth of the bottom tip below the body origin
    body_taper: float = 0.24  # >0 makes the top wider than the bottom
    # Head: a wide, softly squared ellipsoid floating just above the body.
    head_radii: tuple[float, float, float] = (0.34, 0.29, 0.245)  # x (width), y (depth), z (height)
    head_exponent: float = 2.35  # >2 squares the silhouette slightly (superellipsoid)
    head_gap: float = 0.035  # visible gap between body and head
    neck_height: float = 0.40  # head pivot height above the body origin
    # Face panel: angular extents on the head (degrees).
    face_half_width: float = 64.0
    face_half_height: float = 40.0
    face_center_elevation: float = 2.0
    # Eyes (degrees on the head surface).
    eye_spacing: float = 20.5  # azimuth of each eye centre from the middle
    eye_elevation: float = 4.0
    eye_width: float = 11.5
    eye_height: float = 8.2
    eye_tilt: float = 9.0  # outer ends lower (soft, friendly look)
    # Arms: paddle-like teardrops hanging beside the body.
    arm_length: float = 0.5
    arm_radius: float = 0.075
    arm_flatten: float = 0.62  # depth/width ratio
    shoulder_height: float = 0.2
    shoulder_offset: float = 0.415
    # Chest light (a small glowing indicator that pulses with the bass).
    chest_light_height: float = 0.08
    chest_light_radius: float = 0.032
    # Colours (sRGB 0..1).
    shell_color: tuple[float, float, float] = (0.94, 0.95, 0.97)
    face_color: tuple[float, float, float] = (0.025, 0.03, 0.045)
    eye_color: tuple[float, float, float] = (0.35, 0.78, 1.0)
    arm_color: tuple[float, float, float] = (0.92, 0.93, 0.955)
    shadow_opacity: float = 0.3
    # Mesh resolution (higher = smoother, more vertices).
    segments: int = 72
    rings: int = 48
    model_path: str | None = None
    joints: ExternalModelJoints = field(default_factory=ExternalModelJoints)

    @property
    def head_center_height(self) -> float:
        """Head centre above the body origin."""
        return self.body_top + self.head_gap + self.head_radii[2] * 0.85

    @property
    def total_height(self) -> float:
        return self.body_bottom + self.head_center_height + self.head_radii[2]
