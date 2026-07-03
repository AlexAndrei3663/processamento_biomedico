from __future__ import annotations

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

    def ingest_frame(self, frame: SampleFrame) -> bool:
        """Insere um quadro e retorna ``True`` somente quando ele foi aceito."""

        if self._session is None:
            raise RuntimeError("Aquisição não configurada.")

        expected = self._session.channel_count
        received = len(frame.values_in_order)
        if received != expected:
            self._communication.record_invalid_frame()
            raise ValueError(f"Frame possui {received} valores, mas a sessão espera {expected}.")

        channel_values: Dict[int, float] = {}
        for channel in self._session.channels:
            value = frame.value_for_channel(channel.index)
            if value is None:
                self._communication.record_invalid_frame()
                raise ValueError(f"Frame não contém valor para o canal {channel.index}.")
            channel_values[channel.index] = value

        if not self._communication.register_frame(frame):
            return False

        for channel_index, value in channel_values.items():
            self._buffers[channel_index].append(
                value=value,
                timestamp_us=frame.timestamp_us,
                sequence_id=frame.sequence_id,
            )
        return True

    def snapshot(self) -> AcquisitionSnapshot:
        return AcquisitionSnapshot(
            configured=self._session is not None,
            running=self._running,
            communication=self._communication.snapshot(),
            last_sequence_id=self._communication.last_sequence_id,
            last_timestamp_us=self._communication.last_timestamp_us,
            channels={index: buffer.snapshot() for index, buffer in self._buffers.items()},
        )
