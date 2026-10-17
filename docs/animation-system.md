# Animation and choreography

## Character hierarchy and pose channels

The pose is a 20-float vector indexed by `eve.character.character_rig.Ch`:

| Group | Channels | Units |
|---|---|---|
| Root | `ROOT_X`, `ROOT_Y` (depth), `ROOT_Z`, `ROOT_H` (heading) | body heights, degrees |
| Body | `BODY_P` (+ = lean forward), `BODY_R` (+ = top leans to viewer's right), `BODY_SQUASH` | degrees, fraction |
| Head | `HEAD_H`, `HEAD_P`, `HEAD_R` (relative to body), `HEAD_LIFT` (float gap) | degrees, units |
| Arms | `ARM_L_SWING`, `ARM_L_SPREAD`, `ARM_R_SWING`, `ARM_R_SPREAD` (L = viewer's left) | degrees |
| Eyes | `EYE_OPEN`, `EYE_HAPPY`, `EYE_LOOK_X`, `EYE_LOOK_Y`, `EYE_GLOW` | 0..1 / −1..1 |

Scene graph: `root → body_pivot → {body_scale (torso, chest light), head_pivot (head,
face, eyes), arm pivots}`; the floor shadow is separate and fades with height. Squash
scales only the torso (volume-preserving) and moves the neck point, so the head never
deforms.

**Conventions** were verified visually with a pose sheet (`BODY_R +20` leans right, arms
`SWING 90` point at the viewer, `SPREAD 60` lift outward). If a replacement model uses a
different axis convention, adjust `ROLL_SIGN`/`PITCH_SIGN` in `eve_character.py`.

## Layers (per frame, `AnimationController.update`)

1. **Idle** (`idle_animation.py`): float bob (0.21 Hz), breathing squash, smooth-noise
   drift of position/heading/tilt, glances every 4–9 s (eyes lead, head follows),
   blinks every 2.5–6.5 s (18 % double blinks), occasional soft "content" eyes. Idle is
   attenuated by 65 % × dance weight while dancing.
2. **Dance** (`DanceController`): movement targets × dance weight (0..1, rises over ~0.7 s,
   falls over ~2.2 s for a gradual settle).
3. **Secondary motion** (`secondary_motion.py`), derived from the springs' previous state:
   head counter-roll/pitch stabilisation, arm swing from vertical/lateral acceleration,
   centrifugal arm spread from heading velocity, squash/stretch from vertical velocity,
   gaze toward travel direction.
4. **Limits** (`motion_parameters.SPECS`) and reduced-motion scaling (0.42 × posture,
   0.5 × speed limits).
5. **Accents**: beat/onset events are applied as **velocity impulses** (down-kick on the
   root and squash, nod on the head) — the springs turn them into a natural bounce.
6. **Springs** (`spring_dynamics.SpringBank`): per-channel frequency/damping/max velocity,
   semi-implicit Euler at ≤ 1/240 s sub-steps (frame-rate independent). Root ~3 Hz
   bouncy, body 2.8 Hz, head 2.3–2.6 Hz with ζ≈0.5 (lags and overshoots), arms 1.9 Hz
   ζ 0.4 (loose follow-through), eyes 9 Hz. Heading uses shortest-arc error so finished
   spins never unwind.
7. **Blink** applied after the springs (too fast for a spring).

## Choreography (`eve/dance`)

* **Musical clock**: `beat_pos` advances at the tracked tempo and is phase-locked to the
  analyser's beat phase (soft correction, capped at half a frame's advance so the clock
  always moves forward — moves never freeze or rewind on bad input). Without trusted tempo
  (confidence < 0.35) it free-runs at 84–120 BPM pacing and accents come from onsets
  ("energy-reactive fallback") — the robot never pretends to follow a beat it cannot hear.
* **Drive** = 0.45·rhythmic intensity + 0.35·smoothed energy + 0.2·tempo factor
  (volume-independent inputs). No genre or emotion is inferred.
* **State machine** (`dance_state.py`): IDLE, CALM, GROOVE, ENERGETIC, FLOURISH,
  TRANSITION. Hysteresis thresholds (groove 0.42/0.32, energetic 0.66/0.55), 1.5 s hold,
  3 s minimum dwell, 1.2 s silence hold before idle, 0.8 s TRANSITION crossfade between
  dancing states, FLOURISH on an analyser surge with a 15 s cooldown (one celebratory
  move, then back).
* **Movement library** (`movement_library.py`, 27 primitives):

  | State | Moves |
  |---|---|
  | CALM | gentle_sway, head_nod, circular_glide, floating_turn, slow_dance, body_wave, lean_back_groove, figure_eight, pendulum_swing, look_around |
  | GROOVE | gentle_sway, bob, double_bounce, alternating_bounce, head_nod, small_spin, circular_glide, arm_wave, rhythmic_accent, floating_turn, side_step, robot_pop, body_wave, fist_pump, hop_turn, lean_back_groove, figure_eight, pendulum_swing, arm_circles, shimmy, dip_and_rise |
  | ENERGETIC | bob, double_bounce, alternating_bounce, small_spin, arm_wave, excited_wiggle, rhythmic_accent, side_step, robot_pop, headbang, fist_pump, hop_turn, arm_circles, shimmy, dip_and_rise |
  | FLOURISH | celebratory_flourish, star_burst |

  Each
  has per-state weights, a preferred drive range, cooldown, reduced-motion eligibility,
  half-time eligibility and a crossfade time. Anticipation is built into the curves
  (`anticipate()` wind-ups before spins/turns, dips before hops, head "spotting" before a
  spin).
* **Selection** (`choreography.py`): weight × drive fit × 0.35^(recent repeats) ×
  0.15 if it was the previous move × cooldown gate; random side mirroring (70 % alternate);
  ±10 % amplitude jitter; half-time in calm passages above 105 BPM.
* **Phrases**: 40 % of picks of short moves (≤ 4 beats, cooldown < 8 s) start a phrase —
  patterns `AB`, `ABA`, `BbA`, `AaB` after the opening move, where `A` repeats the move
  mirrored (call and response), `a` repeats it on the same side, `B`/`b` is a
  contrasting move. A phrase is abandoned when the dance state changes.
* **Expressions**: wide eyes (EYE_OPEN up to 1.3) and a head lift for 0.9 s on a surge;
  happy arcs per move; sleepy after 45 s without dancing (ramping over 30 s: heavy lids,
  slow blinks, sinking, nodding off, no glances; the app drops to 15 FPS), waking quickly
  when music starts or on a click.
* **Arms overhead** use *spread* > 90° (raised out to the side), which reads from the
  front; *swing* points the arm at the viewer and is foreshortened, so it is used for
  small forward motion only.
* **Transitions** (`transition_manager.py`): quintic crossfade, outgoing move keeps
  running, angles blended on the shortest arc.

Measured: dance + animation update ≈ 0.07 ms per frame.

## Adding a movement

1. Write a function in `movement_library.py`:
   ```python
   def _my_move(c: MoveContext, out: np.ndarray) -> None:
       out[Ch.ROOT_Z] = 0.04 * c.amp * skewed_wave(c.phase)  # bob on the beat
       out[Ch.BODY_R] = 8.0 * c.amp * c.side * math.sin(TAU * c.beat / 4)
   ```
   Use `c.beat` (beats since start) for slow shapes, `c.phase` (0 = on the beat) for
   accents, `c.side` for mirroring, `c.amp` for intensity. Write **offsets** only; do not
   smooth — the springs do that.
2. Register it in `build_library()` with state weights, drive range, cooldown, flags.
3. `tests/unit/test_dance_controller.py::test_every_movement_is_finite_and_starts_near_rest`
   covers it automatically; preview with the debug panel's "Play move".
