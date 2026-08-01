from __future__ import annotations

import ast
from pathlib import Path


def test_live_page_applies_operational_dashboard_once():
    source = Path("serial_monitor/ui/pages/live_page.py").read_text(
        encoding="utf-8"
    )
    assert (
        "from serial_monitor.ui.layouts.operational_dashboard import "
        "apply_operational_dashboard"
    ) in source
    assert source.count("apply_operational_dashboard(self)") == 1
    ast.parse(source)


def test_dashboard_reuses_existing_controls_and_has_no_timer():
    source = Path(
        "serial_monitor/ui/layouts/operational_dashboard.py"
    ).read_text(encoding="utf-8")
    for required in (
        "page.connect_button",
        "page.start_recording_button",
        "page.recording_state_label",
        "page.live_group",
    ):
        assert required in source
    assert "QTimer" not in source
    assert "setInterval" not in source
    ast.parse(source)


def test_dashboard_navigation_and_diagnostics_start_collapsed():
    source = Path(
        "serial_monitor/ui/layouts/operational_dashboard.py"
    ).read_text(encoding="utf-8")
    assert "self.navigation_wrapper.setVisible(False)" in source
    assert "self.diagnostics_wrapper.setVisible(False)" in source
    assert "if visible and self._diagnostics_visible" in source
    assert "if visible and self._navigation_visible" in source


def test_dashboard_does_not_replace_live_page_signals():
    source = Path("serial_monitor/ui/pages/live_page.py").read_text(
        encoding="utf-8"
    )
    for signal_name in (
        "filter_toggled",
        "display_mode_changed",
        "plot_domain_changed",
        "active_channel_changed",
        "fullscreen_requested",
    ):
        assert signal_name in source
