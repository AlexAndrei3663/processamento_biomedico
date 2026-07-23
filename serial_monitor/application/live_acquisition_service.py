from __future__ import annotations

from collections.abc import Sequence

from typing import Dict

from serial_monitor.application.communication_monitor import CommunicationMonitor
from serial_monitor.domain.models import AcquisitionSnapshot, SampleFrame, SessionConfig
from serial_monitor.processing.ring_buffer import RingBuffer


class LiveAcquisitionService:
    """Modelo de aquisição ao vivo com diagnóstico de integridade.

    O serviço recebe ``SampleFrame`` já parseado, valida continuidade sequencial e
    temporal e distribui apenas quadros aceitos para buffers circulares independentes.
    """

    def __init__(self) -> None:
        self._session: SessionConfig | None = None
        self._buffers: Dict[int, RingBuffer] = {}
        self._running = False
        self._communication = CommunicationMonitor()

    @property
    def is_configured(self) -> bool:
        return self._session is not None

    @property
    def is_running(self) -> bool:
        return self._running

    def configure(self, session: SessionConfig) -> None:
        self._session = session
        self._buffers = {
            channel.index: RingBuffer(channel=channel, capacity=session.window_size)
            for channel in session.channels
        }
        self._communication.reset()
        self._running = False

    def start(self) -> None:
        if self._session is None:
            raise RuntimeError("Aquisição não configurada.")

        # Cada abertura da serial representa um novo fluxo. O firmware pode
        # reiniciar sequência e timestamp ao reconectar; por isso a janela e as
        # referências temporais anteriores não devem ser misturadas ao novo
        # fluxo. Os contadores de diagnóstico acumulados são preservados.
        self.clear_buffers(reset_stream_baseline=True)
        self._running = True

    def stop(self) -> None:
        self._running = False

    def begin_stream(self) -> None:
        """Aceita o próximo frame como nova referência temporal e sequencial."""

        self._communication.begin_stream()

    def clear_buffers(self, *, reset_stream_baseline: bool = False) -> None:
        """Limpa a janela móvel de visualização.

        Quando ``reset_stream_baseline`` é verdadeiro, o próximo quadro passa
        a ser a nova referência válida de sequência e timestamp. Os contadores
        de perdas, duplicações e erros já acumulados não são apagados.
        """

        for buffer in self._buffers.values():
            buffer.clear()

        if reset_stream_baseline:
            self._communication.begin_stream()

    def reset(self) -> None:
        """Reinicia buffers e diagnóstico para uma nova aquisição lógica."""

        self.clear_buffers()
        self._communication.reset()

    def record_invalid_frame(self, count: int = 1) -> None:
        self._communication.record_invalid_frame(count)

    def record_checksum_error(self) -> None:
        self._communication.record_checksum_error()

    def _validated_channel_values(self, frame: SampleFrame) -> Dict[int, float]:
        """Valida a estrutura de um frame sem alterar o monitor de sequência."""
        if self._session is None:
            raise RuntimeError("Aquisição não configurada.")

        expected = self._session.channel_count
        received = len(frame.values_in_order)
        if received != expected:
            self._communication.record_invalid_frame()
            raise ValueError(
                f"Frame possui {received} valores, mas a sessão espera {expected}."
            )

        channel_values: Dict[int, float] = {}
        for channel in self._session.channels:
            value = frame.value_for_channel(channel.index)
            if value is None:
                self._communication.record_invalid_frame()
                raise ValueError(
                    f"Frame não contém valor para o canal {channel.index}."
                )
            channel_values[channel.index] = value
        return channel_values

    def ingest_frames(
        self,
        frames: Sequence[SampleFrame],
    ) -> tuple[SampleFrame, ...]:
        """Valida e insere um lote, retornando apenas os frames aceitos."""
        if self._session is None:
            raise RuntimeError("Aquisição não configurada.")
        if not frames:
            return ()

        validated = [self._validated_channel_values(frame) for frame in frames]

        accepted_frames: list[SampleFrame] = []
        timestamps_us: list[int] = []
        sequence_ids: list[int] = []
        values_by_channel: Dict[int, list[float]] = {
            channel.index: [] for channel in self._session.channels
        }

        for frame, channel_values in zip(frames, validated, strict=True):
            if not self._communication.register_frame(frame):
                continue
            accepted_frames.append(frame)
            timestamps_us.append(frame.timestamp_us)
            sequence_ids.append(frame.sequence_id)
            for channel_index, value in channel_values.items():
                values_by_channel[channel_index].append(value)

        if accepted_frames:
            for channel_index, values in values_by_channel.items():
                self._buffers[channel_index].append_batch(
                    values=values,
                    timestamps_us=timestamps_us,
                    sequence_ids=sequence_ids,
                )

        return tuple(accepted_frames)

    def ingest_frame(self, frame: SampleFrame) -> bool:
        """Mantém a API unitária usada por testes e integrações legadas."""
        return bool(self.ingest_frames((frame,)))

    def snapshot(self) -> AcquisitionSnapshot:
        return AcquisitionSnapshot(
            configured=self._session is not None,
            running=self._running,
            communication=self._communication.snapshot(),
            last_sequence_id=self._communication.last_sequence_id,
            last_timestamp_us=self._communication.last_timestamp_us,
            channels={index: buffer.snapshot() for index, buffer in self._buffers.items()},
        )
