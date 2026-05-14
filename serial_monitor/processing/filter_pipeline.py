from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Set

import numpy as np
from scipy import signal

from serial_monitor.domain.enums import SignalType
from serial_monitor.domain.models import (
    AcquisitionSnapshot,
    ChannelBufferSnapshot,
    MetricSnapshot,
    ProcessedAcquisitionSnapshot,
    ProcessedChannelSnapshot,
    SessionConfig,
    SignalChannelConfig,
)
from serial_monitor.processing.spectrum import calculate_single_sided_spectrum


@dataclass(frozen=True, slots=True)
class FilterDefinition:
    filter_id: str
    display_name: str
    description: str
    processor: Callable[[np.ndarray, float, SignalChannelConfig], np.ndarray]


def _as_float_array(values: np.ndarray) -> np.ndarray:
    return np.asarray(values, dtype=float)


def _safe_sos_filter(values: np.ndarray, sos: np.ndarray) -> np.ndarray:
    """Aplica filtro zero-phase quando houver amostras suficientes.

    Em janelas muito curtas, `sosfiltfilt` pode falhar por falta de pontos para
    padding. Nesse caso, retorna o vetor original para manter a aquisição estável.
    """
    if values.size < 12:
        return values.copy()
    try:
        return signal.sosfiltfilt(sos, values)
    except ValueError:
        return values.copy()


def _normalized_cutoff(cutoff_hz: float, sample_rate_hz: float) -> float | None:
    nyquist = sample_rate_hz / 2.0
    if nyquist <= 0:
        return None
    cutoff = min(cutoff_hz, nyquist * 0.90)
    if cutoff <= 0:
        return None
    normalized = cutoff / nyquist
    if not 0 < normalized < 1:
        return None
    return normalized


def _lowpass_cutoff(channel: SignalChannelConfig) -> float:
    if channel.signal_type == SignalType.RESPIRACAO:
        return 2.0
    if channel.signal_type == SignalType.TEMPERATURA:
        return 1.0
    if channel.signal_type == SignalType.PPG:
        return 12.0
    if channel.signal_type == SignalType.OXIMETRIA:
        return 3.0
    return 40.0


def _bandpass_edges(channel: SignalChannelConfig) -> tuple[float, float]:
    if channel.signal_type == SignalType.EMG:
        return 20.0, 150.0
    if channel.signal_type == SignalType.EEG:
        return 0.5, 45.0
    if channel.signal_type == SignalType.PPG:
        return 0.5, 12.0
    if channel.signal_type == SignalType.RESPIRACAO:
        return 0.05, 2.0
    return 0.5, 40.0


def remove_dc(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    values = _as_float_array(values)
    if values.size == 0:
        return values.copy()
    return values - float(np.mean(values))


def moving_average(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    values = _as_float_array(values)
    if values.size < 3:
        return values.copy()
    window = int(max(3, min(values.size, round(sample_rate_hz * 0.05))))
    if window % 2 == 0:
        window += 1
    if window > values.size:
        window = values.size if values.size % 2 == 1 else values.size - 1
    if window < 3:
        return values.copy()
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(values, kernel, mode="same")


def lowpass(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    values = _as_float_array(values)
    normalized = _normalized_cutoff(_lowpass_cutoff(channel), sample_rate_hz)
    if normalized is None:
        return values.copy()
    sos = np.asarray(signal.butter(4, normalized, btype="lowpass", output="sos"), dtype=float)
    return _safe_sos_filter(values, sos)


def highpass(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    values = _as_float_array(values)
    cutoff = 20.0 if channel.signal_type == SignalType.EMG else 0.5
    normalized = _normalized_cutoff(cutoff, sample_rate_hz)
    if normalized is None:
        return values.copy()
    sos = np.asarray(signal.butter(4, normalized, btype="highpass", output="sos"), dtype=float)
    return _safe_sos_filter(values, sos)


def baseline(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    values = _as_float_array(values)
    normalized = _normalized_cutoff(0.5, sample_rate_hz)
    if normalized is None:
        return values.copy()
    sos = np.asarray(signal.butter(2, normalized, btype="highpass", output="sos"), dtype=float)
    return _safe_sos_filter(values, sos)


def bandpass(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    values = _as_float_array(values)
    nyquist = sample_rate_hz / 2.0
    if nyquist <= 0:
        return values.copy()

    low_hz, high_hz = _bandpass_edges(channel)
    high_hz = min(high_hz, nyquist * 0.90)
    if not 0 < low_hz < high_hz < nyquist:
        return values.copy()

    sos = np.asarray(signal.butter(4, [low_hz / nyquist, high_hz / nyquist], btype="bandpass", output="sos"), dtype=float)
    return _safe_sos_filter(values, sos)


def notch_60hz(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    values = _as_float_array(values)
    if values.size < 24 or sample_rate_hz <= 130:
        return values.copy()
    try:
        b, a = signal.iirnotch(w0=60.0, Q=30.0, fs=sample_rate_hz)
        return signal.filtfilt(b, a, values)
    except ValueError:
        return values.copy()


def envelope(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    values = _as_float_array(values)
    if values.size == 0:
        return values.copy()
    rectified = np.abs(values)
    return moving_average(rectified, sample_rate_hz, channel)


FILTER_DEFINITIONS: Dict[str, FilterDefinition] = {
    "baseline": FilterDefinition(
        "baseline",
        "Remover linha de base",
        "Filtro passa-altas suave para reduzir deriva lenta da linha de base.",
        baseline,
    ),
    "notch_60hz": FilterDefinition(
        "notch_60hz",
        "Notch 60 Hz",
        "Atenua interferência de rede elétrica em 60 Hz.",
        notch_60hz,
    ),
    "bandpass": FilterDefinition(
        "bandpass",
        "Passa-faixa",
        "Aplica faixa típica conforme o tipo de sinal configurado.",
        bandpass,
    ),
    "dc_remove": FilterDefinition(
        "dc_remove",
        "Remover nível DC",
        "Subtrai a média da janela atual.",
        remove_dc,
    ),
    "lowpass": FilterDefinition(
        "lowpass",
        "Passa-baixas",
        "Reduz componentes rápidas conforme o tipo de sinal.",
        lowpass,
    ),
    "moving_average": FilterDefinition(
        "moving_average",
        "Média móvel",
        "Suavização temporal simples.",
        moving_average,
    ),
    "highpass": FilterDefinition(
        "highpass",
        "Passa-altas",
        "Remove componentes lentas; usado principalmente em EMG.",
        highpass,
    ),
    "envelope": FilterDefinition(
        "envelope",
        "Envelope",
        "Retificação seguida de suavização, útil para EMG.",
        envelope,
    ),
}


class FilterPipeline:
    """Aplica uma sequência determinística de filtros a um canal."""

    FILTER_ORDER = [
        "baseline",
        "dc_remove",
        "highpass",
        "notch_60hz",
        "bandpass",
        "lowpass",
        "moving_average",
        "envelope",
    ]

    def __init__(self, definitions: Dict[str, FilterDefinition] | None = None) -> None:
        self.definitions = definitions or FILTER_DEFINITIONS

    def apply(
        self,
        values: np.ndarray,
        channel: SignalChannelConfig,
        active_filters: Iterable[str],
    ) -> tuple[np.ndarray, List[str]]:
        output = _as_float_array(values).copy()
        active: Set[str] = set(active_filters)
        status: List[str] = []

        for filter_id in self.FILTER_ORDER:
            if filter_id not in active:
                continue
            definition = self.definitions.get(filter_id)
            if definition is None:
                status.append(f"Filtro desconhecido ignorado: {filter_id}")
                continue
            before = output
            output = definition.processor(output, channel.sample_rate_hz, channel)
            if output.shape != before.shape:
                output = before.copy()
                status.append(f"Filtro {filter_id} ignorado: tamanho de saída inválido.")
            else:
                status.append(f"Filtro aplicado: {definition.display_name}")

        return output, status


def calculate_metrics(values: np.ndarray) -> MetricSnapshot:
    values = _as_float_array(values)
    if values.size == 0:
        return MetricSnapshot()
    return MetricSnapshot(
        mean=float(np.mean(values)),
        rms=float(np.sqrt(np.mean(np.square(values)))),
        minimum=float(np.min(values)),
        maximum=float(np.max(values)),
    )


class ProcessingService:
    """Mantém o estado de filtros ativos e gera snapshots processados."""

    def __init__(self, pipeline: FilterPipeline | None = None) -> None:
        self._session: SessionConfig | None = None
        self._enabled_filters: Dict[int, Set[str]] = {}
        self.pipeline = pipeline or FilterPipeline()

    def configure(self, session: SessionConfig) -> None:
        self._session = session
        # Os filtros ficam disponíveis na interface, mas começam desativados.
        self._enabled_filters = {channel.index: set() for channel in session.channels}

    def reset(self) -> None:
        if self._session is None:
            self._enabled_filters = {}
            return
        self._enabled_filters = {channel.index: set() for channel in self._session.channels}

    def set_filter_enabled(self, channel_index: int, filter_id: str, enabled: bool) -> None:
        if self._session is None:
            raise RuntimeError("Processamento não configurado.")
        if channel_index not in self._enabled_filters:
            raise ValueError(f"Canal {channel_index} não existe no processamento.")
        if filter_id not in FILTER_DEFINITIONS:
            raise ValueError(f"Filtro desconhecido: {filter_id}")

        if enabled:
            self._enabled_filters[channel_index].add(filter_id)
        else:
            self._enabled_filters[channel_index].discard(filter_id)


    def enabled_filters_snapshot(self) -> Dict[int, List[str]]:
        """Retorna uma cópia serializável dos filtros ativos por canal."""
        return {index: sorted(filters) for index, filters in self._enabled_filters.items()}

    def set_enabled_filters(self, filters_by_channel: Dict[int, List[str]]) -> None:
        """Restaura filtros ativos, ignorando filtros desconhecidos.

        Usado ao abrir uma sessão armazenada. A validação é conservadora para não
        impedir a abertura de arquivos antigos caso algum filtro deixe de existir.
        """
        if self._session is None:
            raise RuntimeError("Processamento não configurado.")

        restored: Dict[int, Set[str]] = {channel.index: set() for channel in self._session.channels}
        for channel_index, filter_ids in filters_by_channel.items():
            if channel_index not in restored:
                continue
            for filter_id in filter_ids:
                if filter_id in FILTER_DEFINITIONS:
                    restored[channel_index].add(filter_id)
        self._enabled_filters = restored

    def active_filters_for(self, channel_index: int) -> List[str]:
        return sorted(self._enabled_filters.get(channel_index, set()))

    def process(self, snapshot: AcquisitionSnapshot) -> ProcessedAcquisitionSnapshot:
        processed_channels: Dict[int, ProcessedChannelSnapshot] = {}

        for index, channel_snapshot in snapshot.channels.items():
            active_filters = self.active_filters_for(index)
            processed_values, status = self._process_channel(channel_snapshot, active_filters)
            last_processed_value = None
            if processed_values.size:
                last_processed_value = float(processed_values[-1])

            raw_spectrum = calculate_single_sided_spectrum(
                channel_snapshot.values,
                channel_snapshot.channel.sample_rate_hz,
            )
            processed_spectrum = calculate_single_sided_spectrum(
                processed_values,
                channel_snapshot.channel.sample_rate_hz,
            )

            processed_channels[index] = ProcessedChannelSnapshot(
                channel=channel_snapshot.channel,
                sample_count=channel_snapshot.sample_count,
                x_seconds=channel_snapshot.x_seconds,
                raw_values=channel_snapshot.values,
                processed_values=processed_values,
                timestamps_ms=channel_snapshot.timestamps_ms,
                sequence_ids=channel_snapshot.sequence_ids,
                last_raw_value=channel_snapshot.last_value,
                last_processed_value=last_processed_value,
                last_timestamp_ms=channel_snapshot.last_timestamp_ms,
                active_filters=active_filters,
                filter_status=status,
                metrics=calculate_metrics(processed_values),
                raw_spectrum=raw_spectrum,
                processed_spectrum=processed_spectrum,
            )

        return ProcessedAcquisitionSnapshot(
            configured=snapshot.configured,
            running=snapshot.running,
            frames_received=snapshot.frames_received,
            sequence_gaps=snapshot.sequence_gaps,
            last_sequence_id=snapshot.last_sequence_id,
            last_timestamp_ms=snapshot.last_timestamp_ms,
            channels=processed_channels,
        )

    def _process_channel(
        self,
        snapshot: ChannelBufferSnapshot,
        active_filters: List[str],
    ) -> tuple[np.ndarray, List[str]]:
        raw = _as_float_array(snapshot.values)
        if not active_filters:
            return raw.copy(), ["Sem filtros ativos."]
        if raw.size == 0:
            return raw.copy(), ["Sem amostras para processar."]
        return self.pipeline.apply(raw, snapshot.channel, active_filters)
