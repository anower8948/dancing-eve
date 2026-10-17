"""Secondary motion derived from the primary motion's physics.

Nothing here is random: the head stabilises against body tilt, the arms swing from body
acceleration (like loose pendulums), spins push the arms outward (centrifugal), and the
gaze follows lateral movement. Inputs are the spring state of the previous frame.
"""

from __future__ import annotations

import numpy as np

from eve.character.character_rig import Ch


class SecondaryMotion:
    def __init__(self) -> None:
        self._prev_v = np.zeros(4)  # ROOT_X, ROOT_Z, BODY_R, ROOT_H velocities
        self._acc = np.zeros(4)  # smoothed accelerations

    def apply(self, target: np.ndarray, x: np.ndarray, v: np.ndarray, dt: float, amount: float = 1.0) -> None:
        """Add secondary offsets to ``target`` in place."""
        if dt <= 0:
            return
        current = np.array((v[Ch.ROOT_X], v[Ch.ROOT_Z], v[Ch.BODY_R], v[Ch.ROOT_H]))
        raw_acc = (current - self._prev_v) / dt
        self._prev_v = current
        alpha = min(1.0, dt / 0.06)
        self._acc += (raw_acc - self._acc) * alpha
        acc_x, acc_z, _acc_roll, _ = self._acc
        vel_x, vel_z, vel_roll, vel_h = current

        k = amount
        # Head: partial stabilisation (keeps looking at the viewer) + lag-induced counter-roll.
        target[Ch.HEAD_R] += k * (-0.35 * x[Ch.BODY_R] - 0.04 * vel_roll)
        target[Ch.HEAD_P] += k * (-0.3 * x[Ch.BODY_P] + 6.0 * np.clip(acc_z, -8, 8) * 0.25)
        # Arms: inertia against acceleration, outward during spins.
        swing = np.clip(-acc_z * 3.5, -25.0, 25.0)
        sway = np.clip(acc_x * 12.0, -30.0, 30.0)
        spin_spread = min(40.0, abs(vel_h) * 0.07)
        target[Ch.ARM_L_SWING] += k * swing
        target[Ch.ARM_R_SWING] += k * swing
        target[Ch.ARM_L_SPREAD] += k * (max(0.0, sway) + spin_spread)
        target[Ch.ARM_R_SPREAD] += k * (max(0.0, -sway) + spin_spread)
        # Squash on downward acceleration (landing), stretch when rising fast.
        target[Ch.BODY_SQUASH] += k * float(np.clip(0.012 * vel_z, -0.03, 0.03))
        # Eyes glance in the direction of travel.
        target[Ch.EYE_LOOK_X] += k * float(np.clip(vel_x * 1.5, -0.4, 0.4))
