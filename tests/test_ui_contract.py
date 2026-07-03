from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_update_interval_control_is_on_configuration_page() -> None:
    config_source = (ROOT / "serial_monitor/ui/pages/config_page.py").read_text(
        encoding="utf-8"
    )
    live_source = (ROOT / "serial_monitor/ui/pages/live_page.py").read_text(
        encoding="utf-8"
    )

    assert "update_interval_spinbox" in config_source
    assert "update_interval_changed" in config_source
    assert "update_interval_spinbox" not in live_source


def test_touch_configuration_exposes_conversion_controls() -> None:
    source = (ROOT / "serial_monitor/ui/pages/config_page.py").read_text(
        encoding="utf-8"
    )

    assert "adc_reference_voltage_input" in source
    assert "adc_gain_selector" in source
    assert "channel_base_mode_selector" in source
    assert "channel_conversion_configs" in source


def test_live_tab_distinguishes_base_and_processed() -> None:
    source = (ROOT / "serial_monitor/ui/widgets/signal_tab.py").read_text(
        encoding="utf-8"
    )

    assert 'BASE_MODE = "base"' in source
    assert 'PROCESSED_MODE = "processed"' in source
    assert 'CONVERTED_MODE = "converted"' not in source
    assert "converted_radio" not in source


def test_manual_protocol_test_controls_were_removed() -> None:
    config_source = (ROOT / "serial_monitor/ui/pages/config_page.py").read_text(
        encoding="utf-8"
    )
    controller_source = (ROOT / "serial_monitor/app/bootstrap.py").read_text(
        encoding="utf-8"
    )
    main_source = (ROOT / "serial_monitor/ui/main_window.py").read_text(
        encoding="utf-8"
    )

    for token in (
        "_build_protocol_test_group",
        "validate_frame_button",
        "ingest_frame_button",
        "test_sequence_input",
        "test_timestamp_input",
        "sample_frame_text",
    ):
        assert token not in config_source
        assert token not in controller_source
        assert token not in main_source


def test_live_graph_layout_is_bounded_focusable_and_keeps_recording_controls() -> None:
    live_source = (ROOT / "serial_monitor/ui/pages/live_page.py").read_text(
        encoding="utf-8"
    )
    tab_source = (ROOT / "serial_monitor/ui/widgets/signal_tab.py").read_text(
        encoding="utf-8"
    )
    plot_source = (
        ROOT / "serial_monitor/ui/widgets/signal_plot_widget.py"
    ).read_text(encoding="utf-8")
    main_source = (ROOT / "serial_monitor/ui/main_window.py").read_text(
        encoding="utf-8"
    )

    assert "QScrollArea" not in live_source
    assert "set_fullscreen_mode" in live_source
    assert "self.controls_group.setVisible(True)" in live_source
    assert "self.recording_group.setVisible(True)" in live_source
    assert "self.controls_group.setVisible(not enabled)" not in live_source
    assert "self.recording_group.setVisible(not enabled)" not in live_source
    assert 'self.start_recording_button = QPushButton("Gravar")' in live_source
    assert 'self.finalize_recording_button = QPushButton("Finalizar")' in live_source
    assert 'self.cancel_recording_button = QPushButton("Cancelar")' in live_source

    assert "QSplitter" in tab_source
    assert "self.side_scroll = QScrollArea()" in tab_source
    assert "set_plot_focused" in tab_source
    assert "self.side_scroll.hide()" in tab_source
    assert "setMinimumSize(0, 0)" in plot_source
    assert "QSizePolicy.Expanding" in plot_source
    assert "enter_fullscreen" in main_source
    assert "leave_fullscreen" in main_source
    assert "status_bar.setVisible(False)" in main_source


def test_controller_does_not_reference_removed_config_buffer_button() -> None:
    controller_source = (ROOT / "serial_monitor/app/bootstrap.py").read_text(
        encoding="utf-8"
    )

    assert "config.clear_buffers_button" not in controller_source
    assert "live.clear_buffers_button" in controller_source


def test_reconnection_resets_sequence_baseline_and_plot_follows_timestamp() -> None:
    controller_source = (ROOT / "serial_monitor/app/bootstrap.py").read_text(
        encoding="utf-8"
    )
    acquisition_source = (
        ROOT / "serial_monitor/application/live_acquisition_service.py"
    ).read_text(encoding="utf-8")
    ring_source = (ROOT / "serial_monitor/processing/ring_buffer.py").read_text(
        encoding="utf-8"
    )
    plot_source = (
        ROOT / "serial_monitor/ui/widgets/signal_plot_widget.py"
    ).read_text(encoding="utf-8")

    assert "self._last_rendered_sequence_id = None" in controller_source
    assert "reset_stream_baseline=True" in controller_source
    assert "self.clear_buffers(reset_stream_baseline=True)" in acquisition_source
    assert "self._time_origin_us" in ring_source
    assert "self._set_x_range(max(x_min, x_max - window), x_max)" in plot_source
    assert "zoom_horizontal" in plot_source
    assert "follow_mode_changed" in plot_source
    assert 'x_min = max(0.0, data_x_min) if self._current_domain == "time"' in plot_source
    assert "y_min = min(0.0, data_y_min)" in plot_source


def test_operational_panel_exposes_required_diagnostics() -> None:
    live_source = (ROOT / "serial_monitor/ui/pages/live_page.py").read_text(encoding="utf-8")
    controller_source = (ROOT / "serial_monitor/app/bootstrap.py").read_text(encoding="utf-8")

    for token in (
        "missing_frames_label",
        "crc_errors_label",
        "disk_free_label",
        "cpu_label",
        "memory_label",
        "temperature_label",
        "queue_high_watermark",
    ):
        assert token in live_source
    assert "refresh_operational_status" in controller_source
    assert "OperationalMonitor" in controller_source


def test_logs_and_protocol_errors_are_graphically_throttled() -> None:
    main_source = (ROOT / "serial_monitor/ui/main_window.py").read_text(encoding="utf-8")
    serial_source = (ROOT / "serial_monitor/infrastructure/serial/serial_reader.py").read_text(encoding="utf-8")
    controller_source = (ROOT / "serial_monitor/app/bootstrap.py").read_text(encoding="utf-8")

    assert "_pending_log_lines" in main_source
    assert "_flush_pending_logs" in main_source
    assert "PROTOCOL_REPORT_INTERVAL_S" in serial_source
    assert "self.wait(1500)" not in serial_source
    assert "def on_protocol_error(self, count: int, message: str)" in controller_source


def test_new_validation_disconnects_current_serial_first() -> None:
    controller_source = (ROOT / "serial_monitor/app/bootstrap.py").read_text(encoding="utf-8")
    assert "request_session_validation" in controller_source
    assert "self._pending_session_validation = True" in controller_source
    assert "QTimer.singleShot(0, self.validate_session)" in controller_source
