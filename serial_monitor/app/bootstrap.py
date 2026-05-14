from __future__ import annotations

import sys
from typing import Any

from PyQt5.QtCore import QObject, QTimer, pyqtSlot
from PyQt5.QtWidgets import QApplication

from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser
from serial_monitor.infrastructure.serial.serial_reader import SerialReader
from serial_monitor.processing.filter_pipeline import ProcessingService
from serial_monitor.ui.main_window import MainWindow

from serial_monitor.domain.models import SampleFrame

class StageSixController(QObject):
    """Controlador da navegação, aquisição e pipeline de processamento."""

    def __init__(
        self,
        window: MainWindow,
        session_service: SessionService,
        serial_reader: SerialReader,
        acquisition_service: LiveAcquisitionService,
        processing_service: ProcessingService,
    ) -> None:
        super().__init__()
        self.window = window
        self.session_service = session_service
        self.serial_reader = serial_reader
        self.acquisition_service = acquisition_service
        self.processing_service = processing_service
        self.parser = FrameCsvParser()
        self._session = None
        self._last_summary_frame_count = -1

        self.view_timer = QTimer(self)
        self.view_timer.setInterval(100)
        self.view_timer.timeout.connect(self.refresh_live_view)
        self.view_timer.start()

        self._connect_signals()
        self.log("INFO", "Controlador inicializado. Etapa 6: visualização em espectro.")

    def _connect_signals(self) -> None:
        menu = self.window.menu_page
        config = self.window.config_page
        live = self.window.live_page
        stored = self.window.stored_page

        menu.start_button.clicked.connect(self.start_monitoring_from_menu)
        menu.config_button.clicked.connect(self.window.show_config)
        menu.stored_button.clicked.connect(self.window.show_stored)
        menu.exit_button.clicked.connect(self.close_application)

        config.validate_button.clicked.connect(self.validate_session)
        config.validate_frame_button.clicked.connect(self.validate_sample_frame)
        config.ingest_frame_button.clicked.connect(self.ingest_sample_frame)
        config.clear_buffers_button.clicked.connect(self.clear_buffers)
        config.go_live_button.clicked.connect(self.go_live_from_config)
        config.back_menu_button.clicked.connect(self.window.show_menu)
        config.clear_log_button.clicked.connect(self.window.clear_logs)

        live.connect_button.clicked.connect(self.connect_serial)
        live.disconnect_button.clicked.connect(self.disconnect_serial)
        live.clear_buffers_button.clicked.connect(self.clear_buffers)
        live.clear_log_button.clicked.connect(self.window.clear_logs)
        live.open_config_button.clicked.connect(self.window.show_config)
        live.open_stored_button.clicked.connect(self.window.show_stored)
        live.back_menu_button.clicked.connect(self.window.show_menu)
        live.filter_toggled.connect(self.on_filter_toggled)
        live.display_mode_changed.connect(self.on_display_mode_changed)

        stored.back_menu_button.clicked.connect(self.window.show_menu)
        stored.open_config_button.clicked.connect(self.window.show_config)
        stored.open_live_button.clicked.connect(self.go_live_from_config)
        stored.refresh_button.clicked.connect(self.refresh_stored_sessions_placeholder)

        self.serial_reader.frame_received.connect(self.on_frame_received)
        self.serial_reader.error_occurred.connect(self.on_error)
        self.serial_reader.connection_changed.connect(self.on_connection_changed)

    def log(self, level: str, message: str) -> None:
        self.window.append_log(level, message)
        print(f"[{level}] {message}", flush=True)

    @pyqtSlot()
    def start_monitoring_from_menu(self) -> None:
        if self._session is None:
            self.window.show_config()
            self.log("INFO", "Configure e valide a sessão antes de iniciar o monitoramento.")
            return
        self.window.show_live()
        self.refresh_live_view(force=True)

    @pyqtSlot()
    def go_live_from_config(self) -> None:
        if self._session is None and not self.validate_session():
            return
        self.window.show_live()
        self.refresh_live_view(force=True)

    @pyqtSlot()
    def close_application(self) -> None:
        if self.serial_reader.isRunning():
            self.serial_reader.stop()
        QApplication.instance().quit()

    @pyqtSlot()
    def refresh_stored_sessions_placeholder(self) -> None:
        self.log(
            "INFO",
            "A listagem real de sessões armazenadas será implementada na etapa de armazenamento.",
        )

    @pyqtSlot()
    def validate_session(self) -> bool:
        try:
            self._session = self.session_service.build_session(
                port=self.window.port_text,
                baudrate=int(self.window.baudrate_text),
                base_sample_rate_hz=int(self.window.sample_rate_text),
                window_size=int(self.window.window_size_text),
                signal_order_text=self.window.signal_order_text,
            )
            self.acquisition_service.configure(self._session)
            self.processing_service.configure(self._session)
            self.window.build_signal_tabs(self._session)
            self._last_summary_frame_count = -1
        except ValueError as exc:
            self._session = None
            self.log("ERRO", str(exc))
            self.refresh_live_view(force=True)
            return False
        except Exception as exc:
            self._session = None
            self.log("ERRO", f"Falha inesperada ao validar sessão: {exc}")
            self.refresh_live_view(force=True)
            return False

        ordered_signals = ", ".join(
            f"{channel.index}:{channel.signal_type.value}" for channel in self._session.channels
        )
        self.log(
            "OK",
            (
                f"Sessão válida: porta={self._session.port}, baudrate={self._session.baudrate}, "
                f"fs={self._session.base_sample_rate_hz} Hz, janela={self._session.window_size}, "
                f"canais=[{ordered_signals}]"
            ),
        )
        self.refresh_live_view(force=True)
        return True

    @pyqtSlot()
    def validate_sample_frame(self) -> None:
        if self._session is None and not self.validate_session():
            return
        assert self._session is not None

        line = self.window.sample_frame_text
        try:
            parsed = self.parser.parse_line(line, self._session)
        except Exception as exc:
            self.log("ERRO", f"Frame de teste inválido: {exc}")
            return

        frame = parsed.frame
        pairs = []
        for channel, value in zip(self._session.channels, frame.values_in_order, strict=True):
            pairs.append(f"ch{channel.index}:{channel.signal_type.value}={value:g} {channel.unit}")
        self.log(
            "OK",
            f"Frame aceito: seq={frame.sequence_id}, timestamp_ms={frame.timestamp_ms}, " + ", ".join(pairs),
        )

    @pyqtSlot()
    def ingest_sample_frame(self) -> None:
        if self._session is None and not self.validate_session():
            return
        assert self._session is not None

        line = self.window.sample_frame_text
        try:
            frame = self.parser.parse_line(line, self._session).frame
            self.acquisition_service.ingest_frame(frame)
        except Exception as exc:
            self.log("ERRO", f"Não foi possível inserir frame no buffer: {exc}")
            return

        self.refresh_live_view(force=True)
        self.log("BUFFER", f"Frame seq={frame.sequence_id} inserido nos buffers multicanais.")

    @pyqtSlot()
    def connect_serial(self) -> None:
        if self.serial_reader.isRunning():
            self.log("INFO", "A serial já está conectada ou tentando conectar.")
            return
        if self._session is None and not self.validate_session():
            return
        assert self._session is not None
        self.acquisition_service.start()
        self.refresh_live_view(force=True)
        self.log("INFO", f"Tentando abrir porta serial {self._session.port} a {self._session.baudrate} baud...")
        self.serial_reader.configure(self._session)
        self.serial_reader.start()

    @pyqtSlot()
    def disconnect_serial(self) -> None:
        if not self.serial_reader.isRunning():
            self.log("INFO", "A serial já está desconectada.")
            self.acquisition_service.stop()
            self.refresh_live_view(force=True)
            return
        self.log("INFO", "Encerrando leitura serial...")
        self.serial_reader.stop()

    @pyqtSlot()
    def clear_buffers(self) -> None:
        self.acquisition_service.reset()
        self.window.clear_signal_tabs()
        self.refresh_live_view(force=True)
        self.log("BUFFER", "Buffers multicanais limpos.")

    @pyqtSlot(int, str, bool)
    def on_filter_toggled(self, channel_index: int, filter_id: str, enabled: bool) -> None:
        try:
            self.processing_service.set_filter_enabled(channel_index, filter_id, enabled)
        except Exception as exc:
            self.log("ERRO", f"Não foi possível alterar filtro: {exc}")
            return

        state = "ativado" if enabled else "desativado"
        self.log("FILTRO", f"Canal ch{channel_index}: filtro '{filter_id}' {state}.")
        self.refresh_live_view(force=True)

    @pyqtSlot(int, str)
    def on_display_mode_changed(self, channel_index: int, mode: str) -> None:
        label = "processado" if mode == "processed" else "bruto"
        self.log("VIEW", f"Canal ch{channel_index}: visualização alterada para sinal {label}.")
        self.refresh_live_view(force=True)

    @pyqtSlot()
    def refresh_live_view(self, force: bool = False) -> None:
        raw_snapshot = self.acquisition_service.snapshot()
        processed_snapshot = self.processing_service.process(raw_snapshot)
        self.window.update_live_view(processed_snapshot)

        if force or processed_snapshot.frames_received != self._last_summary_frame_count:
            self.window.update_buffer_summary(processed_snapshot)
            self._last_summary_frame_count = processed_snapshot.frames_received

    @pyqtSlot(object)
    def on_frame_received(self, frame: SampleFrame) -> None:
        try:
            self.acquisition_service.ingest_frame(frame)
        except Exception as exc:
            self.log("ERRO", f"Frame recebido, mas não inserido nos buffers: {exc}")
            return

        snapshot = self.acquisition_service.snapshot()
        if snapshot.frames_received == 1 or snapshot.frames_received % 50 == 0:
            self.log(
                "FRAME",
                (
                    f"frames={snapshot.frames_received}, último_seq={snapshot.last_sequence_id}, "
                    f"gaps={snapshot.sequence_gaps}"
                ),
            )

    @pyqtSlot(str)
    def on_error(self, message: str) -> None:
        self.log("ERRO", message)

    @pyqtSlot(bool)
    def on_connection_changed(self, connected: bool) -> None:
        self.window.update_connection_state(connected)
        if not connected:
            self.acquisition_service.stop()
        state = "conectado" if connected else "desconectado"
        self.refresh_live_view(force=True)
        self.log("STATUS", f"Serial {state}.")


def run() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()

    controller = StageSixController(
        window=window,
        session_service=SessionService(),
        serial_reader=SerialReader(),
        acquisition_service=LiveAcquisitionService(),
        processing_service=ProcessingService(),
    )
    window.controller = controller  # type: ignore[attr-defined]

    window.show()
    return app.exec_()
