from __future__ import annotations

import math
from typing import List

from serial_monitor.application.communication_monitor import UINT32_MAX, UINT64_MAX
from serial_monitor.domain.models import ParsedFrame, SampleFrame, SessionConfig


class FrameProtocolError(ValueError):
    """Erro de sintaxe ou domínio no protocolo serial textual."""


class FrameCsvParser:
    """Parser do protocolo textual multicanal da Etapa 12.

    Formato oficial::

        FRAME,<packet_sequence>,<scan_sequence>,<timestamp_us>,<v0>,...,<vN>

    Contrato temporal:
    - ``packet_sequence`` é uint32 e identifica o pacote transmitido;
    - ``scan_sequence`` é uint32 e identifica o ciclo de varredura multicanal;
    - ambos reiniciam no boot do firmware e avançam com wrap em ``2**32``;
    - ``timestamp_us`` é uint64, monotônico, em microssegundos desde o boot;
    - o timestamp corresponde à primeira conversão do ciclo;
    - os valores seguem a ordem dos canais configurada na sessão.

    Nesta versão textual há um ciclo por pacote. Os dois contadores permanecem separados
    para permitir que o protocolo evolua para lotes e canais assíncronos.
    """

    header = "FRAME"

    @staticmethod
    def _parse_unsigned(token: str, *, name: str, maximum: int) -> int:
        try:
            value = int(token)
        except ValueError as exc:
            raise FrameProtocolError(f"{name} deve ser um número inteiro sem sinal.") from exc
        if not 0 <= value <= maximum:
            raise FrameProtocolError(f"{name} fora da faixa permitida: 0 a {maximum}.")
        return value

    def parse_line(self, line: str, session: SessionConfig) -> ParsedFrame:
        clean_line = line.strip()
        if not clean_line:
            raise FrameProtocolError("Linha vazia recebida.")

        tokens = [token.strip() for token in clean_line.split(",")]
        expected_tokens = 4 + session.channel_count
        if len(tokens) != expected_tokens:
            raise FrameProtocolError(
                f"Quantidade de campos inválida. Esperado {expected_tokens}, recebido {len(tokens)}."
            )
        if tokens[0].upper() != self.header:
            raise FrameProtocolError("Cabeçalho FRAME ausente.")

        packet_sequence = self._parse_unsigned(
            tokens[1],
            name="packet_sequence",
            maximum=UINT32_MAX,
        )
        scan_sequence = self._parse_unsigned(
            tokens[2],
            name="scan_sequence",
            maximum=UINT32_MAX,
        )
        timestamp_us = self._parse_unsigned(
            tokens[3],
            name="timestamp_us",
            maximum=UINT64_MAX,
        )

        try:
            values_in_order = [float(token) for token in tokens[4:]]
        except ValueError as exc:
            raise FrameProtocolError("Valores de canal inválidos no frame.") from exc
        if any(not math.isfinite(value) for value in values_in_order):
            raise FrameProtocolError("Valores NaN ou infinitos não são aceitos no frame.")

        values_by_channel_index = {
            channel.index: value
            for channel, value in zip(session.channels, values_in_order, strict=True)
        }
        return ParsedFrame(
            frame=SampleFrame(
                packet_sequence=packet_sequence,
                scan_sequence=scan_sequence,
                timestamp_us=timestamp_us,
                values_by_channel_index=values_by_channel_index,
                values_in_order=values_in_order,
            )
        )


def format_frame_csv(
    packet_sequence: int,
    scan_sequence: int,
    timestamp_us: int,
    values: List[float],
) -> str:
    if not 0 <= packet_sequence <= UINT32_MAX:
        raise ValueError("packet_sequence fora da faixa uint32.")
    if not 0 <= scan_sequence <= UINT32_MAX:
        raise ValueError("scan_sequence fora da faixa uint32.")
    if not 0 <= timestamp_us <= UINT64_MAX:
        raise ValueError("timestamp_us fora da faixa uint64.")
    if any(not math.isfinite(float(value)) for value in values):
        raise ValueError("Os valores do payload devem ser finitos.")

    payload = ",".join(str(value) for value in values)
    return f"FRAME,{packet_sequence},{scan_sequence},{timestamp_us},{payload}"
