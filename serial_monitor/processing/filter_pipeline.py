from __future__ import annotations

from typing import Dict, Iterable, List, Set

import numpy as np
from scipy import signal

from serial_monitor.application.conversion_service import ConversionService
from serial_monitor.domain.models import (
    AcquisitionSnapshot,
    ChannelBufferSnapshot,
    MetricSnapshot,
    ProcessedAcquisitionSnapshot,
    ProcessedChannelSnapshot,
    SessionConfig,
    SpectrumSnapshot,
    SignalChannelConfig,
    FilterDefinition,
)
from serial_monitor.processing.spectrum import calculate_single_sided_spectrum
from serial_monitor.processing.filter_config import FilterParameters
from serial_monitor.processing.filter_runtime import (
    DISPLAY_FILTER_ORDER,
    FILTER_ORDER as RUNTIME_FILTER_ORDER,
    apply_filter as apply_configured_filter,
    expand_filter_ids,
)


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


def remove_dc(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    values = _as_float_array(values)
    if values.size == 0:
        return values.copy()
    return values - float(np.mean(values))


def moving_average(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    parameters = FilterParameters.defaults_for_sample_rate(sample_rate_hz)
    return apply_configured_filter("moving_average", values, sample_rate_hz, parameters)

def lowpass(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    parameters = FilterParameters.defaults_for_sample_rate(sample_rate_hz)
    return apply_configured_filter("lowpass", values, sample_rate_hz, parameters)

def highpass(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    parameters = FilterParameters.defaults_for_sample_rate(sample_rate_hz)
    return apply_configured_filter("highpass", values, sample_rate_hz, parameters)

def baseline(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    parameters = FilterParameters.defaults_for_sample_rate(sample_rate_hz)
    return apply_configured_filter("baseline", values, sample_rate_hz, parameters)

def bandpass(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    parameters = FilterParameters.defaults_for_sample_rate(sample_rate_hz)
    output = apply_configured_filter("highpass", values, sample_rate_hz, parameters)
    return apply_configured_filter("lowpass", output, sample_rate_hz, parameters)

def notch_60hz(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    parameters = FilterParameters.defaults_for_sample_rate(sample_rate_hz)
    return apply_configured_filter("notch_60hz", values, sample_rate_hz, parameters)

def envelope(values: np.ndarray, sample_rate_hz: float, channel: SignalChannelConfig) -> np.ndarray:
    parameters = FilterParameters.defaults_for_sample_rate(sample_rate_hz)
    return apply_configured_filter("envelope", values, sample_rate_hz, parameters)

FILTER_DEFINITIONS: Dict[str, FilterDefinition] = {
    "baseline": FilterDefinition(
        "baseline",
        "Remover linha de base",
        "Passa-altas suave de 0,5 Hz para reduzir deriva lenta.",
        baseline,
    ),
    "dc_remove": FilterDefinition(
        "dc_remove",
        "Remover nível DC",
        "Subtrai a média da janela atual.",
        remove_dc,
    ),
    "highpass": FilterDefinition(
        "highpass",
        "Passa-altas",
        "Frequência de corte configurável, disponível para qualquer sinal.",
        highpass,
    ),
    "bandpass": FilterDefinition(
        "bandpass",
        "Passa-faixa (HP + LP)",
        "Atalho que habilita simultaneamente passa-altas e passa-baixas.",
        bandpass,
    ),
    "notch_60hz": FilterDefinition(
        "notch_60hz",
        "Notch 60 Hz",
        "Atenua interferência de rede elétrica em 60 Hz.",
        notch_60hz,
    ),
    "lowpass": FilterDefinition(
        "lowpass",
        "Passa-baixas",
        "Frequência de corte configurável, disponível para qualquer sinal.",
        lowpass,
    ),
    "moving_average": FilterDefinition(
        "moving_average",
        "Média móvel",
        "Suavização temporal simples.",
        moving_average,
    ),
    "envelope": FilterDefinition(
        "envelope",
        "Envelope",
        "Retificação seguida de suavização.",
        envelope,
    ),
}

class FilterPipeline:
    """Aplica filtros universais em ordem determinística."""

    FILTER_ORDER = list(RUNTIME_FILTER_ORDER)
    DISPLAY_ORDER = list(DISPLAY_FILTER_ORDER)

    def __init__(self, definitions: Dict[str, FilterDefinition] | None = None) -> None:
        self.definitions = definitions or FILTER_DEFINITIONS

    def apply(
        self,
        values: np.ndarray,
        channel: SignalChannelConfig,
        active_filters: Iterable[str],
        parameters: FilterParameters | None = None,
    ) -> tuple[np.ndarray, List[str]]:
        output = _as_float_array(values).copy()
        active = expand_filter_ids(active_filters)
        parameters = parameters or FilterParameters.defaults_for_sample_rate(
            channel.sample_rate_hz
        )
        parameters = parameters.validated(channel.sample_rate_hz)
        status: List[str] = []

        for filter_id in self.FILTER_ORDER:
            if filter_id not in active:
                continue
            definition = self.definitions.get(filter_id)
            if definition is None:
                status.append(f"Filtro desconhecido ignorado: {filter_id}")
                continue
            before = output
            output = apply_configured_filter(
                filter_id,
                output,
                channel.sample_rate_hz,
                parameters,
            )
            if output.shape != before.shape:
                output = before.copy()
                status.append(
                    f"Filtro {filter_id} ignorado: tamanho de saída inválido."
                )
                continue
            if filter_id == "highpass":
                detail = f" ({parameters.highpass_cutoff_hz:g} Hz)"
            elif filter_id == "lowpass":
                detail = f" ({parameters.lowpass_cutoff_hz:g} Hz)"
            else:
                detail = ""
            status.append(f"Filtro aplicado: {definition.display_name}{detail}")
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
    """Mantém filtros e parâmetros ativos e gera snapshots processados."""

    def __init__(
        self,
        pipeline: FilterPipeline | None = None,
        conversion_service: ConversionService | None = None,
    ) -> None:
        self._session: SessionConfig | None = None
        self._enabled_filters: Dict[int, Set[str]] = {}
        self._filter_parameters: Dict[int, FilterParameters] = {}
        self.pipeline = pipeline or FilterPipeline()
        self.conversion_service = conversion_service or ConversionService()

    def configure(self, session: SessionConfig) -> None:
        self._session = session
        self._enabled_filters = {channel.index: set() for channel in session.channels}
        self._filter_parameters = {
            channel.index: FilterParameters.defaults_for_sample_rate(
                channel.sample_rate_hz
            )
            for channel in session.channels
        }

    def reset(self) -> None:
        if self._session is None:
            self._enabled_filters = {}
            self._filter_parameters = {}
            return
        self.configure(self._session)

    def _channel(self, channel_index: int) -> SignalChannelConfig:
        if self._session is None:
            raise RuntimeError("Processamento não configurado.")
        for channel in self._session.channels:
            if channel.index == channel_index:
                return channel
        raise ValueError(f"Canal {channel_index} não existe no processamento.")

    def set_filter_enabled(self, channel_index: int, filter_id: str, enabled: bool) -> None:
        self._channel(channel_index)
        if filter_id not in FILTER_DEFINITIONS:
            raise ValueError(f"Filtro desconhecido: {filter_id}")
        target_ids = expand_filter_ids((filter_id,))
        if not target_ids:
            raise ValueError(f"Filtro não executável: {filter_id}")
        if enabled:
            self._enabled_filters[channel_index].update(target_ids)
        else:
            self._enabled_filters[channel_index].difference_update(target_ids)

    def set_filter_parameter(
        self,
        channel_index: int,
        parameter_id: str,
        value: float,
    ) -> FilterParameters:
        channel = self._channel(channel_index)
        current = self._filter_parameters[channel_index]
        updated = current.with_value(parameter_id, value, channel.sample_rate_hz)
        self._filter_parameters[channel_index] = updated
        return updated

    def filter_parameters_for(self, channel_index: int) -> FilterParameters:
        self._channel(channel_index)
        return self._filter_parameters[channel_index]

    def filter_parameters_snapshot(self) -> Dict[int, dict[str, float | int]]:
        return {
            index: parameters.to_dict()
            for index, parameters in self._filter_parameters.items()
        }

    def enabled_filters_snapshot(self) -> Dict[int, List[str]]:
        """Retorna somente filtros reais; ``bandpass`` é expandido em HP + LP."""
        return {index: sorted(filters) for index, filters in self._enabled_filters.items()}

    def set_enabled_filters(self, filters_by_channel: Dict[int, List[str]]) -> None:
        """Restaura filtros e migra o identificador legado ``bandpass``."""
        if self._session is None:
            raise RuntimeError("Processamento não configurado.")
        restored: Dict[int, Set[str]] = {
            channel.index: set() for channel in self._session.channels
        }
        for channel_index, filter_ids in filters_by_channel.items():
            if channel_index not in restored:
                continue
            restored[channel_index].update(expand_filter_ids(filter_ids))
        self._enabled_filters = restored

    def active_filters_for(self, channel_index: int) -> List[str]:
        return sorted(self._enabled_filters.get(channel_index, set()))

    def process(
        self,
        snapshot: AcquisitionSnapshot,
        *,
        channel_indexes: set[int] | None = None,
        spectrum_modes: Dict[int, str] | None = None,
        display_modes: Dict[int, str] | None = None,
    ) -> ProcessedAcquisitionSnapshot:
        """Gera somente os canais e espectros solicitados pela tela."""
        processed_channels: Dict[int, ProcessedChannelSnapshot] = {}
        selected_indexes = (
            set(snapshot.channels) if channel_indexes is None else set(channel_indexes)
        )

        def empty_spectrum() -> SpectrumSnapshot:
            empty = np.array([], dtype=float)
            return SpectrumSnapshot(empty, empty)

        for index, channel_snapshot in snapshot.channels.items():
            if index not in selected_indexes:
                continue
            enabled_filters = self.active_filters_for(index)
            requested_display_mode = (
                None if display_modes is None else display_modes.get(index)
            )
            filters_to_apply = (
                [] if requested_display_mode == "base" else enabled_filters
            )
            conversion = self.conversion_service.convert(
                channel_snapshot.values,
                channel_snapshot.channel,
            )
            processed_values, filter_status = self._process_channel_values(
                conversion.values,
                channel_snapshot.channel,
                filters_to_apply,
                self._filter_parameters.get(index),
            )
            if requested_display_mode == "base" and enabled_filters:
                filter_status = [
                    "Filtros ativos preservados; cálculo suspenso no modo base."
                ]
            last_converted_value = (
                float(conversion.values[-1]) if conversion.values.size else None
            )
            last_processed_value = (
                float(processed_values[-1]) if processed_values.size else None
            )
            raw_spectrum = empty_spectrum()
            converted_spectrum = empty_spectrum()
            processed_spectrum = empty_spectrum()
            requested_mode = (
                None if spectrum_modes is None else spectrum_modes.get(index)
            )
            if spectrum_modes is None:
                raw_spectrum = calculate_single_sided_spectrum(
                    channel_snapshot.values,
                    channel_snapshot.channel.sample_rate_hz,
                )
                converted_spectrum = calculate_single_sided_spectrum(
                    conversion.values,
                    channel_snapshot.channel.sample_rate_hz,
                )
                processed_spectrum = calculate_single_sided_spectrum(
                    processed_values,
                    channel_snapshot.channel.sample_rate_hz,
                )
            elif requested_mode == "base":
                converted_spectrum = calculate_single_sided_spectrum(
                    conversion.values,
                    channel_snapshot.channel.sample_rate_hz,
                )
            elif requested_mode == "processed":
                processed_spectrum = calculate_single_sided_spectrum(
                    processed_values,
                    channel_snapshot.channel.sample_rate_hz,
                )
            processed_channels[index] = ProcessedChannelSnapshot(
                channel=channel_snapshot.channel,
                sample_count=channel_snapshot.sample_count,
                x_seconds=channel_snapshot.x_seconds,
                raw_values=channel_snapshot.values,
                converted_values=conversion.values,
                processed_values=processed_values,
                timestamps_us=channel_snapshot.timestamps_us,
                sequence_ids=channel_snapshot.sequence_ids,
                last_raw_value=channel_snapshot.last_value,
                last_converted_value=last_converted_value,
                last_processed_value=last_processed_value,
                last_timestamp_us=channel_snapshot.last_timestamp_us,
                conversion_enabled=conversion.enabled,
                conversion_profile_id=conversion.profile_id,
                conversion_status=list(conversion.status),
                conversion_input_unit=conversion.input_unit,
                conversion_output_unit=conversion.output_unit,
                conversion_out_of_input_range=conversion.out_of_input_range,
                conversion_out_of_output_range=conversion.out_of_output_range,
                active_filters=enabled_filters,
                filter_status=filter_status,
                metrics=calculate_metrics(processed_values),
                raw_spectrum=raw_spectrum,
                converted_spectrum=converted_spectrum,
                processed_spectrum=processed_spectrum,
            )
        return ProcessedAcquisitionSnapshot(
            configured=snapshot.configured,
            running=snapshot.running,
            communication=snapshot.communication,
            last_sequence_id=snapshot.last_sequence_id,
            last_timestamp_us=snapshot.last_timestamp_us,
            channels=processed_channels,
        )

    def _process_channel_values(
        self,
        values: np.ndarray,
        channel: SignalChannelConfig,
        active_filters: List[str],
        parameters: FilterParameters | None = None,
    ) -> tuple[np.ndarray, List[str]]:
        source = _as_float_array(values)
        if not active_filters:
            return source.copy(), ["Sem filtros ativos."]
        if source.size == 0:
            return source.copy(), ["Sem amostras para processar."]
        parameters = parameters or FilterParameters.defaults_for_sample_rate(
            channel.sample_rate_hz
        )
        return self.pipeline.apply(source, channel, active_filters, parameters)

