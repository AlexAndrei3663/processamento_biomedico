from __future__ import annotations

import threading
import time

from PyQt5.QtCore import QThread, pyqtSignal

import serial

from serial_monitor.domain.models import SessionConfig

from .protocol import (
    FrameCsvParser,
    FrameProtocolError,
    is_ignorable_serial_line,
)


class SerialReader(QThread):
    """Leitor serial assíncrono com erros agregados e entrega em lotes."""

    frame_received = pyqtSignal(object)
    frames_received = pyqtSignal(object)

    error_occurred = pyqtSignal(str)
    protocol_error = pyqtSignal(int, str)
    connection_changed = pyqtSignal(bool)

    PROTOCOL_REPORT_INTERVAL_S = 1.0
    INCOMPATIBLE_PROTOCOL_GRACE_S = 2.0
    INCOMPATIBLE_PROTOCOL_INVALID_LIMIT = 100

    FRAME_BATCH_SIZE = 20
    FRAME_BATCH_MAX_LATENCY_S = 0.020
    MAX_LINE_BYTES = 256
    INPUT_BUFFER_BYTES = 262_144

    def __init__(self, parser: FrameCsvParser | None = None):
        super().__init__()
        self._parser = parser or FrameCsvParser()
        self._session: SessionConfig | None = None
        self._running = False
        self._serial_port: serial.Serial | None = None
        self._serial_lock = threading.Lock()

    def configure(self, session: SessionConfig) -> None:
        if self.isRunning():
            raise RuntimeError(
                "Não é possível reconfigurar a serial durante a leitura."
            )
        self._session = session

    def stop(self) -> None:
        """Solicita a parada sem bloquear a thread da interface."""

        self._running = False
        self.requestInterruption()

        with self._serial_lock:
            port = self._serial_port

        if port is None:
            return

        try:
            cancel_read = getattr(port, "cancel_read", None)
            if callable(cancel_read):
                cancel_read()
            else:
                port.close()
        except Exception:
            # A thread encerrará pelo timeout curto ou pelo fechamento da porta.
            pass

    def _emit_batch(self, pending_frames: list[object]) -> None:
        if not pending_frames:
            return

        self.frames_received.emit(tuple(pending_frames))
        pending_frames.clear()

    @classmethod
    def _decode_line(cls, raw_line: bytes) -> str:
        if len(raw_line) >= cls.MAX_LINE_BYTES and not raw_line.endswith(b"\n"):
            raise FrameProtocolError(
                f"Linha serial excede {cls.MAX_LINE_BYTES} bytes.",
                category="line_length",
            )
        try:
            return raw_line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise FrameProtocolError(
                "Linha serial contém bytes UTF-8 inválidos.",
                category="encoding",
            ) from exc

    @classmethod
    def _configure_input_buffer(cls, port: object) -> bool:
        set_buffer_size = getattr(port, "set_buffer_size", None)
        if not callable(set_buffer_size):
            return False
        try:
            set_buffer_size(rx_size=cls.INPUT_BUFFER_BYTES)
            return True
        except (AttributeError, NotImplementedError, OSError, serial.SerialException):
            return False

    @staticmethod
    def _format_protocol_summary(counts: dict[str, int], last_message: str) -> str:
        summary = ", ".join(
            f"{category}={count}"
            for category, count in sorted(counts.items())
        )
        return f"{summary}. Último erro: {last_message}" if summary else last_message

    def run(self) -> None:
        if self._session is None:
            self.error_occurred.emit("Sessão serial não configurada.")
            return

        self._running = True
        invalid_count = 0
        invalid_total = 0
        invalid_by_category: dict[str, int] = {}
        valid_total = 0
        last_invalid_message = ""
        last_report = time.monotonic()
        connected_at = last_report
        last_batch_emit = last_report
        pending_frames: list[object] = []
        connected = False

        try:
            port = serial.Serial(
                self._session.port,
                self._session.baudrate,
                timeout=0.1,
            )
            self._configure_input_buffer(port)

            with self._serial_lock:
                self._serial_port = port

            connected = True
            self.connection_changed.emit(True)

            while self._running and not self.isInterruptionRequested():
                try:
                    raw_line = port.read_until(
                        expected=b"\n",
                        size=self.MAX_LINE_BYTES,
                    )
                except (serial.SerialException, OSError) as exc:
                    if self._running and not self.isInterruptionRequested():
                        self.error_occurred.emit(f"Erro durante leitura serial: {exc}")
                    break

                now = time.monotonic()

                if raw_line:
                    try:
                        decoded_line = self._decode_line(raw_line)
                        if not is_ignorable_serial_line(decoded_line):
                            parsed = self._parser.parse_line(
                                decoded_line,
                                self._session,
                            )
                            valid_total += 1
                            pending_frames.append(parsed.frame)
                    except FrameProtocolError as exc:
                        invalid_count += 1
                        invalid_total += 1
                        invalid_by_category[exc.category] = (
                            invalid_by_category.get(exc.category, 0) + 1
                        )
                        last_invalid_message = str(exc)
                    except Exception as exc:
                        self.error_occurred.emit(
                            "Erro inesperado ao processar linha serial: "
                            f"{exc}"
                        )

                should_emit_batch = (
                    len(pending_frames) >= self.FRAME_BATCH_SIZE
                    or (
                        pending_frames
                        and now - last_batch_emit
                        >= self.FRAME_BATCH_MAX_LATENCY_S
                    )
                )
                if should_emit_batch:
                    self._emit_batch(pending_frames)
                    last_batch_emit = now

                if (
                    invalid_count
                    and now - last_report >= self.PROTOCOL_REPORT_INTERVAL_S
                ):
                    self.protocol_error.emit(
                        invalid_count,
                        self._format_protocol_summary(
                            invalid_by_category,
                            last_invalid_message,
                        ),
                    )
                    invalid_count = 0
                    invalid_by_category.clear()
                    last_report = now

                if (
                    valid_total == 0
                    and invalid_total >= self.INCOMPATIBLE_PROTOCOL_INVALID_LIMIT
                    and now - connected_at
                    >= self.INCOMPATIBLE_PROTOCOL_GRACE_S
                ):
                    self.error_occurred.emit(
                        "Nenhum frame válido foi reconhecido. "
                        "Verifique porta, quantidade de canais e versão "
                        "do protocolo."
                    )
                    break

        except serial.SerialException as exc:
            if self._running and not self.isInterruptionRequested():
                self.error_occurred.emit(f"Erro serial: {exc}")

        finally:
            # Entrega os frames válidos que ainda não completaram um lote.
            self._emit_batch(pending_frames)

            if invalid_count:
                self.protocol_error.emit(
                    invalid_count,
                    self._format_protocol_summary(
                        invalid_by_category,
                        last_invalid_message,
                    ),
                )

            self._running = False

            with self._serial_lock:
                port = self._serial_port
                self._serial_port = None

            if port is not None:
                try:
                    if port.is_open:
                        port.close()
                except Exception:
                    pass

            # Mantém a interface em estado coerente mesmo se a abertura falhar.
            self.connection_changed.emit(False)
