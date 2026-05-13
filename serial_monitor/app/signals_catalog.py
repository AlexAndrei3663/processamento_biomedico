from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from serial_monitor.domain.enums import SignalType


@dataclass(frozen=True, slots=True)
class SignalPreset:
    display_name: str
    unit: str
    default_filters: List[str]


SIGNAL_PRESETS: Dict[SignalType, SignalPreset] = {
    SignalType.ECG: SignalPreset("ECG", "mV", ["baseline", "notch_60hz", "bandpass"]),
    SignalType.PPG: SignalPreset("PPG", "a.u.", ["dc_remove", "lowpass"]),
    SignalType.OXIMETRIA: SignalPreset("Oximetria", "%", ["moving_average"]),
    SignalType.TEMPERATURA: SignalPreset("Temperatura", "°C", ["moving_average"]),
    SignalType.RESPIRACAO: SignalPreset("Respiração", "a.u.", ["lowpass"]),
    SignalType.EMG: SignalPreset("EMG", "mV", ["highpass", "notch_60hz", "envelope"]),
    SignalType.EEG: SignalPreset("EEG", "µV", ["notch_60hz", "bandpass"]),
    SignalType.OUTRO: SignalPreset("Outro", "a.u.", []),
}
