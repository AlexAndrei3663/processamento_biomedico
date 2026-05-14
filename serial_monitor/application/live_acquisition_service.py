from __future__ import annotations

from typing import Dict

from serial_monitor.domain.models import AcquisitionSnapshot, SampleFrame, SessionConfig
from serial_monitor.processing.ring_buffer import RingBuffer


class LiveAcquisitionService:
    """Modelo de aquisição ao vivo.

    Recebe SampleFrame já parseado, valida a quantidade de canais e distribui os
    valores para buffers circulares independentes, um por canal.
    """

    def __init__(self) -> None:
        self._session: SessionConfig | None = None
        self._buffers: Dict[int, RingBuffer] = {}
        self._running = False
        self._frames_received = 0
        self._sequence_gaps = 0
        self._last_sequence_id: int | None = None
        self._last_timestamp_ms: int | None = None

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
        self._frames_received = 0
        self._sequence_gaps = 0
        self._last_sequence_id = None
        self._last_timestamp_ms = None
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
        self._frames_received = 0
        self._sequence_gaps = 0
        self._last_sequence_id = None
        self._last_timestamp_ms = None

    def ingest_frame(self, frame: SampleFrame) -> None:
        if self._session is None:
            raise RuntimeError("Aquisição não configurada.")

        expected = self._session.channel_count
        received = len(frame.values_in_order)
        if received != expected:
            raise ValueError(f"Frame possui {received} valores, mas a sessão espera {expected}.")

        if self._last_sequence_id is not None:
            expected_next = self._last_sequence_id + 1
            if frame.sequence_id != expected_next:
                self._sequence_gaps += 1

        for channel in self._session.channels:
            value = frame.value_for_channel(channel.index)
            if value is None:
                raise ValueError(f"Frame não contém valor para o canal {channel.index}.")
            self._buffers[channel.index].append(
                value=value,
                timestamp_ms=frame.timestamp_ms,
                sequence_id=frame.sequence_id,
            )

        self._frames_received += 1
        self._last_sequence_id = frame.sequence_id
        self._last_timestamp_ms = frame.timestamp_ms

    def snapshot(self) -> AcquisitionSnapshot:
        return AcquisitionSnapshot(
            configured=self._session is not None,
            running=self._running,
            frames_received=self._frames_received,
            sequence_gaps=self._sequence_gaps,
            last_sequence_id=self._last_sequence_id,
            last_timestamp_ms=self._last_timestamp_ms,
            channels={index: buffer.snapshot() for index, buffer in self._buffers.items()},
        )
