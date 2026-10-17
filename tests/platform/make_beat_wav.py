"""Write a 14 s, 120 BPM synthetic beat to a WAV file (used by the platform capture checks).

python tests/platform/make_beat_wav.py beat.wav
"""

from __future__ import annotations

import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.fixtures import synthetic_audio as sa

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "beat.wav"
    samples = np.clip(sa.beat_track(14, bpm=120, amp=0.6), -1, 1)
    with wave.open(target, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(48000)
        out.writeframes((samples * 32767).astype(np.int16).tobytes())
    print(f"wrote {target}")
