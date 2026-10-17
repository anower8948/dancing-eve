"""Per-channel motion limits and spring tuning.

Different body parts respond at different speeds: the root/body reacts quickly to beats,
the head lags and overshoots a little, the arms are loose and follow through, and the
eyes are fast (blinks, glances). Changing these numbers changes the character's 'weight'.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from eve.character.character_rig import N_CHANNELS, Ch


@dataclass(frozen=True)
class ChannelSpec:
    lo: float
    hi: float
    freq: float  # spring frequency (Hz)
    damping: float  # damping ratio
    max_vel: float  # units per second
    angular: bool = False  # wraps at ±180°


SPECS: dict[Ch, ChannelSpec] = {
    Ch.ROOT_X: ChannelSpec(-0.22, 0.22, 1.9, 0.78, 2.0),
    Ch.ROOT_Y: ChannelSpec(-0.25, 0.25, 1.6, 0.8, 1.5),
    Ch.ROOT_Z: ChannelSpec(-0.22, 0.32, 3.0, 0.55, 2.5),
    Ch.ROOT_H: ChannelSpec(-1e9, 1e9, 2.1, 0.78, 900.0, angular=True),
    Ch.BODY_P: ChannelSpec(-24.0, 24.0, 2.8, 0.6, 320.0),
    Ch.BODY_R: ChannelSpec(-26.0, 26.0, 2.8, 0.6, 320.0),
    Ch.BODY_SQUASH: ChannelSpec(-0.12, 0.12, 5.0, 0.35, 3.0),
    Ch.HEAD_H: ChannelSpec(-55.0, 55.0, 2.3, 0.52, 420.0),
    Ch.HEAD_P: ChannelSpec(-28.0, 28.0, 2.6, 0.5, 420.0),
    Ch.HEAD_R: ChannelSpec(-30.0, 30.0, 2.4, 0.5, 420.0),
    Ch.HEAD_LIFT: ChannelSpec(-0.03, 0.09, 3.4, 0.42, 1.0),
    Ch.ARM_L_SWING: ChannelSpec(-60.0, 115.0, 1.9, 0.4, 600.0),
    Ch.ARM_L_SPREAD: ChannelSpec(-4.0, 165.0, 1.9, 0.4, 600.0),  # >90 = raised overhead
    Ch.ARM_R_SWING: ChannelSpec(-60.0, 115.0, 1.9, 0.4, 600.0),
    Ch.ARM_R_SPREAD: ChannelSpec(-4.0, 165.0, 1.9, 0.4, 600.0),
    Ch.EYE_OPEN: ChannelSpec(0.0, 1.3, 9.0, 1.0, 30.0),  # >1 = wide-eyed surprise
    Ch.EYE_HAPPY: ChannelSpec(0.0, 1.0, 3.5, 0.9, 8.0),
    Ch.EYE_LOOK_X: ChannelSpec(-1.0, 1.0, 6.5, 0.85, 12.0),
    Ch.EYE_LOOK_Y: ChannelSpec(-1.0, 1.0, 6.5, 0.85, 12.0),
    Ch.EYE_GLOW: ChannelSpec(0.5, 1.6, 3.0, 1.0, 6.0),
}

assert len(SPECS) == N_CHANNELS

LOWER = np.array([SPECS[ch].lo for ch in Ch])
UPPER = np.array([SPECS[ch].hi for ch in Ch])
FREQUENCIES = [SPECS[ch].freq for ch in Ch]
DAMPING = [SPECS[ch].damping for ch in Ch]
MAX_VELOCITY = [SPECS[ch].max_vel for ch in Ch]
ANGULAR = [SPECS[ch].angular for ch in Ch]

# Reduced-motion mode: smaller excursions and gentler speeds for posture channels.
REDUCED_MOTION_SCALE = 0.42
REDUCED_MOTION_VELOCITY_SCALE = 0.5


def clamp_pose(values: np.ndarray, out: np.ndarray | None = None) -> np.ndarray:
    """Clamp every channel to its limits (heading is unbounded)."""
    return np.clip(values, LOWER, UPPER, out=out)
