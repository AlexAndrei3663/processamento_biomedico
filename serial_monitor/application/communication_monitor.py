from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from serial_monitor.domain.models import (
    CommunicationStats,
    SampleFrame,
    SequenceDiagnostics,
)

UINT32_MODULUS = 1 << 32
UINT32_MAX = UINT32_MODULUS - 1
UINT64_MAX = (1 << 64) - 1


class SequenceDisposition(str, Enum):
    FIRST = "first"
    IN_ORDER = "in_order"
    GAP = "gap"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"


class TimestampDisposition(str, Enum):
    FIRST = "first"
    IN_ORDER = "in_order"
    WRAP = "wrap"
    RESET = "reset"
    REGRESSION = "regression"


@dataclass(frozen=True, slots=True)
class SequenceObservation:
    disposition: SequenceDisposition
    missing_items: int = 0

    @property
    def is_acceptable(self) -> bool:
        return self.disposition in {
            SequenceDisposition.FIRST,
            SequenceDisposition.IN_ORDER,
            SequenceDisposition.GAP,
        }


@dataclass(frozen=True, slots=True)
class TimestampObservation:
    disposition: TimestampDisposition
    normalized_timestamp_us: int | None

    @property
    def is_acceptable(self) -> bool:
        return self.disposition is not TimestampDisposition.REGRESSION


@dataclass(slots=True)
class _MutableSequenceDiagnostics:
    gap_events: int = 0
    missing_items: int = 0
    duplicate_items: int = 0
    out_of_order_items: int = 0

    def snapshot(self) -> SequenceDiagnostics:
        return SequenceDiagnostics(
            gap_events=self.gap_events,
            missing_items=self.missing_items,
            duplicate_items=self.duplicate_items,
            out_of_order_items=self.out_of_order_items,
        )


class _SequenceTracker:
    """Classifica contadores uint32, incluindo o wrap natural em 2**32."""

    def __init__(self) -> None:
        self.last_value: int | None = None
        self.diagnostics = _MutableSequenceDiagnostics()

    def reset(self) -> None:
        self.last_value = None
        self.diagnostics = _MutableSequenceDiagnostics()

    def reset_baseline(self) -> None:
        """Esquece apenas a última sequência aceita.

        Os contadores de diagnóstico são preservados. Isso permite iniciar uma
        nova conexão serial considerando o primeiro quadro recebido como uma
        nova referência, mesmo que o firmware tenha reiniciado a sequência.
        """

        self.last_value = None

    def classify(self, value: int) -> SequenceObservation:
        if not 0 <= value <= UINT32_MAX:
            raise ValueError(f"Contador fora da faixa uint32: {value}.")
        if self.last_value is None:
            return SequenceObservation(SequenceDisposition.FIRST)

        forward_distance = (value - self.last_value) % UINT32_MODULUS
        if forward_distance == 0:
            return SequenceObservation(SequenceDisposition.DUPLICATE)
        if forward_distance < UINT32_MODULUS // 2:
            if forward_distance == 1:
                return SequenceObservation(SequenceDisposition.IN_ORDER)
            return SequenceObservation(
                SequenceDisposition.GAP,
                missing_items=forward_distance - 1,
            )
        return SequenceObservation(SequenceDisposition.OUT_OF_ORDER)

    def commit_accepted(self, value: int, observation: SequenceObservation) -> None:
        if not observation.is_acceptable:
            raise ValueError("Somente observações aceitáveis podem avançar o contador.")
        if observation.disposition is SequenceDisposition.GAP:
            self.diagnostics.gap_events += 1
            self.diagnostics.missing_items += observation.missing_items
        self.last_value = value

    def record_rejected(self, observation: SequenceObservation) -> None:
        if observation.disposition is SequenceDisposition.DUPLICATE:
            self.diagnostics.duplicate_items += 1
        elif observation.disposition is SequenceDisposition.OUT_OF_ORDER:
            self.diagnostics.out_of_order_items += 1


class _TimestampNormalizer:
    def __init__(self) -> None:
        self.last_raw_timestamp_us: int | None = None
        self.last_normalized_timestamp_us: int | None = None
        self.last_delta_us = 1
        self.epoch_offset_us = 0

    def reset(self) -> None:
        self.last_raw_timestamp_us = None
        self.last_normalized_timestamp_us = None
        self.last_delta_us = 1
        self.epoch_offset_us = 0

    def is_probable_device_reset(
        self,
        *,
        raw_timestamp_us: int,
        sequence_id: int,
        last_sequence_id: int | None,
        sequence_observation: SequenceObservation,
    ) -> bool:
        last_raw = self.last_raw_timestamp_us
        if (
            last_raw is None
            or last_sequence_id is None
            or sequence_observation.disposition is not SequenceDisposition.OUT_OF_ORDER
            or raw_timestamp_us >= last_raw
            or sequence_id >= last_sequence_id
        ):
            return False
        timestamp_drop = last_raw - raw_timestamp_us
        sequence_drop = last_sequence_id - sequence_id
        return (
            timestamp_drop >= max(1_000_000, last_raw // 2)
            and sequence_drop >= max(100, last_sequence_id // 2)
        )

    def observe(
        self,
        raw_timestamp_us: int,
        *,
        device_reset: bool = False,
    ) -> TimestampObservation:
        if not 0 <= raw_timestamp_us <= UINT64_MAX:
            raise ValueError("Timestamp fora da faixa uint64.")

        last_raw = self.last_raw_timestamp_us
        last_normalized = self.last_normalized_timestamp_us
        if last_raw is None or last_normalized is None:
            return self._commit(
                raw_timestamp_us,
                raw_timestamp_us,
                TimestampDisposition.FIRST,
            )

        if device_reset:
            normalized = last_normalized + max(1, self.last_delta_us)
            self.epoch_offset_us = normalized - raw_timestamp_us
            return self._commit(
                raw_timestamp_us,
                normalized,
                TimestampDisposition.RESET,
            )

        if raw_timestamp_us > UINT32_MAX or last_raw > UINT32_MAX:
            if raw_timestamp_us <= last_normalized:
                return TimestampObservation(TimestampDisposition.REGRESSION, None)
            return self._commit(
                raw_timestamp_us,
                raw_timestamp_us,
                TimestampDisposition.IN_ORDER,
            )

        if raw_timestamp_us < last_raw:
            forward_distance = (raw_timestamp_us - last_raw) % UINT32_MODULUS
            if forward_distance >= UINT32_MODULUS // 2:
                return TimestampObservation(TimestampDisposition.REGRESSION, None)
            self.epoch_offset_us += UINT32_MODULUS
            disposition = TimestampDisposition.WRAP
        elif raw_timestamp_us == last_raw:
            return TimestampObservation(TimestampDisposition.REGRESSION, None)
        else:
            disposition = TimestampDisposition.IN_ORDER

        normalized = self.epoch_offset_us + raw_timestamp_us
        if normalized <= last_normalized:
            return TimestampObservation(TimestampDisposition.REGRESSION, None)
        return self._commit(raw_timestamp_us, normalized, disposition)

    def _commit(
        self,
        raw_timestamp_us: int,
        normalized_timestamp_us: int,
        disposition: TimestampDisposition,
    ) -> TimestampObservation:
        if self.last_normalized_timestamp_us is not None:
            self.last_delta_us = max(
                1,
                normalized_timestamp_us - self.last_normalized_timestamp_us,
            )
        self.last_raw_timestamp_us = raw_timestamp_us
        self.last_normalized_timestamp_us = normalized_timestamp_us
        return TimestampObservation(disposition, normalized_timestamp_us)


def sequence_forward_distance(origin: int, current: int) -> int:
    """Retorna a distância modular uint32 entre duas sequências."""

    if not 0 <= origin <= UINT32_MAX or not 0 <= current <= UINT32_MAX:
        raise ValueError("Sequências devem estar na faixa uint32.")
    return (current - origin) % UINT32_MODULUS


def estimate_timestamp_us(
    *,
    sequence_id: int,
    origin_sequence_id: int,
    origin_timestamp_us: int,
    sample_rate_hz: float,
) -> int:
    """Estima o tempo ideal de um ciclo a partir da sequência e da taxa nominal.

    A estimativa representa a grade temporal ideal. Ela não mede jitter, pausas,
    deriva do clock ou atrasos reais do firmware e, portanto, não substitui o timestamp
    gerado no STM32 quando essas grandezas precisam ser validadas.
    """

    if sample_rate_hz <= 0:
        raise ValueError("A taxa de amostragem deve ser maior que zero.")
    if not 0 <= origin_timestamp_us <= UINT64_MAX:
        raise ValueError("origin_timestamp_us fora da faixa uint64.")

    elapsed_cycles = sequence_forward_distance(origin_sequence_id, sequence_id)
    elapsed_us = round(elapsed_cycles * 1_000_000.0 / sample_rate_hz)
    estimated = origin_timestamp_us + elapsed_us
    if estimated > UINT64_MAX:
        raise OverflowError("Timestamp estimado excede a faixa uint64.")
    return estimated


class CommunicationMonitor:
    """Valida a continuidade temporal e sequencial dos quadros aceitos."""

    def __init__(self) -> None:
        self._sequence_tracker = _SequenceTracker()
        self._timestamp_normalizer = _TimestampNormalizer()
        self._valid_frames = 0
        self._invalid_frames = 0
        self._checksum_errors = 0
        self._timestamp_regressions = 0
        self._timestamp_wraps = 0
        self._device_resets = 0

    @property
    def last_sequence_id(self) -> int | None:
        return self._sequence_tracker.last_value

    @property
    def last_timestamp_us(self) -> int | None:
        return self._timestamp_normalizer.last_normalized_timestamp_us

    def reset(self) -> None:
        self._sequence_tracker.reset()
        self._valid_frames = 0
        self._invalid_frames = 0
        self._checksum_errors = 0
        self._timestamp_regressions = 0
        self._timestamp_wraps = 0
        self._device_resets = 0
        self._timestamp_normalizer.reset()

    def begin_stream(self) -> None:
        """Inicia uma nova continuidade serial sem apagar os diagnósticos.

        O primeiro ``sequence_id`` e o primeiro ``timestamp_us`` recebidos após
        a chamada passam a ser referências válidas. Essa operação é usada em
        reconexões e ao limpar a visualização, evitando que um contador
        reiniciado pelo microcontrolador bloqueie os novos quadros.
        """

        self._sequence_tracker.reset_baseline()
        self._timestamp_normalizer.reset()

    def record_invalid_frame(self, count: int = 1) -> None:
        count = int(count)
        if count <= 0:
            return
        self._invalid_frames += count

    def record_checksum_error(self) -> None:
        self._checksum_errors += 1
        self._invalid_frames += 1

    def register_frame(self, frame: SampleFrame) -> bool:
        """Registra um quadro e informa se ele deve entrar nos buffers.

        Quadros duplicados, fora de ordem ou com timestamp não crescente são
        contabilizados e rejeitados. Gaps são aceitos e a quantidade ausente é estimada.
        """

        sequence_observation = self._sequence_tracker.classify(frame.sequence_id)
        device_reset = self._timestamp_normalizer.is_probable_device_reset(
            raw_timestamp_us=frame.timestamp_us,
            sequence_id=frame.sequence_id,
            last_sequence_id=self._sequence_tracker.last_value,
            sequence_observation=sequence_observation,
        )
        if device_reset:
            self._sequence_tracker.reset_baseline()
            sequence_observation = self._sequence_tracker.classify(frame.sequence_id)
        elif not sequence_observation.is_acceptable:
            self._sequence_tracker.record_rejected(sequence_observation)
            return False

        timestamp_observation = self._timestamp_normalizer.observe(
            frame.timestamp_us,
            device_reset=device_reset,
        )
        if not timestamp_observation.is_acceptable:
            self._timestamp_regressions += 1
            return False

        self._sequence_tracker.commit_accepted(frame.sequence_id, sequence_observation)
        if timestamp_observation.disposition is TimestampDisposition.WRAP:
            self._timestamp_wraps += 1
        elif timestamp_observation.disposition is TimestampDisposition.RESET:
            self._device_resets += 1
        frame.timestamp_us = int(timestamp_observation.normalized_timestamp_us)
        self._valid_frames += 1
        return True

    def snapshot(self) -> CommunicationStats:
        return CommunicationStats(
            valid_frames=self._valid_frames,
            invalid_frames=self._invalid_frames,
            checksum_errors=self._checksum_errors,
            timestamp_regressions=self._timestamp_regressions,
            timestamp_wraps=self._timestamp_wraps,
            device_resets=self._device_resets,
            sequence=self._sequence_tracker.diagnostics.snapshot(),
        )
