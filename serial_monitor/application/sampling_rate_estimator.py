from __future__ import annotations

from dataclasses import dataclass

from serial_monitor.application.communication_monitor import (
    UINT32_MAX,
    sequence_forward_distance,
)


@dataclass(frozen=True, slots=True)
class SamplingRateSnapshot:
    nominal_hz: float
    estimated_hz: float | None
    locked: bool
    completed_windows: int
    rejected_windows: int
    instability_events: int

    @property
    def deviation_percent(self) -> float | None:
        if self.estimated_hz is None or self.nominal_hz <= 0:
            return None
        return 100.0 * (self.estimated_hz - self.nominal_hz) / self.nominal_hz


class SamplingRateEstimator:
    def __init__(
        self,
        nominal_hz: float,
        *,
        window_seconds: float = 5.0,
        lock_after_windows: int = 2,
        smoothing_factor: float = 0.5,
        change_threshold_percent: float = 1.0,
    ) -> None:
        nominal_hz = float(nominal_hz)
        if nominal_hz <= 0:
            raise ValueError("A taxa nominal deve ser maior que zero.")
        if window_seconds <= 0:
            raise ValueError("A janela do estimador deve ser maior que zero.")
        if lock_after_windows <= 0:
            raise ValueError("A quantidade de janelas deve ser positiva.")
        if not 0 < smoothing_factor <= 1:
            raise ValueError("O fator de suavização deve estar entre zero e um.")
        if change_threshold_percent <= 0:
            raise ValueError("O limite de variação deve ser maior que zero.")

        self.nominal_hz = nominal_hz
        self.window_duration_us = round(window_seconds * 1_000_000.0)
        self.lock_after_windows = int(lock_after_windows)
        self.smoothing_factor = float(smoothing_factor)
        self.change_threshold_percent = float(change_threshold_percent)
        self._origin_sequence_id: int | None = None
        self._origin_timestamp_us: int | None = None
        self._estimated_hz: float | None = None
        self._locked = False
        self._completed_windows = 0
        self._rejected_windows = 0
        self._instability_events = 0

    def reset(self) -> None:
        self._origin_sequence_id = None
        self._origin_timestamp_us = None
        self._estimated_hz = None
        self._locked = False
        self._completed_windows = 0
        self._rejected_windows = 0
        self._instability_events = 0

    def reset_window(self) -> None:
        self._origin_sequence_id = None
        self._origin_timestamp_us = None

    def observe(self, sequence_id: int, timestamp_us: int) -> bool:
        if not 0 <= sequence_id <= UINT32_MAX:
            raise ValueError("A sequência deve estar na faixa uint32.")
        if timestamp_us < 0:
            raise ValueError("O timestamp deve ser não negativo.")

        if self._origin_sequence_id is None or self._origin_timestamp_us is None:
            self._origin_sequence_id = sequence_id
            self._origin_timestamp_us = timestamp_us
            return False

        elapsed_us = timestamp_us - self._origin_timestamp_us
        if elapsed_us < self.window_duration_us:
            return False

        elapsed_frames = sequence_forward_distance(
            self._origin_sequence_id,
            sequence_id,
        )
        self._origin_sequence_id = sequence_id
        self._origin_timestamp_us = timestamp_us

        if elapsed_us <= 0 or elapsed_frames <= 0:
            self._rejected_windows += 1
            return False

        measured_hz = elapsed_frames * 1_000_000.0 / elapsed_us
        if not self.nominal_hz * 0.25 <= measured_hz <= self.nominal_hz * 4.0:
            self._rejected_windows += 1
            return False

        if self._locked:
            reference_hz = self._estimated_hz or self.nominal_hz
            deviation = abs(measured_hz - reference_hz) * 100.0 / reference_hz
            if deviation > self.change_threshold_percent:
                self._instability_events += 1
            return False

        if self._estimated_hz is None:
            self._estimated_hz = measured_hz
        else:
            alpha = self.smoothing_factor
            self._estimated_hz = alpha * measured_hz + (1.0 - alpha) * self._estimated_hz
        self._completed_windows += 1
        if self._completed_windows >= self.lock_after_windows:
            self._locked = True
            return True
        return False

    def snapshot(self) -> SamplingRateSnapshot:
        return SamplingRateSnapshot(
            nominal_hz=self.nominal_hz,
            estimated_hz=self._estimated_hz,
            locked=self._locked,
            completed_windows=self._completed_windows,
            rejected_windows=self._rejected_windows,
            instability_events=self._instability_events,
        )
