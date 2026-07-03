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
        self._valid_frames = 0
        self._invalid_frames = 0
        self._checksum_errors = 0
        self._timestamp_regressions = 0
        self._last_timestamp_us: int | None = None

    @property
    def last_sequence_id(self) -> int | None:
        return self._sequence_tracker.last_value

    @property
    def last_timestamp_us(self) -> int | None:
        return self._last_timestamp_us

    def reset(self) -> None:
        self._sequence_tracker.reset()
        self._valid_frames = 0
        self._invalid_frames = 0
        self._checksum_errors = 0
        self._timestamp_regressions = 0
        self._last_timestamp_us = None

    def begin_stream(self) -> None:
        """Inicia uma nova continuidade serial sem apagar os diagnósticos.

        O primeiro ``sequence_id`` e o primeiro ``timestamp_us`` recebidos após
        a chamada passam a ser referências válidas. Essa operação é usada em
        reconexões e ao limpar a visualização, evitando que um contador
        reiniciado pelo microcontrolador bloqueie os novos quadros.
        """

        self._sequence_tracker.reset_baseline()
        self._last_timestamp_us = None

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

        observation = self._sequence_tracker.classify(frame.sequence_id)
        if not observation.is_acceptable:
            self._sequence_tracker.record_rejected(observation)
            return False

        if self._last_timestamp_us is not None and frame.timestamp_us <= self._last_timestamp_us:
            self._timestamp_regressions += 1
            return False

        self._sequence_tracker.commit_accepted(frame.sequence_id, observation)
        self._last_timestamp_us = frame.timestamp_us
        self._valid_frames += 1
        return True

    def snapshot(self) -> CommunicationStats:
        return CommunicationStats(
            valid_frames=self._valid_frames,
            invalid_frames=self._invalid_frames,
            checksum_errors=self._checksum_errors,
            timestamp_regressions=self._timestamp_regressions,
            sequence=self._sequence_tracker.diagnostics.snapshot(),
        )
