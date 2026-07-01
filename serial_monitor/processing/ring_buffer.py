from __future__ import annotations

import numpy as np

from serial_monitor.domain.models import ChannelBufferSnapshot, SignalChannelConfig


class RingBuffer:
    """Buffer circular de visualização para um canal.

    O buffer mantém valor, timestamp em microssegundos e os contadores de pacote e
    varredura. O snapshot sempre devolve os dados em ordem cronológica.
    """

    def __init__(self, channel: SignalChannelConfig, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("A capacidade do buffer deve ser maior que zero.")
        self.channel = channel
        self.capacity = capacity
        self._values = np.zeros(capacity, dtype=float)
        self._timestamps_us = np.zeros(capacity, dtype=np.uint64)
        self._packet_sequences = np.zeros(capacity, dtype=np.uint32)
        self._scan_sequences = np.zeros(capacity, dtype=np.uint32)
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
        self._timestamps_us.fill(0)
        self._packet_sequences.fill(0)
        self._scan_sequences.fill(0)
        self._write_index = 0
        self._count = 0

    def append(
        self,
        value: float,
        timestamp_us: int,
        packet_sequence: int,
        scan_sequence: int,
    ) -> None:
        self._values[self._write_index] = value
        self._timestamps_us[self._write_index] = timestamp_us
        self._packet_sequences[self._write_index] = packet_sequence
        self._scan_sequences[self._write_index] = scan_sequence

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
        timestamps_us = self._timestamps_us[indices].copy()
        packet_sequences = self._packet_sequences[indices].copy()
        scan_sequences = self._scan_sequences[indices].copy()

        if len(timestamps_us) > 0:
            x_seconds = (timestamps_us.astype(np.float64) - float(timestamps_us[0])) / 1_000_000.0
            last_value = float(values[-1])
            last_timestamp_us = int(timestamps_us[-1])
        else:
            x_seconds = np.array([], dtype=float)
            last_value = None
            last_timestamp_us = None

        return ChannelBufferSnapshot(
            channel=self.channel,
            sample_count=int(self._count),
            x_seconds=x_seconds,
            values=values,
            timestamps_us=timestamps_us,
            packet_sequences=packet_sequences,
            scan_sequences=scan_sequences,
            last_value=last_value,
            last_timestamp_us=last_timestamp_us,
        )
