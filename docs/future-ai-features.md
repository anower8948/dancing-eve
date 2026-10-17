# Future AI features (not implemented)

None of these exist yet. They must remain local, optional, and never download large
models automatically.

* **Better rhythm tracking:** a small local beat/downbeat model (e.g. TCN/CRNN like
  madmom/BeatNet, exported to ONNX) running on the analyzer thread with the current DSP
  tracker as fallback. Plug-in point: produce `PulseEvent(BEAT)` and `beat_phase` with
  an honest confidence.
* **Local music classification** (genre/mood/energy embeddings) to bias movement
  weights. Must be labelled as an estimate; never infer emotion from loudness alone.
  Plug-in point: an extra field in `AudioFeatures` consumed by `Choreographer.weights`.
* **Model-based choreography:** a sequence model choosing movement primitives (not raw
  joint angles) from music features, keeping the spring layer for physical plausibility.
  Plug-in point: replace `Choreographer.choose`.
* **Motion generation for humanoid characters** (when GLB/VRM characters arrive): music-
  to-dance models output skeletal motion; would need retargeting and a different rig.
* **Character customisation** from text prompts — out of scope for local-only operation
  unless a small local model exists.

Requirements for any of these: opt-in download with size shown, checksum verification,
CPU budget, offline operation afterwards, and tests showing they beat the DSP baseline.
