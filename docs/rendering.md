# Rendering

## Pipeline

`Panda3DRenderer` (`eve/rendering/panda3d_renderer.py`) creates a Panda3D
`GraphicsBuffer` (offscreen, RGBA8 + depth 24, 4× MSAA when available) directly through
`GraphicsEngine` — no `ShowBase`, no Panda window, no Panda task loop. Each frame:

1. `EveCharacter.apply_pose(pose)` sets node transforms and shader inputs.
2. `GraphicsEngine.renderFrame()` renders; the buffer's texture uses `RTM_copy_ram`.
3. The BGRA RAM image is flipped vertically into a reusable NumPy array → `FrameImage`.
4. `CompanionWindow` wraps it in a `QImage` (`Format_ARGB32_Premultiplied`) and paints it
   into a translucent frameless Qt window. Output is premultiplied alpha.

Render size = window logical size × device-pixel ratio; it is recreated when the window
moves between Retina and non-Retina screens.

## Look

* GLSL 1.20 shaders (`shaders.py`) — compatible with the macOS legacy GL 2.1 context.
* Lighting in view space: warm key (upper left), cool fill (right), back light,
  hemisphere ambient, wrapped diffuse, Blinn-Phong highlights, fresnel rim; computed in
  linear space and gamma-encoded.
* Materials (`character/materials.py`): glossy white shell, very glossy near-black face
  visor, unlit emissive eyes and chest light, premultiplied-alpha glow halos and floor
  shadow (`ColorBlendAttrib(add, one, one_minus_incoming_alpha)` for colour and alpha).
* Geometry (`character/character_geometry.py`, pure NumPy): egg-shaped torso (wider top,
  elongated tip), superellipsoid head (exponent 2.35) floating above the body, face visor
  as a rounded-rectangle patch on the head surface, curved oval eyes and "happy" arcs in
  a right-handed surface frame, surface-conforming glow halos, teardrop paddle arms.

## Performance (measured, macOS 27, Apple M2, 213–246 × 260–300 px)

| Scenario | FPS | frame p50 / p95 | render p50 | process CPU | RSS |
|---|---|---|---|---|---|
| Dancing (`--demo`, 20 s) | 58.4 | 3.7 / 4.6 ms | 3.0 ms | 23 % of one core | 229 MB |
| Idle (`--no-audio`, 20 s, drops to idle FPS after 12 s) | 47 avg | 3.6 / 4.3 ms | 2.9 ms | 19 % | 209 MB |
| Tight render loop (no Qt painting) | — | — | 0.45 ms | — | — |

The gap between 0.45 ms and ~3 ms is the synchronous GPU→CPU readback waiting for an
idling GPU. Idle FPS has since been lowered from 30 to 24 (not re-measured). Ideas:
async PBO readback, sharing a Qt OpenGL context, rendering only when the pose changes.

## Replacing the character

`CharacterConfig.model_path` and `ExternalModelJoints` define the hook for a licensed
model: nodes named `body`, `head`, `arm_l`, `arm_r`, `eye_l`, `eye_r`. Loading such
models is **planned, not implemented** — `EveCharacter` currently always builds the
procedural robot. Implementing it means: load with `loader.loadModel`, find the joints,
and map pose channels to them in the same way as `apply_pose`.
