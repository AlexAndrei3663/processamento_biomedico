from __future__ import annotations

from enum import Enum


class SignalType(str, Enum):
    ECG = "ecg"
    PPG = "ppg"
    OXIMETRIA = "oximetria"
    TEMPERATURA = "temperatura"
    RESPIRACAO = "respiracao"
    EMG = "emg"
    EEG = "eeg"
    OUTRO = "outro"

    @classmethod
    def from_text(cls, text: str) -> "SignalType":
        normalized = text.strip().lower()
        aliases = {
            "spo2": cls.OXIMETRIA,
            "spo_2": cls.OXIMETRIA,
            "resp": cls.RESPIRACAO,
            "respiração": cls.RESPIRACAO,
            "temp": cls.TEMPERATURA,
            "temperature": cls.TEMPERATURA,
            "other": cls.OUTRO,
        }
        return aliases.get(normalized, cls(normalized))


class ConversionModel(str, Enum):
    IDENTITY = "identity"
    LINEAR = "linear"
    POLYNOMIAL = "polynomial"
    LOOKUP_TABLE = "lookup_table"


class ProtocolMode(str, Enum):
    FRAME_CSV = "frame_csv"


class RecordingState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WindowPageIndex(int, Enum):
    MENU_PAGE = 0
    CONFIG_PAGE = 1
    LIVE_PAGE = 2
    STORED_PAGE = 3
