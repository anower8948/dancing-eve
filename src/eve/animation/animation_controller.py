"""Layered pose controller: idle + dance + secondary motion -> springs -> final pose.

Per frame:
  1. idle targets (always running, attenuated while dancing)
  2. dance targets, weighted by the dance layer weight
  3. secondary motion from the previous frame's spring velocities/accelerations
  4. clamp to channel limits; reduced-motion scaling
  5. dance accents applied as velocity impulses
  6. springs integrate toward the targets (inertia, overshoot, follow-through)
  7. blink applied on top (too fast to be a spring)
"""

from __future__ import annotations

import numpy as np

from eve.animation.idle_animation import IdleAnimator
from eve.animation.secondary_motion import SecondaryMotion
from eve.animation.spring_dynamics import SpringBank
from eve.character.character_rig import EXPRESSION_CHANNELS, N_CHANNELS, NEUTRAL, Ch
from eve.dance import motion_parameters as mp
from eve.dance.dance_controller import DanceOutput

IDLE_ATTENUATION_WHILE_DANCING = 0.65


class AnimationController:
    def __init__(self, seed: int | None = None, reduced_motion: bool = False) -> None:
        self.idle = IdleAnimator(seed)
        self.secondary = SecondaryMotion()
        self._max_vel = np.asarray(mp.MAX_VELOCITY, dtype=np.float64)
        self.springs = SpringBank(mp.FREQUENCIES, mp.DAMPING, self._max_vel, mp.ANGULAR, initial=NEUTRAL)
        self._target = np.zeros(N_CHANNELS)
        self._pose = NEUTRAL.copy()
        self._posture = np.ones(N_CHANNELS, dtype=bool)
        self._posture[list(EXPRESSION_CHANNELS)] = False
        self.reduced_motion = False
        self.set_reduced_motion(reduced_motion)

    def set_reduced_motion(self, enabled: bool) -> None:
        self.reduced_motion = enabled
        scale = np.where(self._posture, mp.REDUCED_MOTION_VELOCITY_SCALE if enabled else 1.0, 1.0)
        self.springs.max_velocity = self._max_vel * scale

    def poke(self) -> None:
        self.idle.poke()
        self.springs.impulse(Ch.ROOT_Z, 0.5)
        self.springs.impulse(Ch.BODY_SQUASH, 0.8)

    def update(self, dt: float, dance: DanceOutput | None) -> np.ndarray:
        dt = min(max(dt, 0.0), 0.1)  # avoid huge steps after a stall
        idle = self.idle.update(dt)
        w = dance.weight if dance is not None else 0.0
        target = self._target
        np.multiply(idle, 1.0 - IDLE_ATTENUATION_WHILE_DANCING * w, out=target)
        if dance is not None and w > 0:
            target += dance.targets * w
        if self.reduced_motion:
            target[self._posture] *= mp.REDUCED_MOTION_SCALE
        target += NEUTRAL
        self.secondary.apply(target, self.springs.x, self.springs.v, dt, 0.5 if self.reduced_motion else 1.0)
        mp.clamp_pose(target, out=target)

        if dance is not None:
            for channel, delta_v in dance.impulses:
                self.springs.impulse(channel, delta_v)

        x = self.springs.step(target, dt)
        pose = self._pose
        pose[:] = x
        pose[Ch.EYE_OPEN] = float(np.clip(x[Ch.EYE_OPEN], 0.0, 1.0)) * (1.0 - 0.96 * self.idle.blink_amount)
        return pose

    @property
    def pose(self) -> np.ndarray:
        return self._pose
