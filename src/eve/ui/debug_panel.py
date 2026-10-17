"""Debug panel: live analysis features, beat/tempo, dance state and performance."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from eve.app_context import AppController

BARS = (
    ("energy", "Energy"),
    ("low", "Bass (20–150 Hz)"),
    ("mid", "Mid (150–2k Hz)"),
    ("high", "High (2–10 kHz)"),
    ("flux", "Spectral flux"),
    ("onset_strength", "Onset strength"),
    ("bass_pulse", "Bass pulse"),
    ("intensity", "Rhythmic intensity"),
    ("music_activity", "Music activity"),
    ("tempo_confidence", "Tempo confidence"),
)


class DebugPanel(QWidget):
    def __init__(self, app: AppController) -> None:
        super().__init__()
        self.app = app
        grid = QGridLayout()
        grid.setVerticalSpacing(3)
        self._bars: dict[str, QProgressBar] = {}
        for row, (key, title) in enumerate(BARS):
            grid.addWidget(QLabel(title), row, 0)
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setTextVisible(False)
            bar.setMaximumHeight(8)
            grid.addWidget(bar, row, 1)
            self._bars[key] = bar
        self._text: dict[str, QLabel] = {}
        form = QFormLayout()
        for key in ("level", "tempo", "beat", "state", "movement", "drive", "render", "analysis", "buffer"):
            label = QLabel("–")
            self._text[key] = label
            form.addRow(key.capitalize() + ":", label)
        moves = QHBoxLayout()
        self.moves = QComboBox()
        self.moves.addItems(app.movement_names())
        play = QPushButton("Play move")
        play.clicked.connect(lambda: app.play_movement(self.moves.currentText()))
        moves.addWidget(self.moves, 1)
        moves.addWidget(play)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(grid)
        layout.addLayout(form)
        layout.addLayout(moves)

    def refresh(self) -> None:
        snap: dict[str, Any] = self.app.debug_snapshot()
        f = self.app.latest_features()
        for key, bar in self._bars.items():
            bar.setValue(int(1000 * max(0.0, min(1.0, float(getattr(f, key))))))
        t = self._text
        t["level"].setText(f"{f.level_db:6.1f} dBFS  ({'silent' if f.is_silent else 'sound'})")
        tempo = f"{f.tempo_bpm:5.1f} BPM" if f.tempo_bpm > 0 else "not locked"
        t["tempo"].setText(f"{tempo}  (onsets {f.onset_rate:.1f}/s)")
        lock = "(locked)" if snap.get("beat_locked") else "(free)"
        t["beat"].setText(f"phase {f.beat_phase:.2f} · dance clock {snap.get('dance_bpm', 0):.0f} BPM {lock}")
        t["state"].setText(str(snap.get("state", "")))
        t["movement"].setText(str(snap.get("movement", "")))
        t["drive"].setText(f"{snap.get('drive', 0):.2f}  weight {snap.get('weight', 0):.2f}")
        t["render"].setText(
            f"{snap.get('fps', 0):.0f} FPS · {snap.get('frame_ms', 0):.1f} ms/frame · {snap.get('render_size', '')}"
        )
        t["analysis"].setText(f"{snap.get('analysis_ms', 0):.2f} ms/hop · {snap.get('source', '')}")
        t["buffer"].setText(f"overruns {snap.get('overruns', 0)} · samples {snap.get('samples', 0):,}")
