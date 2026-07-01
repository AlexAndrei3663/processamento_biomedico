from __future__ import annotations

from PyQt5.QtCore import QThread, pyqtSignal
import serial

from serial_monitor.domain.models import SessionConfig
from .protocol import FrameCsvParser, FrameProtocolError


class SerialReader(QThread):
    frame_received = pyqtSignal(object)
    error_occurred = pyqtSignal(str)
    protocol_error = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)

    def __init__(self, parser: FrameCsvParser | None = None):
        super().__init__()
        self._parser = parser or FrameCsvParser()
        self._session: SessionConfig | None = None
        self._running = False

    def configure(self, session: SessionConfig) -> None:
        self._session = session

    def stop(self) -> None:
        self._running = False
        self.wait(1500)

    def run(self) -> None:
        if self._session is None:
            self.error_occurred.emit("Sessão serial não configurada.")
            return

        self._running = True
        try:
            with serial.Serial(self._session.port, self._session.baudrate, timeout=0.2) as ser:
                self.connection_changed.emit(True)
                while self._running:
                    raw_line = ser.readline()
                    if not raw_line:
                        continue

                    try:
                        decoded_line = raw_line.decode("utf-8", errors="ignore")
                        parsed = self._parser.parse_line(decoded_line, self._session)
                        self.frame_received.emit(parsed.frame)
                    except FrameProtocolError as exc:
                        self.protocol_error.emit(str(exc))
                    except Exception as exc:
                        self.error_occurred.emit(f"Erro inesperado ao processar linha serial: {exc}")
        except serial.SerialException as exc:
            self.error_occurred.emit(f"Erro serial: {exc}")
        finally:
            self._running = False
            self.connection_changed.emit(False)
