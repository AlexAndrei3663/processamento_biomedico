from __future__ import annotations

from datetime import datetime
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCloseEvent, QKeyEvent
from PyQt5.QtWidgets import QMainWindow, QStackedWidget

from serial_monitor.app.runtime_settings import RuntimeSettings
from serial_monitor.domain.models import (
    CommunicationStats,
    ConversionProfile,
    ProcessedAcquisitionSnapshot,
    RecordingStatus,
    SessionConfig,
    StoredSessionSummary,
    SystemResourceSnapshot,
)
from serial_monitor.domain.enums import WindowPageIndex
from serial_monitor.infrastructure.storage.config_repository import SessionPreset
from serial_monitor.ui.pages.config_page import ConfigPage
from serial_monitor.ui.pages.live_page import LivePage
from serial_monitor.ui.pages.menu_page import MenuPage
from serial_monitor.ui.pages.stored_page import StoredPage


class MainWindow(QMainWindow):
    """Janela principal com navegação por páginas."""

    def __init__(self, settings: RuntimeSettings | None = None) -> None:
        super().__init__()
        self.settings = settings or RuntimeSettings()
        self.setWindowTitle("Monitor de Sinais Biomédicos")
        self.resize(1024, 600)

        self.setStyleSheet(
            """
            QPushButton {
                min-height: 46px;
                padding: 7px 12px;
                font-size: 15px;
                font-weight: 600;
            }
            QComboBox, QSpinBox, QDoubleSpinBox {
                min-height: 42px;
                padding: 4px 8px;
                font-size: 14px;
            }
            QListWidget {
                font-size: 15px;
            }
            QListWidget::item {
                min-height: 38px;
                padding: 5px;
            }
            QTabBar::tab {
                min-height: 40px;
                min-width: 105px;
                padding: 6px 10px;
                font-size: 14px;
            }
            QCheckBox, QRadioButton {
                min-height: 36px;
                spacing: 10px;
                font-size: 14px;
            }
            QCheckBox::indicator, QRadioButton::indicator {
                width: 24px;
                height: 24px;
            }
            QGroupBox {
                font-size: 14px;
                font-weight: 600;
                margin-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }

            /* A página ao vivo precisa caber integralmente em 1024 x 600. */
            QWidget#livePage QPushButton {
                min-height: 36px;
                max-height: 40px;
                padding: 3px 7px;
                font-size: 13px;
            }
            QWidget#livePage QTabBar::tab {
                min-height: 32px;
                min-width: 90px;
                padding: 4px 8px;
                font-size: 13px;
            }
            QWidget#livePage QCheckBox,
            QWidget#livePage QRadioButton {
                min-height: 32px;
                spacing: 8px;
                font-size: 13px;
            }
            QWidget#livePage QCheckBox::indicator,
            QWidget#livePage QRadioButton::indicator {
                width: 22px;
                height: 22px;
            }
            QWidget#livePage QLabel {
                font-size: 12px;
            }
            """
        )

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.menu_page = MenuPage()
        self.config_page = ConfigPage()
        self.live_page = LivePage(
            update_interval_ms=self.settings.update_interval_ms,
            max_plot_points=self.settings.max_plot_points,
        )
        self.stored_page = StoredPage()
        self.config_page.set_performance_settings(
            self.settings.update_interval_ms,
            self.settings.max_plot_points,
        )

        self.stack.addWidget(self.menu_page)
        self.stack.addWidget(self.config_page)
        self.stack.addWidget(self.live_page)
        self.stack.addWidget(self.stored_page)

        self.show_menu()
        self._show_status_message("Pronto")

    def _show_status_message(self, message: str, timeout: int = 0) -> None:
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.showMessage(message, timeout)

    def show_menu(self) -> None:
        self.stack.setCurrentIndex(WindowPageIndex.MENU_PAGE)
        self._show_status_message("Menu inicial")

    def show_config(self) -> None:
        self.stack.setCurrentIndex(WindowPageIndex.CONFIG_PAGE)
        self._show_status_message("Configuração da sessão")

    def show_live(self) -> None:
        self.stack.setCurrentIndex(WindowPageIndex.LIVE_PAGE)
        self._show_status_message("Visualização ao vivo")

    def show_stored(self) -> None:
        self.stack.setCurrentIndex(WindowPageIndex.STORED_PAGE)
        self._show_status_message("Sinais armazenados")

    def enter_fullscreen(self) -> None:
        self.live_page.set_fullscreen_mode(True)
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.setVisible(False)
        self.showFullScreen()

    def leave_fullscreen(self) -> None:
        self.live_page.set_fullscreen_mode(False)
        self.showNormal()
        status_bar = self.statusBar()
        if status_bar is not None:
            status_bar.setVisible(True)
        self._show_status_message("Modo janela")

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.leave_fullscreen()
        else:
            self.enter_fullscreen()

    def append_log(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] [{level}] {message}"
        self.config_page.log.appendPlainText(line)
        self._show_status_message(f"[{level}] {message}", 5000)

    def clear_logs(self) -> None:
        self.config_page.log.clear()

    def build_signal_tabs(self, session: SessionConfig) -> None:
        self.live_page.build_signal_tabs(session, max_plot_points=self.settings.max_plot_points)

    def clear_signal_tabs(self) -> None:
        self.live_page.clear_signal_tabs()

    def update_live_view(self, snapshot: ProcessedAcquisitionSnapshot) -> None:
        self.live_page.update_live_view(snapshot)

    def update_buffer_summary(self, snapshot: ProcessedAcquisitionSnapshot) -> None:
        self.config_page.update_buffer_summary(snapshot)

    def update_recording_status(self, status: RecordingStatus) -> None:
        self.live_page.update_recording_status(status)

    def update_operational_status(
        self,
        communication: CommunicationStats,
        resources: SystemResourceSnapshot,
        *,
        crc_available: bool,
        minimum_free_disk_bytes: int,
    ) -> None:
        self.live_page.update_operational_status(
            communication,
            resources,
            crc_available=crc_available,
            minimum_free_disk_bytes=minimum_free_disk_bytes,
        )

    def update_connection_state(self, connected: bool) -> None:
        self.live_page.connect_button.setEnabled(not connected)
        self.live_page.disconnect_button.setEnabled(connected)

    def update_stored_sessions(self, summaries: list[StoredSessionSummary]) -> None:
        self.stored_page.set_sessions(summaries)

    def update_stored_details(self, text: str) -> None:
        self.stored_page.set_details(text)

    def set_stored_export_running(self, running: bool) -> None:
        self.stored_page.set_export_running(running)

    def update_stored_export_progress(self, percent: int, completed: int, total: int) -> None:
        self.stored_page.update_export_progress(percent, completed, total)

    def finish_stored_export(self, message: str, *, success: bool) -> None:
        self.stored_page.finish_export(message, success=success)


    def set_conversion_profiles(self, profiles: list[ConversionProfile]) -> None:
        self.config_page.set_conversion_profiles(profiles)

    def update_presets(self, presets: list[SessionPreset]) -> None:
        self.config_page.set_presets(presets)

    def apply_preset(self, preset: SessionPreset) -> None:
        self.config_page.apply_preset(preset)

    def keyPressEvent(self, a0: QKeyEvent | None) -> None:  # noqa: N802 - método Qt
        if a0:
            if a0.key() == Qt.Key.Key_F11:
                self.toggle_fullscreen()
                return
            if a0.key() == Qt.Key.Key_Escape and self.isFullScreen():
                self.leave_fullscreen()
                return
        super().keyPressEvent(a0)

    def closeEvent(self, a0: QCloseEvent | None) -> None:  # noqa: N802 - método Qt
        controller: Any = getattr(self, "controller", None)
        if controller is not None and hasattr(controller, "shutdown"):
            controller.shutdown()
        if a0:
            a0.accept()

    # Atalhos usados pelo controlador para manter a leitura do código simples.
    @property
    def selected_preset_name(self) -> str | None:
        return self.config_page.selected_preset_name

    @property
    def preset_name_text(self) -> str:
        return self.config_page.preset_name

    @property
    def selected_stored_session_id(self) -> str | None:
        return self.stored_page.selected_session_id


    @property
    def selected_stored_summary(self) -> StoredSessionSummary | None:
        return self.stored_page.selected_summary

    @property
    def selected_stored_start_seconds(self) -> float:
        return self.stored_page.selected_start_seconds

    @property
    def selected_stored_duration_seconds(self) -> float:
        return self.stored_page.selected_duration_seconds

    @property
    def selected_stored_max_points(self) -> int:
        return self.stored_page.selected_max_points

    @property
    def selected_port(self) -> str:
        return self.config_page.selected_port or ""

    @property
    def baudrate_text(self) -> str:
        return str(self.config_page.baudrate)

    @property
    def sample_rate_text(self) -> str:
        return str(self.config_page.sample_rate_hz)

    @property
    def window_size_text(self) -> str:
        return str(self.config_page.window_size)

    @property
    def signal_order_text(self) -> str:
        return self.config_page.signal_order_text

    @property
    def channel_conversion_configs(self) -> list[dict]:
        return self.config_page.channel_conversion_configs

