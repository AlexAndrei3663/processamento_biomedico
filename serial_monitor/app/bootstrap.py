from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication

from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial import SerialReader
from serial_monitor.ui.main_window import MainWindow

from serial_monitor.domain.models import SampleFrame


class StageOneController:
    def __init__(self, window: MainWindow, session_service: SessionService, serial_reader: SerialReader) -> None:
        self.window = window
        self.session_service = session_service
        self.serial_reader = serial_reader
        self._session = None
        self._connect_signals()

    def _connect_signals(self) -> None:
        self.window.validate_button.clicked.connect(self.validate_session)
        self.window.connect_button.clicked.connect(self.connect_serial)
        self.window.disconnect_button.clicked.connect(self.disconnect_serial)
        self.serial_reader.frame_received.connect(self.on_frame_received)
        self.serial_reader.error_occurred.connect(self.on_error)
        self.serial_reader.connection_changed.connect(self.on_connection_changed)

    def validate_session(self) -> None:
        try:
            self._session = self.session_service.build_session(
                port=self.window.port_input.text().strip(),
                baudrate=int(self.window.baudrate_input.text()),
                base_sample_rate_hz=int(self.window.sample_rate_input.text()),
                window_size=int(self.window.window_size_input.text()),
                signal_order_text=self.window.signal_order_input.text(),
            )
        except Exception as exc:
            self.window.log.append(f"[ERRO] {exc}")
            return

        ordered_signals = ", ".join(signal.value for signal in self._session.signal_order)
        self.window.log.append(f"[OK] Sessão válida: {ordered_signals}")

    def connect_serial(self) -> None:
        if self._session is None:
            self.validate_session()
        if self._session is None:
            return
        self.serial_reader.configure(self._session)
        self.serial_reader.start()

    def disconnect_serial(self) -> None:
        self.serial_reader.stop()

    def on_frame_received(self, frame: SampleFrame) -> None:
        self.window.log.append(
            f"[FRAME] seq={frame.sequence_id} ts={frame.timestamp_ms} values={frame.values_in_order}"
        )

    def on_error(self, message: str) -> None:
        self.window.log.append(f"[ERRO] {message}")

    def on_connection_changed(self, connected: bool) -> None:
        self.window.connect_button.setEnabled(not connected)
        self.window.disconnect_button.setEnabled(connected)
        state = "conectado" if connected else "desconectado"
        self.window.log.append(f"[STATUS] Serial {state}.")


def run() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    StageOneController(window, SessionService(), SerialReader())
    window.show()
    return app.exec_()
