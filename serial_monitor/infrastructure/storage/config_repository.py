from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List

from serial_monitor.domain.models import SessionPreset


class ConfigRepository:
    """Persistência simples de presets de configuração da sessão."""

    SUFFIX = ".json"

    def __init__(self, base_dir: str | Path = "data/config_presets") -> None:
        self.base_dir = Path(base_dir)

    def save_preset(
        self,
        *,
        name: str,
        port: str,
        baudrate: int,
        base_sample_rate_hz: int,
        window_size: int,
        signal_order_text: str,
        channel_conversions: list[dict] | None = None,
        adc_reference_voltage_v: float = 2.5,
        adc_gain: int = 1,
    ) -> SessionPreset:
        normalized_name = self._normalize_name(name)
        if baudrate <= 0:
            raise ValueError("O baudrate deve ser maior que zero.")
        if base_sample_rate_hz <= 0:
            raise ValueError("A taxa base deve ser maior que zero.")
        if window_size <= 0:
            raise ValueError("A janela deve ser maior que zero.")
        if adc_reference_voltage_v <= 0:
            raise ValueError("A tensão de referência do ADC deve ser maior que zero.")
        if adc_gain not in (1, 2, 4, 8, 16, 32, 64):
            raise ValueError("Ganho inválido para o ADS1256.")
        if not signal_order_text.strip():
            raise ValueError("Informe a ordem dos sinais antes de salvar o preset.")

        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for_name(normalized_name)
        now = datetime.now().isoformat(timespec="seconds")
        created_at = now
        if path.exists():
            try:
                created_at = str(
                    json.loads(path.read_text(encoding="utf-8")).get(
                        "created_at", now
                    )
                )
            except Exception:
                created_at = now

        payload = {
            "version": 3,
            "name": normalized_name,
            "created_at": created_at,
            "updated_at": now,
            "port": port.strip(),
            "baudrate": int(baudrate),
            "base_sample_rate_hz": int(base_sample_rate_hz),
            "window_size": int(window_size),
            "signal_order_text": signal_order_text.strip(),
            "adc": {
                "model": "ADS1256",
                "input_mode": "differential",
                "reference_voltage_v": float(adc_reference_voltage_v),
                "gain": int(adc_gain),
            },
            "channel_conversions": [
                {
                    "channel_index": int(item.get("channel_index", index)),
                    "mode": self._conversion_mode(item),
                }
                for index, item in enumerate(channel_conversions or [])
                if isinstance(item, dict)
            ],
        }
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return self._preset_from_payload(payload, path)

    def list_presets(self) -> List[SessionPreset]:
        if not self.base_dir.exists():
            return []
        presets: List[SessionPreset] = []
        for path in self.base_dir.glob(f"*{self.SUFFIX}"):
            try:
                presets.append(
                    self._preset_from_payload(
                        json.loads(path.read_text(encoding="utf-8")), path
                    )
                )
            except Exception:
                continue
        return sorted(presets, key=lambda item: item.name.casefold())

    def load_preset(self, name: str) -> SessionPreset:
        normalized_name = self._normalize_name(name)
        path = self._path_for_name(normalized_name)
        if not path.exists():
            raise FileNotFoundError(f"Preset não encontrado: {normalized_name}")
        return self._preset_from_payload(
            json.loads(path.read_text(encoding="utf-8")), path
        )

    def delete_preset(self, name: str) -> None:
        normalized_name = self._normalize_name(name)
        path = self._path_for_name(normalized_name)
        if not path.exists():
            raise FileNotFoundError(f"Preset não encontrado: {normalized_name}")
        path.unlink()

    def _path_for_name(self, name: str) -> Path:
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip()).strip("._")
        if not safe:
            raise ValueError("Nome do preset inválido.")
        return self.base_dir / f"{safe}{self.SUFFIX}"

    def _normalize_name(self, name: str) -> str:
        value = name.strip()
        if not value:
            raise ValueError("Informe um nome para o preset.")
        if len(value) > 80:
            raise ValueError("O nome do preset deve ter no máximo 80 caracteres.")
        return value

    @staticmethod
    def _conversion_mode(item: dict) -> str:
        mode = str(item.get("mode", "")).strip().lower()
        if mode in {"raw", "voltage"}:
            return mode
        return "voltage" if bool(item.get("enabled", False)) else "raw"

    def _preset_from_payload(self, payload: dict, path: Path) -> SessionPreset:
        adc = payload.get("adc", {})
        if not isinstance(adc, dict):
            adc = {}
        return SessionPreset(
            name=str(payload.get("name", path.stem)),
            created_at=str(payload.get("created_at", "")),
            updated_at=str(payload.get("updated_at", "")),
            port=str(payload.get("port", "")),
            baudrate=int(payload.get("baudrate", 115200)),
            base_sample_rate_hz=int(payload.get("base_sample_rate_hz", 1000)),
            window_size=int(payload.get("window_size", 1000)),
            signal_order_text=str(payload.get("signal_order_text", "")),
            channel_conversions=[
                {
                    "channel_index": int(item.get("channel_index", index)),
                    "mode": self._conversion_mode(item),
                }
                for index, item in enumerate(
                    payload.get("channel_conversions", [])
                )
                if isinstance(item, dict)
            ],
            adc_reference_voltage_v=float(
                adc.get("reference_voltage_v", payload.get("adc_reference_voltage_v", 2.5))
            ),
            adc_gain=int(adc.get("gain", payload.get("adc_gain", 1))),
            path=path,
        )
