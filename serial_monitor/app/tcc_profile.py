from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.enums import SignalType
from serial_monitor.domain.models import SessionConfig, SessionPreset


DEFAULT_PROFILE_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "tcc_profile.json"
)


@dataclass(frozen=True, slots=True)
class TccChannelProfile:
    index: int
    signal_type: SignalType
    display_name: str
    physical_input: str
    base_mode: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TccChannelProfile":
        mode = str(payload.get("base_mode", "raw")).strip().lower()
        if mode not in {"raw", "voltage"}:
            raise ValueError(
                f"Modo base inválido no canal {payload.get('index')}: {mode}."
            )
        return cls(
            index=int(payload["index"]),
            signal_type=SignalType.from_text(str(payload["signal_type"])),
            display_name=str(payload["display_name"]).strip(),
            physical_input=str(payload.get("physical_input", "")).strip(),
            base_mode=mode,
        )

    def to_conversion_dict(self) -> dict[str, object]:
        return {"channel_index": self.index, "mode": self.base_mode}


@dataclass(frozen=True, slots=True)
class TccOperationalProfile:
    profile_version: int
    name: str
    locked: bool
    baudrate: int
    base_sample_rate_hz: int
    window_seconds: int
    adc_reference_voltage_v: float
    adc_gain: int
    protocol: dict[str, object]
    firmware: dict[str, object]
    channels: tuple[TccChannelProfile, ...]

    @property
    def window_size(self) -> int:
        return self.base_sample_rate_hz * self.window_seconds

    @property
    def signal_order_text(self) -> str:
        return ",".join(channel.signal_type.value for channel in self.channels)

    @property
    def channel_conversions(self) -> list[dict[str, object]]:
        return [channel.to_conversion_dict() for channel in self.channels]

    @property
    def expected_channel_count(self) -> int:
        return len(self.channels)

    def validate(self) -> None:
        if self.profile_version <= 0:
            raise ValueError("A versão do perfil deve ser positiva.")
        if not self.name:
            raise ValueError("O perfil operacional deve possuir nome.")
        if self.baudrate <= 0:
            raise ValueError("O baudrate do perfil deve ser positivo.")
        if self.base_sample_rate_hz <= 0:
            raise ValueError("A taxa de amostragem deve ser positiva.")
        if self.window_seconds <= 0:
            raise ValueError("A janela temporal deve ser positiva.")
        if self.adc_reference_voltage_v <= 0:
            raise ValueError("A tensão de referência deve ser positiva.")
        if self.adc_gain not in (1, 2, 4, 8, 16, 32, 64):
            raise ValueError("Ganho inválido para o ADS1256.")
        if len(self.channels) != 4:
            raise ValueError(
                "O perfil do TCC exige exatamente quatro pares diferenciais."
            )
        indexes = [channel.index for channel in self.channels]
        if indexes != [0, 1, 2, 3]:
            raise ValueError("Os canais devem usar índices sequenciais de 0 a 3.")
        names = [channel.display_name for channel in self.channels]
        if any(not name for name in names):
            raise ValueError("Todos os canais devem possuir nome de exibição.")
        if len(set(names)) != len(names):
            raise ValueError("Os nomes dos canais devem ser únicos.")
        expected = int(
            self.protocol.get("expected_channel_count", len(self.channels))
        )
        if expected != len(self.channels):
            raise ValueError(
                "A quantidade de canais do protocolo diverge do perfil."
            )

    def to_preset(self, *, port: str) -> SessionPreset:
        now = datetime.now().isoformat(timespec="seconds")
        return SessionPreset(
            name=self.name,
            created_at=now,
            updated_at=now,
            port=str(port).strip(),
            baudrate=self.baudrate,
            base_sample_rate_hz=self.base_sample_rate_hz,
            window_size=self.window_size,
            signal_order_text=self.signal_order_text,
            channel_conversions=self.channel_conversions,
            adc_reference_voltage_v=self.adc_reference_voltage_v,
            adc_gain=self.adc_gain,
            path=Path(),
        )

    def build_session(
        self,
        session_service: SessionService,
        *,
        port: str,
    ) -> SessionConfig:
        self.validate()
        selected_port = str(port).strip()
        if not selected_port:
            raise ValueError(
                "Nenhuma porta serial foi selecionada. "
                "Conecte a BlackPill e atualize a lista de portas."
            )
        session = session_service.build_session(
            port=selected_port,
            baudrate=self.baudrate,
            base_sample_rate_hz=self.base_sample_rate_hz,
            window_size=self.window_size,
            signal_order_text=self.signal_order_text,
            channel_conversions=self.channel_conversions,
            adc_reference_voltage_v=self.adc_reference_voltage_v,
            adc_gain=self.adc_gain,
        )
        for channel, channel_profile in zip(
            session.channels,
            self.channels,
            strict=True,
        ):
            channel.display_name = channel_profile.display_name
        return session

    def source_metadata(self) -> dict[str, object]:
        """Contrato preparado para integração futura com o firmware."""
        return {
            "operational_profile": self.name,
            "operational_profile_version": self.profile_version,
            "expected_channel_count": self.expected_channel_count,
            "channel_map": [
                {
                    "index": channel.index,
                    "signal_type": channel.signal_type.value,
                    "display_name": channel.display_name,
                    "physical_input": channel.physical_input,
                }
                for channel in self.channels
            ],
            "protocol": dict(self.protocol),
            "firmware": dict(self.firmware),
        }


def _load_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Perfil operacional não encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"JSON inválido no perfil operacional {path}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError("O perfil operacional deve ser um objeto JSON.")
    return payload


def load_tcc_profile(
    path: str | Path | None = None,
) -> TccOperationalProfile:
    selected = Path(
        path
        or os.environ.get("BIOMED_TCC_PROFILE_PATH", "")
        or DEFAULT_PROFILE_PATH
    )
    payload = _load_payload(selected)
    adc = payload.get("adc", {})
    protocol = payload.get("protocol", {})
    firmware = payload.get("firmware", {})
    channels_payload = payload.get("channels", [])

    if not isinstance(adc, dict):
        raise ValueError("A seção 'adc' do perfil deve ser um objeto.")
    if not isinstance(protocol, dict):
        raise ValueError("A seção 'protocol' deve ser um objeto.")
    if not isinstance(firmware, dict):
        raise ValueError("A seção 'firmware' deve ser um objeto.")
    if not isinstance(channels_payload, list):
        raise ValueError("A seção 'channels' deve ser uma lista.")

    profile = TccOperationalProfile(
        profile_version=int(payload.get("profile_version", 1)),
        name=str(payload.get("name", "")).strip(),
        locked=bool(payload.get("locked", True)),
        baudrate=int(payload.get("baudrate", 115200)),
        base_sample_rate_hz=int(payload.get("base_sample_rate_hz", 1000)),
        window_seconds=int(payload.get("window_seconds", 10)),
        adc_reference_voltage_v=float(adc.get("reference_voltage_v", 2.5)),
        adc_gain=int(adc.get("gain", 1)),
        protocol={str(key): value for key, value in protocol.items()},
        firmware={str(key): value for key, value in firmware.items()},
        channels=tuple(
            TccChannelProfile.from_dict(item)
            for item in channels_payload
            if isinstance(item, dict)
        ),
    )
    profile.validate()
    return profile


TCC_PROFILE = load_tcc_profile()
