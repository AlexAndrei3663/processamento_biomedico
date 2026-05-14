from __future__ import annotations

import numpy as np

from serial_monitor.domain.models import ChannelBufferSnapshot, SignalChannelConfig


class RingBuffer:
    """Buffer circular numérico para um canal de aquisição.

    O buffer mantém valores, timestamps e sequência de amostras. A leitura por
    snapshot sempre devolve os dados em ordem cronológica.
    """

    def __init__(self, channel: SignalChannelConfig, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("A capacidade do buffer deve ser maior que zero.")
        self.channel = channel
        self.capacity = capacity
        self._values = np.zeros(capacity, dtype=float)
        self._timestamps_ms = np.zeros(capacity, dtype=np.int64)
        self._sequence_ids = np.zeros(capacity, dtype=np.int64)
        self._write_index = 0
        self._count = 0

    @property
    def count(self) -> int:
        return self._count

    @property
    def is_full(self) -> bool:
        return self._count == self.capacity

    def clear(self) -> None:
        self._values.fill(0.0)
        self._timestamps_ms.fill(0)
        self._sequence_ids.fill(0)
        self._write_index = 0
        self._count = 0

    def append(self, value: float, timestamp_ms: int, sequence_id: int) -> None:
        self._values[self._write_index] = value
        self._timestamps_ms[self._write_index] = timestamp_ms
        self._sequence_ids[self._write_index] = sequence_id

        self._write_index = (self._write_index + 1) % self.capacity
        self._count = min(self._count + 1, self.capacity)

    def _ordered_indices(self) -> np.ndarray:
        if self._count == 0:
            return np.array([], dtype=np.int64)
        if self._count < self.capacity:
            return np.arange(self._count, dtype=np.int64)
        return np.concatenate(
            (
                np.arange(self._write_index, self.capacity, dtype=np.int64),
                np.arange(0, self._write_index, dtype=np.int64),
            )
        )

    def snapshot(self) -> ChannelBufferSnapshot:
        indices = self._ordered_indices()
        values = self._values[indices].copy()
        timestamps_ms = self._timestamps_ms[indices].copy()
        sequence_ids = self._sequence_ids[indices].copy()

        if len(timestamps_ms) > 0:
            x_seconds = (timestamps_ms - timestamps_ms[0]) / 1000.0
            last_value = float(values[-1])
            last_timestamp_ms = int(timestamps_ms[-1])
        else:
            x_seconds = np.array([], dtype=float)
            last_value = None
            last_timestamp_ms = None

        return ChannelBufferSnapshot(
            channel=self.channel,
            sample_count=int(self._count),
            x_seconds=x_seconds,
            values=values,
            timestamps_ms=timestamps_ms,
            sequence_ids=sequence_ids,
            last_value=last_value,
            last_timestamp_ms=last_timestamp_ms,
        )
