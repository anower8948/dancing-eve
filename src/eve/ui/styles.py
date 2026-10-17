"""Shared Qt style sheet (works with both light and dark system palettes)."""

ACCENT = "#3BA7F5"

SETTINGS_QSS = f"""
QWidget#settingsRoot {{ font-size: 13px; }}
QGroupBox {{
    font-weight: 600;
    border: 1px solid palette(mid);
    border-radius: 10px;
    margin-top: 14px;
    padding: 10px 10px 8px 10px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 4px; }}
QPushButton {{ padding: 5px 12px; border-radius: 6px; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: none; font-weight: 600; }}
QPushButton#primary:disabled {{ background: palette(mid); }}
QPushButton#danger {{ color: #d0342c; }}
QLabel#hint {{ color: palette(mid); font-size: 11px; }}
QLabel#statusText {{ font-weight: 600; }}
QProgressBar {{ border: 1px solid palette(mid); border-radius: 4px; height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 3px; }}
"""
