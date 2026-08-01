from __future__ import annotations

import ast
from pathlib import Path


def test_signal_tab_applies_simplified_controls_once():
    source = Path(
        "serial_monitor/ui/widgets/signal_tab.py"
    ).read_text(encoding="utf-8")
    assert (
        "from serial_monitor.ui.layouts.simplified_signal_controls "
        "import apply_simplified_signal_controls"
    ) in source
    assert source.count("apply_simplified_signal_controls(self)") == 1
    ast.parse(source)


def test_filter_changes_are_transactional():
    source = Path(
        "serial_monitor/ui/layouts/simplified_signal_controls.py"
    ).read_text(encoding="utf-8")
    assert "_disconnect_immediate_filter_application" in source
    assert "self.tab.filter_toggled.emit" in source
    assert "def apply_filters" in source
    assert "Fechar sem aplicar descarta" in source
    assert "QTimer" not in source
    ast.parse(source)


def test_base_processed_selection_is_automatic():
    source = Path(
        "serial_monitor/ui/layouts/simplified_signal_controls.py"
    ).read_text(encoding="utf-8")
    assert "def _sync_display_mode" in source
    assert "self.tab.processed_radio.setChecked(True)" in source
    assert "self.tab.base_radio.setChecked(True)" in source
    assert 'view_group.hide()' in source


def test_domain_and_scale_controls_are_contextual_and_top_aligned():
    source = Path(
        "serial_monitor/ui/layouts/simplified_signal_controls.py"
    ).read_text(encoding="utf-8")
    for required in (
        "self.domain_button",
        "self.time_scale_button.setVisible(is_time)",
        "self.spectrum_scale_button.setVisible(not is_time)",
        'domain_group.hide()',
        "self.tab.vertical_scale_group.hide()",
        "self.tab.spectrum_scale_group.hide()",
    ):
        assert required in source


def test_bandpass_remains_highpass_plus_lowpass():
    source = Path(
        "serial_monitor/ui/layouts/simplified_signal_controls.py"
    ).read_text(encoding="utf-8")
    assert 'normalized.update(("highpass", "lowpass"))' in source
    assert 'normalized.discard("bandpass")' in source
