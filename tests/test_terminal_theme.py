from __future__ import annotations

import json
from pathlib import Path

from serial_monitor.ui.themes.terminal_pipboy import (
    active_theme_name,
    build_terminal_qss,
    load_theme_config,
)


def test_theme_configuration_is_valid_and_static():
    config = load_theme_config()
    assert config.name == "pipboy"
    assert config.color("background") == "#050B06"
    assert 0.0 <= config.plot_grid_alpha <= 1.0


def test_terminal_qss_preserves_touch_targets_and_has_no_animation():
    qss = build_terminal_qss(load_theme_config())
    assert "min-height: 46px" in qss
    assert "QWidget#livePage QPushButton" in qss
    assert "QStatusBar" in qss
    assert "animation" not in qss.lower()
    assert "blur" not in qss.lower()


def test_environment_can_disable_terminal_theme(monkeypatch):
    monkeypatch.setenv("BIOMED_UI_THEME", "classic")
    assert active_theme_name(load_theme_config()) == "classic"


def test_main_window_uses_external_theme_layer():
    source = Path("serial_monitor/ui/main_window.py").read_text(
        encoding="utf-8"
    )
    assert "apply_application_theme(self)" in source
    assert "style_plot_widgets(self.live_page)" in source


def test_theme_json_contains_no_external_asset_dependency():
    payload = json.loads(
        Path("config/ui_theme.json").read_text(encoding="utf-8")
    )
    assert payload["theme"] == "pipboy"
    assert "image" not in payload
    assert "font_file" not in payload
