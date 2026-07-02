from __future__ import annotations

from typing import Dict

from serial_monitor.domain.enums import SignalType
from serial_monitor.domain.models import SignalPreset


SIGNAL_PRESETS: Dict[SignalType, SignalPreset] = {
    SignalType.ECG: SignalPreset(
        "ECG", "mV", ["baseline", "notch_60hz", "bandpass"], raw_unit="count"
    ),
    SignalType.PPG: SignalPreset(
        "PPG", "a.u.", ["dc_remove", "lowpass"], raw_unit="count"
    ),
    SignalType.OXIMETRIA: SignalPreset(
        "Oximetria", "%", ["moving_average"], raw_unit="%"
    ),
    SignalType.TEMPERATURA: SignalPreset(
        "Temperatura", "°C", ["moving_average"], raw_unit="count"
    ),
    SignalType.RESPIRACAO: SignalPreset(
        "Respiração", "a.u.", ["lowpass"], raw_unit="count"
    ),
    SignalType.EMG: SignalPreset(
        "EMG", "mV", ["highpass", "notch_60hz", "envelope"], raw_unit="count"
    ),
    SignalType.EEG: SignalPreset(
        "EEG", "µV", ["notch_60hz", "bandpass"], raw_unit="count"
    ),
    SignalType.OUTRO: SignalPreset("Outro", "a.u.", [], raw_unit="count"),
}
