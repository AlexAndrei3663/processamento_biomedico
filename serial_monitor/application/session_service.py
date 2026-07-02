from __future__ import annotations

from typing import Iterable, List

from serial_monitor.app.signals_catalog import SIGNAL_PRESETS
from serial_monitor.domain.enums import ProtocolMode, SignalType
from serial_monitor.domain.models import (
    ConversionConfig,
    SessionConfig,
    SignalChannelConfig,
)
from serial_monitor.infrastructure.storage.conversion_profile_repository import (
    ConversionProfileRepository,
)


class SessionService:
    def __init__(
        self,
        conversion_profiles: ConversionProfileRepository | None = None,
    ) -> None:
        self.conversion_profiles = conversion_profiles

    def parse_signal_order(self, text: str) -> List[SignalType]:
        items = [item.strip() for item in text.split(",") if item.strip()]
        if not items:
            raise ValueError("Informe ao menos um sinal na ordem desejada.")
        return [SignalType.from_text(item) for item in items]

    def build_channels(
        self,
        signal_order: Iterable[SignalType],
        base_sample_rate_hz: int,
        channel_conversions: list[dict] | None = None,
    ) -> List[SignalChannelConfig]:
        conversion_by_index = {
            int(item.get("channel_index", index)): dict(item)
            for index, item in enumerate(channel_conversions or [])
            if isinstance(item, dict)
        }

        channels: List[SignalChannelConfig] = []
        for index, signal_type in enumerate(signal_order):
            preset = SIGNAL_PRESETS[signal_type]
            source = conversion_by_index.get(index, {})
            enabled = bool(source.get("enabled", False))
            profile_id_raw = source.get("profile_id")
            profile_id = str(profile_id_raw).strip() if profile_id_raw else None
            conversion = ConversionConfig(enabled=enabled, profile_id=profile_id)
            profile = None
            unit = preset.raw_unit

            if enabled:
                if self.conversion_profiles is None:
                    raise ValueError(
                        f"Canal ch{index}: repositório de perfis de conversão indisponível."
                    )
                assert profile_id is not None
                profile = self.conversion_profiles.get(profile_id)
                if profile.signal_type is not None and profile.signal_type != signal_type:
                    raise ValueError(
                        f"Canal ch{index}: perfil '{profile_id}' incompatível com "
                        f"o sinal {signal_type.value}."
                    )
                if profile.input_unit != preset.raw_unit:
                    raise ValueError(
                        f"Canal ch{index}: perfil '{profile_id}' espera '{profile.input_unit}', "
                        f"mas o canal fornece '{preset.raw_unit}'."
                    )
                unit = profile.output_unit

            channels.append(
                SignalChannelConfig(
                    index=index,
                    signal_type=signal_type,
                    display_name=preset.display_name,
                    unit=unit,
                    raw_unit=preset.raw_unit,
                    sample_rate_hz=float(base_sample_rate_hz),
                    conversion=conversion,
                    conversion_profile=profile,
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
        channel_conversions: list[dict] | None = None,
    ) -> SessionConfig:
        signal_order = self.parse_signal_order(signal_order_text)
        channels = self.build_channels(
            signal_order,
            base_sample_rate_hz,
            channel_conversions=channel_conversions,
        )
        return SessionConfig(
            port=port,
            baudrate=baudrate,
            base_sample_rate_hz=base_sample_rate_hz,
            window_size=window_size,
            protocol_mode=ProtocolMode.FRAME_CSV,
            channels=channels,
        )
