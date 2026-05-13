from __future__ import annotations

from typing import Iterable, List

from serial_monitor.app.signals_catalog import SIGNAL_PRESETS
from serial_monitor.domain.enums import ProtocolMode, SignalType
from serial_monitor.domain.models import SessionConfig, SignalChannelConfig


class SessionService:
    def parse_signal_order(self, text: str) -> List[SignalType]:
        items = [item.strip() for item in text.split(",") if item.strip()]
        if not items:
            raise ValueError("Informe ao menos um sinal na ordem desejada.")
        return [SignalType.from_text(item) for item in items]

    def build_channels(
        self,
        signal_order: Iterable[SignalType],
        base_sample_rate_hz: int,
    ) -> List[SignalChannelConfig]:
        channels: List[SignalChannelConfig] = []
        for index, signal_type in enumerate(signal_order):
            preset = SIGNAL_PRESETS[signal_type]
            channels.append(
                SignalChannelConfig(
                    index=index,
                    signal_type=signal_type,
                    display_name=preset.display_name,
                    unit=preset.unit,
                    sample_rate_hz=float(base_sample_rate_hz),
                    default_filters=list(preset.default_filters),
                )
            )
        return channels

    def build_session(
        self,
        port: str,
        baudrate: int,
        base_sample_rate_hz: int,
        window_size: int,
        signal_order_text: str,
    ) -> SessionConfig:
        signal_order = self.parse_signal_order(signal_order_text)
        channels = self.build_channels(signal_order, base_sample_rate_hz)
        return SessionConfig(
            port=port,
            baudrate=baudrate,
            base_sample_rate_hz=base_sample_rate_hz,
            window_size=window_size,
            protocol_mode=ProtocolMode.FRAME_CSV,
            channels=channels,
        )
