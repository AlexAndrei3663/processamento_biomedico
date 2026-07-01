from __future__ import annotations

from typing import Dict

from serial_monitor.application.communication_monitor import CommunicationMonitor
from serial_monitor.domain.models import AcquisitionSnapshot, SampleFrame, SessionConfig
from serial_monitor.processing.ring_buffer import RingBuffer


class LiveAcquisitionService:
    """Modelo de aquisição ao vivo com diagnóstico de integridade.

    O serviço recebe ``SampleFrame`` já parseado, valida continuidade sequencial e
    temporal e distribui apenas quadros aceitos para buffers circulares independentes.
    """

    def __init__(self) -> None:
        self._session: SessionConfig | None = None
        self._buffers: Dict[int, RingBuffer] = {}
        self._running = False
        self._communication = CommunicationMonitor()

    @property
    def is_configured(self) -> bool:
        return self._session is not None

    @property
    def is_running(self) -> bool:
        return self._running

    def configure(self, session: SessionConfig) -> None:
        self._session = session
        self._buffers = {
            channel.index: RingBuffer(channel=channel, capacity=session.window_size)
            for channel in session.channels
        }
        self._communication.reset()
        self._running = False

    def start(self) -> None:
        if self._session is None:
            raise RuntimeError("Aquisição não configurada.")
        self._running = True

    def stop(self) -> None:
        self._running = False

    def reset(self) -> None:
        for buffer in self._buffers.values():
            buffer.clear()
        self._communication.reset()

    def record_invalid_frame(self) -> None:
        self._communication.record_invalid_frame()

    def record_checksum_error(self) -> None:
        self._communication.record_checksum_error()

    def ingest_frame(self, frame: SampleFrame) -> bool:
        """Insere um quadro e retorna ``True`` somente quando ele foi aceito."""

        if self._session is None:
            raise RuntimeError("Aquisição não configurada.")

        expected = self._session.channel_count
        received = len(frame.values_in_order)
        if received != expected:
            self._communication.record_invalid_frame()
            raise ValueError(f"Frame possui {received} valores, mas a sessão espera {expected}.")

        channel_values: Dict[int, float] = {}
        for channel in self._session.channels:
            value = frame.value_for_channel(channel.index)
            if value is None:
                self._communication.record_invalid_frame()
                raise ValueError(f"Frame não contém valor para o canal {channel.index}.")
            channel_values[channel.index] = value

        if not self._communication.register_frame(frame):
            return False

        for channel_index, value in channel_values.items():
            self._buffers[channel_index].append(
                value=value,
                timestamp_us=frame.timestamp_us,
                packet_sequence=frame.packet_sequence,
                scan_sequence=frame.scan_sequence,
            )
        return True

    def snapshot(self) -> AcquisitionSnapshot:
        return AcquisitionSnapshot(
            configured=self._session is not None,
            running=self._running,
            communication=self._communication.snapshot(),
            last_packet_sequence=self._communication.last_packet_sequence,
            last_scan_sequence=self._communication.last_scan_sequence,
            last_timestamp_us=self._communication.last_timestamp_us,
            channels={index: buffer.snapshot() for index, buffer in self._buffers.items()},
        )
