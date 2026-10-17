"""Material definitions for the robot's custom shader (engine-independent data)."""

from __future__ import annotations

from dataclasses import dataclass

from eve.character.character_config import CharacterConfig


@dataclass(frozen=True)
class MaterialSpec:
    base_color: tuple[float, float, float]
    specular: float = 0.4  # highlight strength
    shininess: float = 48.0  # highlight tightness
    rim: float = 0.2  # fresnel rim light strength
    wrap: float = 0.35  # soft diffuse wrap (0 = hard Lambert)
    emission: tuple[float, float, float] = (0.0, 0.0, 0.0)
    unlit: bool = False  # emissive-only (eyes, chest light)
    translucent: bool = False  # premultiplied-alpha blending (halos, shadow)


def build_materials(config: CharacterConfig) -> dict[str, MaterialSpec]:
    eye = config.eye_color
    return {
        "shell": MaterialSpec(config.shell_color, specular=0.55, shininess=70.0, rim=0.22, wrap=0.45),
        "arm": MaterialSpec(config.arm_color, specular=0.5, shininess=60.0, rim=0.2, wrap=0.45),
        "face": MaterialSpec(config.face_color, specular=0.95, shininess=140.0, rim=0.18, wrap=0.1),
        "eye": MaterialSpec(eye, emission=eye, unlit=True),
        "eye_halo": MaterialSpec(eye, emission=eye, unlit=True, translucent=True),
        "chest": MaterialSpec(eye, emission=eye, unlit=True),
        "shadow": MaterialSpec((0.0, 0.0, 0.0), unlit=True, translucent=True),
    }
