"""Engine-independent description of the robot's rig: pose channels and hierarchy.

A pose is a float vector indexed by ``Ch``. The animation system produces it; the renderer
maps it onto scene nodes. Neither side needs to know about the other.

Hierarchy (what each channel moves)::

    root ─ position (ROOT_X/Y/Z), heading (ROOT_H)
     └ body ─ pitch/roll (BODY_P/R), squash-and-stretch (BODY_SQUASH)
        ├ head ─ heading/pitch/roll relative to body (HEAD_H/P/R), float gap (HEAD_LIFT)
        │  └ face ─ eyes: openness, happy-arc shape, gaze, glow
        ├ left arm  ─ swing (pitch around the shoulder) / spread (roll outward)
        └ right arm ─ swing / spread

Units: positions in body-heights (the body is ~1.0 tall), angles in degrees.
Left/right are from the *viewer's* perspective: ARM_L is the arm on the viewer's left
(-X), +ROOT_X moves toward the viewer's right.
"""

from __future__ import annotations

from enum import IntEnum

import numpy as np


class Ch(IntEnum):
    ROOT_X = 0
    ROOT_Y = 1
    ROOT_Z = 2
    ROOT_H = 3
    BODY_P = 4
    BODY_R = 5
    BODY_SQUASH = 6
    HEAD_H = 7
    HEAD_P = 8
    HEAD_R = 9
    HEAD_LIFT = 10
    ARM_L_SWING = 11
    ARM_L_SPREAD = 12
    ARM_R_SWING = 13
    ARM_R_SPREAD = 14
    EYE_OPEN = 15
    EYE_HAPPY = 16
    EYE_LOOK_X = 17
    EYE_LOOK_Y = 18
    EYE_GLOW = 19


N_CHANNELS = len(Ch)

# Values of a relaxed pose (everything else is 0).
NEUTRAL = np.zeros(N_CHANNELS)
NEUTRAL[Ch.EYE_OPEN] = 1.0
NEUTRAL[Ch.EYE_GLOW] = 1.0
NEUTRAL[Ch.ARM_L_SPREAD] = 6.0
NEUTRAL[Ch.ARM_R_SPREAD] = 6.0

# Channels that change appearance rather than posture (not scaled by reduced motion).
EXPRESSION_CHANNELS = (Ch.EYE_OPEN, Ch.EYE_HAPPY, Ch.EYE_LOOK_X, Ch.EYE_LOOK_Y, Ch.EYE_GLOW)


def neutral_pose() -> np.ndarray:
    return NEUTRAL.copy()


def describe(pose: np.ndarray) -> dict[str, float]:
    """Readable dict for logs and the debug panel."""
    return {ch.name.lower(): round(float(pose[ch]), 3) for ch in Ch}
