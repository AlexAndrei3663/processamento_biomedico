from __future__ import annotations

from dataclasses import dataclass
from typing import List

from serial_monitor.domain.models import SampleFrame, SessionConfig


class FrameProtocolError(ValueError):
    """Erro de protocolo serial."""


@dataclass(frozen=True, slots=True)
class ParsedFrame:
    frame: SampleFrame


class FrameCsvParser:
    """Parser do protocolo textual oficial.

    Formato aceito:
        FRAME,<seq>,<timestamp_ms>,<v1>,<v2>,...,<vn>
    onde n é exatamente o número de canais configurados na sessão.
    """

    header = "FRAME"

    def parse_line(self, line: str, session: SessionConfig) -> ParsedFrame:
        clean_line = line.strip()
        if not clean_line:
            raise FrameProtocolError("Linha vazia recebida.")

        tokens = [token.strip() for token in clean_line.split(",")]
        minimum_tokens = 3 + session.channel_count
        if len(tokens) != minimum_tokens:
            raise FrameProtocolError(
                f"Quantidade de campos inválida. Esperado {minimum_tokens}, recebido {len(tokens)}."
            )
        if tokens[0].upper() != self.header:
            raise FrameProtocolError("Cabeçalho FRAME ausente.")

        try:
            sequence_id = int(tokens[1])
            timestamp_ms = int(tokens[2])
            values_in_order = [float(token) for token in tokens[3:]]
        except ValueError as exc:
            raise FrameProtocolError("Campos numéricos inválidos no frame.") from exc

        values_by_signal = {
            channel.signal_type: value
            for channel, value in zip(session.channels, values_in_order, strict=True)
        }
        frame = SampleFrame(
            sequence_id=sequence_id,
            timestamp_ms=timestamp_ms,
            values_by_signal=values_by_signal,
            values_in_order=values_in_order,
        )
        return ParsedFrame(frame=frame)


def format_frame_csv(sequence_id: int, timestamp_ms: int, values: List[float]) -> str:
    payload = ",".join(str(value) for value in values)
    return f"FRAME,{sequence_id},{timestamp_ms},{payload}"
