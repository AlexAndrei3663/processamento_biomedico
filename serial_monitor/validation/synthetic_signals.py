from __future__ import annotations

import math
from collections.abc import Iterator

import numpy as np

from serial_monitor.domain.enums import SignalType
from serial_monitor.domain.models import SampleFrame, SessionConfig


class SyntheticFrameGenerator:
    """Gera sinais determinísticos para validar o fluxo completo sem hardware."""

    def __init__(self, session: SessionConfig, *, seed: int = 2026) -> None:
        self.session = session
        self._rng = np.random.default_rng(seed)

    def frames(
        self,
        frame_count: int,
        *,
        start_sequence: int = 0,
        start_timestamp_us: int = 0,
    ) -> Iterator[SampleFrame]:
        sample_rate = float(self.session.base_sample_rate_hz)
        for index in range(max(0, int(frame_count))):
            t = index / sample_rate
            values = [
                self._value(channel.signal_type, t, channel.index)
                for channel in self.session.channels
            ]
            timestamp_us = start_timestamp_us + round(index * 1_000_000.0 / sample_rate)
            sequence_id = (start_sequence + index) % (1 << 32)
            yield SampleFrame(
                sequence_id=sequence_id,
                timestamp_us=timestamp_us,
                values_by_channel_index={
                    channel.index: value
                    for channel, value in zip(self.session.channels, values, strict=True)
                },
                values_in_order=values,
            )

    def _value(self, signal_type: SignalType, t: float, channel_index: int) -> float:
        noise = float(self._rng.normal(0.0, 1.0))
        if signal_type == SignalType.ECG:
            return self._ecg(t, channel_index) + 2.0 * noise
        if signal_type == SignalType.PPG:
            return self._ppg(t) + 5.0 * noise
        if signal_type == SignalType.OXIMETRIA:
            return 97.0 + 0.25 * math.sin(2.0 * math.pi * 0.08 * t) + 0.02 * noise
        if signal_type == SignalType.RESPIRACAO:
            return 1000.0 * math.sin(2.0 * math.pi * 0.25 * t) + noise
        if signal_type == SignalType.TEMPERATURA:
            return 36.5 + 0.1 * math.sin(2.0 * math.pi * 0.01 * t) + 0.01 * noise
        if signal_type == SignalType.EMG:
            carrier = math.sin(2.0 * math.pi * 90.0 * t)
            envelope = 0.5 + 0.5 * math.sin(2.0 * math.pi * 0.5 * t) ** 2
            return 500.0 * carrier * envelope + 10.0 * noise
        if signal_type == SignalType.EEG:
            return 100.0 * math.sin(2.0 * math.pi * 10.0 * t) + 3.0 * noise
        return 100.0 * math.sin(2.0 * math.pi * 2.0 * t) + noise

    @staticmethod
    def _gaussian(phase: float, center: float, width: float, amplitude: float) -> float:
        delta = phase - center
        return amplitude * math.exp(-0.5 * (delta / width) ** 2)

    def _ecg(self, t: float, channel_index: int) -> float:
        period = 60.0 / 72.0
        phase = (t + channel_index * 0.008) % period
        value = (
            self._gaussian(phase, 0.10, 0.025, 80.0)
            + self._gaussian(phase, 0.19, 0.012, -120.0)
            + self._gaussian(phase, 0.21, 0.010, 900.0)
            + self._gaussian(phase, 0.235, 0.014, -220.0)
            + self._gaussian(phase, 0.42, 0.055, 260.0)
        )
        baseline = 20.0 * math.sin(2.0 * math.pi * 0.25 * t)
        gain = 1.0 if channel_index % 2 == 0 else 0.82
        return gain * value + baseline

    @staticmethod
    def _ppg(t: float) -> float:
        period = 60.0 / 72.0
        phase = (t % period) / period
        systolic = math.exp(-7.0 * phase) * (1.0 - math.exp(-35.0 * phase))
        dicrotic = 0.18 * math.exp(-80.0 * (phase - 0.48) ** 2)
        return 50_000.0 + 6_000.0 * (systolic + dicrotic)
