"""Mapping from pose expression channels to concrete eye parameters."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eve.character.character_rig import Ch


@dataclass(frozen=True, slots=True)
class EyeState:
    open_l: float  # vertical scale of the oval eye (0 closed .. 1 open)
    open_r: float
    happy: float  # 0 = oval eyes, 1 = upward 'smiling' arcs
    look_x: float  # eye offset on the face, in eye-widths
    look_y: float
    glow: float  # brightness multiplier


def eye_state(pose: np.ndarray) -> EyeState:
    openness = float(np.clip(pose[Ch.EYE_OPEN], 0.0, 1.0))
    happy = float(np.clip(pose[Ch.EYE_HAPPY], 0.0, 1.0))
    # Happy eyes squint: the oval shrinks as the arc appears.
    oval_open = openness * (1.0 - 0.85 * happy)
    return EyeState(
        open_l=oval_open,
        open_r=oval_open,
        happy=happy * openness,
        look_x=float(np.clip(pose[Ch.EYE_LOOK_X], -1.0, 1.0)) * 0.35,
        look_y=float(np.clip(pose[Ch.EYE_LOOK_Y], -1.0, 1.0)) * 0.3,
        glow=float(np.clip(pose[Ch.EYE_GLOW], 0.4, 1.8)),
    )
