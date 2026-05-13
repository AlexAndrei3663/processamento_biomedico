from __future__ import annotations

import sys
from typing import Any

from PyQt5.QtWidgets import QApplication

from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial import SerialReader
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser
from serial_monitor.ui.main_window import MainWindow

from serial_monitor.domain.models import SampleFrame


class StageOneController:
    def __init__(self, window: MainWindow, session_service: SessionService, serial_reader: SerialReader) -> None:
        self.window = window
        self.session_service = session_service
        self.serial_reader = serial_reader
        self.parser = FrameCsvParser()
        self._session = None
        self._connect_signals()
        self.log("INFO", "Controlador inicializado. Use 'Validar sessão' e depois 'Testar parser'.")

    def _connect_signals(self) -> None:
        self.window.validate_button.clicked.connect(self.validate_session)
        self.window.validate_frame_button.clicked.connect(self.validate_sample_frame)
        self.window.connect_button.clicked.connect(self.connect_serial)
        self.window.disconnect_button.clicked.connect(self.disconnect_serial)
        self.window.clear_log_button.clicked.connect(self.window.log.clear)
        self.serial_reader.frame_received.connect(self.on_frame_received)
        self.serial_reader.error_occurred.connect(self.on_error)
        self.serial_reader.connection_changed.connect(self.on_connection_changed)

    def log(self, level: str, message: str) -> None:
        self.window.append_log(level, message)
        print(f"[{level}] {message}", flush=True)

    def validate_session(self) -> bool:
        try:
            self._session = self.session_service.build_session(
                port=self.window.port_input.text().strip(),
                baudrate=int(self.window.baudrate_input.text()),
                base_sample_rate_hz=int(self.window.sample_rate_input.text()),
                window_size=int(self.window.window_size_input.text()),
                signal_order_text=self.window.signal_order_input.text(),
            )
        except ValueError as exc:
            self._session = None
            self.log("ERRO", str(exc))
            return False
        except Exception as exc:
            self._session = None
            self.log("ERRO", f"Falha inesperada ao validar sessão: {exc}")
            return False

        ordered_signals = ", ".join(signal.value for signal in self._session.signal_order)
        self.log(
            "OK",
            (
                f"Sessão válida: porta={self._session.port}, baudrate={self._session.baudrate}, "
                f"fs={self._session.base_sample_rate_hz} Hz, janela={self._session.window_size}, "
                f"canais=[{ordered_signals}]"
            ),
        )
        return True

    def validate_sample_frame(self) -> None:
        if self._session is None and not self.validate_session():
            return
        assert self._session is not None

        line = self.window.sample_frame_input.text()
        try:
            parsed = self.parser.parse_line(line, self._session)
        except Exception as exc:
            self.log("ERRO", f"Frame de teste inválido: {exc}")
            return

        frame = parsed.frame
        pairs = []
        for channel, value in zip(self._session.channels, frame.values_in_order, strict=True):
            pairs.append(f"{channel.signal_type.value}={value:g} {channel.unit}")
        self.log(
            "OK",
            f"Frame aceito: seq={frame.sequence_id}, timestamp_ms={frame.timestamp_ms}, " + ", ".join(pairs),
        )

    def connect_serial(self) -> None:
        if self.serial_reader.isRunning():
            self.log("INFO", "A serial já está conectada ou tentando conectar.")
            return
        if self._session is None and not self.validate_session():
            return
        assert self._session is not None
        self.log("INFO", f"Tentando abrir porta serial {self._session.port} a {self._session.baudrate} baud...")
        self.serial_reader.configure(self._session)
        self.serial_reader.start()

    def disconnect_serial(self) -> None:
        if not self.serial_reader.isRunning():
            self.log("INFO", "A serial já está desconectada.")
            return
        self.log("INFO", "Encerrando leitura serial...")
        self.serial_reader.stop()

    def on_frame_received(self, frame: SampleFrame) -> None:
        self.log("FRAME", f"seq={frame.sequence_id} ts={frame.timestamp_ms} values={frame.values_in_order}")

    def on_error(self, message: str) -> None:
        self.log("ERRO", message)

    def on_connection_changed(self, connected: bool) -> None:
        self.window.connect_button.setEnabled(not connected)
        self.window.disconnect_button.setEnabled(connected)
        state = "conectado" if connected else "desconectado"
        self.log("STATUS", f"Serial {state}.")


def run() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()

    controller = StageOneController(window, SessionService(), SerialReader())
    window.controller = controller

    window.show()
    return app.exec_()
