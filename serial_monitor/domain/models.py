from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List

import numpy as np

from .enums import ProtocolMode, RecordingState, SignalType


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


@dataclass(frozen=True, slots=True)
class SequenceDiagnostics:
    """Diagnóstico de um contador sequencial com aritmética modular."""

    gap_events: int = 0
    missing_items: int = 0
    duplicate_items: int = 0
    out_of_order_items: int = 0

    @property
    def anomaly_count(self) -> int:
        return self.gap_events + self.duplicate_items + self.out_of_order_items


@dataclass(frozen=True, slots=True)
class CommunicationStats:
    """Contadores de integridade da comunicação durante a sessão."""

    valid_frames: int = 0
    invalid_frames: int = 0
    checksum_errors: int = 0
    timestamp_regressions: int = 0
    sequence: SequenceDiagnostics = field(default_factory=SequenceDiagnostics)

    @property
    def gap_events(self) -> int:
        return self.sequence.gap_events

    @property
    def missing_frames(self) -> int:
        return self.sequence.missing_items

    @property
    def duplicate_frames(self) -> int:
        return self.sequence.duplicate_items

    @property
    def out_of_order_frames(self) -> int:
        return self.sequence.out_of_order_items


@dataclass(slots=True)
class SampleFrame:
    """Quadro multicanal correspondente a um ciclo de varredura."""

    sequence_id: int
    timestamp_us: int
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
    timestamps_us: np.ndarray
    sequence_ids: np.ndarray
    last_value: float | None
    last_timestamp_us: int | None


@dataclass(slots=True)
class AcquisitionSnapshot:
    configured: bool
    running: bool
    communication: CommunicationStats
    last_sequence_id: int | None
    last_timestamp_us: int | None
    channels: Dict[int, ChannelBufferSnapshot]

    @property
    def frames_received(self) -> int:
        return self.communication.valid_frames


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
    timestamps_us: np.ndarray
    sequence_ids: np.ndarray
    last_raw_value: float | None
    last_processed_value: float | None
    last_timestamp_us: int | None
    active_filters: List[str]
    filter_status: List[str]
    metrics: MetricSnapshot
    raw_spectrum: SpectrumSnapshot
    processed_spectrum: SpectrumSnapshot


@dataclass(slots=True)
class ProcessedAcquisitionSnapshot:
    configured: bool
    running: bool
    communication: CommunicationStats
    last_sequence_id: int | None
    last_timestamp_us: int | None
    channels: Dict[int, ProcessedChannelSnapshot]

    @property
    def frames_received(self) -> int:
        return self.communication.valid_frames


@dataclass(frozen=True, slots=True)
class RecordingStatus:
    state: RecordingState = RecordingState.IDLE
    session_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_seconds: float = 0.0
    frames_enqueued: int = 0
    frames_written: int = 0
    queue_size: int = 0
    queue_capacity: int = 0
    file_size_bytes: int = 0
    output_path: Path | None = None
    partial_path: Path | None = None
    end_reason: str | None = None
    error_message: str | None = None

    @property
    def is_active(self) -> bool:
        return self.state in {RecordingState.RECORDING, RecordingState.FINALIZING}


@dataclass(frozen=True, slots=True)
class StoredSessionSummary:
    session_id: str
    created_at: str
    frames_received: int
    gap_events: int
    missing_frames: int
    duplicate_frames: int
    out_of_order_frames: int
    invalid_frames: int
    timestamp_regressions: int
    channel_count: int
    base_sample_rate_hz: int
    channel_labels: List[str]
    metadata_path: Path
    data_path: Path
    state: str = "completed"
    duration_seconds: float = 0.0
    end_reason: str | None = None
    is_partial: bool = False
    format_version: int = 0
    software_version: str = ""
    protocol_version: str = ""
    integrity_status: str = "unknown"
    content_sha256: str | None = None
    first_timestamp_us: int | None = None
    last_timestamp_us: int | None = None
    file_size_bytes: int = 0

    @property
    def time_span_seconds(self) -> float:
        if self.first_timestamp_us is None or self.last_timestamp_us is None:
            return 0.0
        return max(0.0, (self.last_timestamp_us - self.first_timestamp_us) / 1_000_000.0)


@dataclass(frozen=True, slots=True)
class StoredSessionData:
    summary: StoredSessionSummary
    session: SessionConfig
    snapshot: AcquisitionSnapshot
    active_filters: Dict[int, List[str]]
    loaded_start_us: int | None = None
    loaded_end_us: int | None = None
    loaded_frames: int = 0
    total_frames: int = 0
    decimated_for_display: bool = False


@dataclass(frozen=True, slots=True)
class SessionRecoveryResult:
    session_id: str
    source_path: Path
    output_path: Path
    frames_recovered: int
    frames_discarded: int
    integrity_status: str


@dataclass(frozen=True, slots=True)
class FilterDefinition:
    filter_id: str
    display_name: str
    description: str
    processor: Callable[[np.ndarray, float, SignalChannelConfig], np.ndarray]


@dataclass(frozen=True, slots=True)
class SessionPreset:
    name: str
    created_at: str
    updated_at: str
    port: str
    baudrate: int
    base_sample_rate_hz: int
    window_size: int
    signal_order_text: str
    path: Path


@dataclass(frozen=True, slots=True)
class ParsedFrame:
    frame: SampleFrame


@dataclass(frozen=True, slots=True)
class SignalPreset:
    display_name: str
    unit: str
    default_filters: List[str]
