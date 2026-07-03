from __future__ import annotations

from typing import Iterable, List

from serial_monitor.app.signals_catalog import SIGNAL_PRESETS
from serial_monitor.domain.enums import ConversionModel, ProtocolMode, SignalType
from serial_monitor.domain.models import (
    AdcConfig,
    ConversionConfig,
    ConversionProfile,
    SessionConfig,
    SignalChannelConfig,
)
from serial_monitor.infrastructure.storage.conversion_profile_repository import (
    ConversionProfileRepository,
)


class SessionService:
    """Monta sessões válidas a partir da configuração da interface."""

    ADS1256_PROFILE_ID = "ads1256_differential_voltage_v1"

    def __init__(
        self,
        conversion_profiles: ConversionProfileRepository | None = None,
    ) -> None:
        # Mantido para abertura e compatibilidade com perfis antigos. Novas
        # sessões usam diretamente a conversão nominal do ADS1256.
        self.conversion_profiles = conversion_profiles

    def parse_signal_order(self, text: str) -> List[SignalType]:
        items = [item.strip() for item in text.split(",") if item.strip()]
        if not items:
            raise ValueError("Informe ao menos um sinal na ordem desejada.")
        return [SignalType.from_text(item) for item in items]

    @classmethod
    def _ads1256_profile(cls, adc: AdcConfig) -> ConversionProfile:
        full_scale = adc.full_scale_voltage_v
        profile = ConversionProfile(
            profile_id=cls.ADS1256_PROFILE_ID,
            version=1,
            signal_type=None,
            model=ConversionModel.ADS1256_DIFFERENTIAL,
            input_unit="count",
            output_unit="V",
            parameters={
                "reference_voltage_v": adc.reference_voltage_v,
                "gain": adc.gain,
                "input_mode": adc.input_mode,
            },
            description=(
                "Conversão nominal da contagem assinada de 24 bits para a tensão "
                "diferencial AINP-AINN na entrada do ADS1256."
            ),
            valid_input_range=(-8_388_608.0, 8_388_607.0),
            valid_output_range=(-full_scale, full_scale),
            origin="Configuração da sessão",
            reference_equipment="ADS1256",
        )
        profile.validate()
        return profile

    def build_channels(
        self,
        signal_order: Iterable[SignalType],
        base_sample_rate_hz: int,
        channel_conversions: list[dict] | None = None,
        *,
        adc: AdcConfig | None = None,
    ) -> List[SignalChannelConfig]:
        adc = adc or AdcConfig()
        conversion_by_index = {
            int(item.get("channel_index", index)): dict(item)
            for index, item in enumerate(channel_conversions or [])
            if isinstance(item, dict)
        }

        channels: List[SignalChannelConfig] = []
        for index, signal_type in enumerate(signal_order):
            preset = SIGNAL_PRESETS[signal_type]
            source = conversion_by_index.get(index, {})

            # Formato atual: mode=raw|voltage. Para presets antigos, enabled=True
            # é interpretado como solicitação de tensão.
            mode = str(source.get("mode", "")).strip().lower()
            if mode not in {"raw", "voltage"}:
                mode = "voltage" if bool(source.get("enabled", False)) else "raw"

            conversion_enabled = mode == "voltage"
            conversion = ConversionConfig(
                enabled=conversion_enabled,
                profile_id=self.ADS1256_PROFILE_ID if conversion_enabled else None,
            )
            profile = self._ads1256_profile(adc) if conversion_enabled else None
            unit = "V" if conversion_enabled else preset.raw_unit

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
        *,
        adc_reference_voltage_v: float = 2.5,
        adc_gain: int = 1,
    ) -> SessionConfig:
        signal_order = self.parse_signal_order(signal_order_text)
        adc = AdcConfig(
            model="ADS1256",
            input_mode="differential",
            reference_voltage_v=float(adc_reference_voltage_v),
            gain=int(adc_gain),
        )
        channels = self.build_channels(
            signal_order,
            base_sample_rate_hz,
            channel_conversions=channel_conversions,
            adc=adc,
        )
        return SessionConfig(
            port=port,
            baudrate=baudrate,
            base_sample_rate_hz=base_sample_rate_hz,
            window_size=window_size,
            protocol_mode=ProtocolMode.FRAME_CSV,
            channels=channels,
            adc=adc,
        )
