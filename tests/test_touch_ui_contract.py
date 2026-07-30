"""Contratos estruturais da interface touch sem depender do PyQt5 no CI."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_config_page_does_not_use_line_edit_fields():
    source = _source("serial_monitor/ui/pages/config_page.py")
    assert "QLineEdit" not in source
    assert "QComboBox" in source
    assert "QSpinBox" in source


def test_channel_selection_is_list_based_and_ordered():
    source = _source("serial_monitor/ui/pages/config_page.py")
    assert "available_signal_selector" in source
    assert "add_channel_button" in source
    assert "channel_order_list" in source
    assert "move_channel_up_button" in source
    assert "move_channel_down_button" in source
    assert "remove_channel_button" in source


def test_live_page_has_no_log_or_buffer_summary_widgets():
    source = _source("serial_monitor/ui/pages/live_page.py")
    assert "QTextEdit" not in source
    assert "QPlainTextEdit" not in source
    assert "buffer_summary" not in source
    assert "clear_log_button" not in source


def test_main_window_routes_summary_and_log_to_configuration_page():
    source = _source("serial_monitor/ui/main_window.py")
    tree = ast.parse(source)
    assert "self.config_page.log.appendPlainText(line)" in source
    assert "self.config_page.update_buffer_summary(snapshot)" in source
    assert "self.live_page.log" not in source


def test_controller_autoloads_first_preset_and_finalizes_interrupted_sessions():
    source = _source("serial_monitor/app/bootstrap.py")
    assert "self._finalize_interrupted_sessions()" in source
    assert "self._refresh_presets(auto_load_first=False)" in source
    assert "self.window.apply_preset(presets[0])" in source
