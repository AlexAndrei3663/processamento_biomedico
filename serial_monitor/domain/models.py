from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

from .enums import ProtocolMode, SignalType


@dataclass(slots=True)
class SignalChannelConfig:
    index: int
    signal_type: SignalType
    display_name: str
    unit: str
    sample_rate_hz: float
    scale: float = 1.0
    offset: float = 0.0
    default_filters: List[str] = field(default_factory=list)

    @property
    def channel_id(self) -> str:
        return f"ch{self.index}_{self.signal_type.value}"


@dataclass(slots=True)
class SessionConfig:
    port: str
    baudrate: int
    base_sample_rate_hz: int
    window_size: int
    protocol_mode: ProtocolMode
    channels: List[SignalChannelConfig]

    def __post_init__(self) -> None:
        if not self.port.strip():
            raise ValueError("A porta serial não pode ser vazia.")
        if self.baudrate <= 0:
            raise ValueError("O baudrate deve ser maior que zero.")
        if self.base_sample_rate_hz <= 0:
            raise ValueError("A taxa base de amostragem deve ser maior que zero.")
        if self.window_size <= 0:
            raise ValueError("O tamanho da janela deve ser maior que zero.")
        if not self.channels:
            raise ValueError("A sessão deve ter ao menos um canal configurado.")

        indexes = [channel.index for channel in self.channels]
        if sorted(indexes) != list(range(len(self.channels))):
            raise ValueError("Os índices dos canais devem ser sequenciais a partir de zero.")

    @property
    def signal_order(self) -> List[SignalType]:
        return [channel.signal_type for channel in self.channels]

    @property
    def channel_count(self) -> int:
        return len(self.channels)

    def channel_by_index(self, index: int) -> SignalChannelConfig:
        try:
            return self.channels[index]
        except IndexError as exc:
            raise ValueError(f"Canal de índice {index} não existe na sessão.") from exc


@dataclass(slots=True)
class SampleFrame:
    sequence_id: int
    timestamp_ms: int
    values_by_channel_index: Dict[int, float]
    values_in_order: List[float]

    def value_for_channel(self, channel_index: int) -> float | None:
        return self.values_by_channel_index.get(channel_index)


@dataclass(slots=True)
class ChannelBufferSnapshot:
    channel: SignalChannelConfig
    sample_count: int
    x_seconds: np.ndarray
    values: np.ndarray
    timestamps_ms: np.ndarray
    sequence_ids: np.ndarray
    last_value: float | None
    last_timestamp_ms: int | None


@dataclass(slots=True)
class AcquisitionSnapshot:
    configured: bool
    running: bool
    frames_received: int
    sequence_gaps: int
    last_sequence_id: int | None
    last_timestamp_ms: int | None
    channels: Dict[int, ChannelBufferSnapshot]


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    mean: float | None = None
    rms: float | None = None
    minimum: float | None = None
    maximum: float | None = None


@dataclass(frozen=True, slots=True)
class SpectrumSnapshot:
    frequencies_hz: np.ndarray
    magnitudes: np.ndarray
    peak_frequency_hz: float | None = None
    peak_magnitude: float | None = None
    resolution_hz: float | None = None


@dataclass(slots=True)
class ProcessedChannelSnapshot:
    channel: SignalChannelConfig
    sample_count: int
    x_seconds: np.ndarray
    raw_values: np.ndarray
    processed_values: np.ndarray
    timestamps_ms: np.ndarray
    sequence_ids: np.ndarray
    last_raw_value: float | None
    last_processed_value: float | None
    last_timestamp_ms: int | None
    active_filters: List[str]
    filter_status: List[str]
    metrics: MetricSnapshot
    raw_spectrum: SpectrumSnapshot
    processed_spectrum: SpectrumSnapshot


@dataclass(slots=True)
class ProcessedAcquisitionSnapshot:
    configured: bool
    running: bool
    frames_received: int
    sequence_gaps: int
    last_sequence_id: int | None
    last_timestamp_ms: int | None
    channels: Dict[int, ProcessedChannelSnapshot]
