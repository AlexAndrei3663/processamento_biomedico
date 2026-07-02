from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from serial_monitor.domain.enums import ConversionModel, SignalType
from serial_monitor.domain.models import ConversionProfile


class ConversionProfileRepository:
    """Carrega e valida perfis versionados de conversão de unidades."""

    SUPPORTED_FILE_VERSION = 1

    def __init__(self, path: str | Path = "config/conversion_profiles.json") -> None:
        self.path = Path(path)
        self._profiles: dict[str, ConversionProfile] = {}
        self._loaded = False

    def reload(self) -> None:
        if not self.path.exists():
            raise FileNotFoundError(f"Arquivo de perfis de conversão não encontrado: {self.path}")

        source = json.loads(self.path.read_text(encoding="utf-8"))
        version = int(source.get("version", 0))
        if version != self.SUPPORTED_FILE_VERSION:
            raise ValueError(
                f"Versão do arquivo de conversão incompatível: {version}; "
                f"esperada {self.SUPPORTED_FILE_VERSION}."
            )

        raw_profiles = source.get("profiles")
        if not isinstance(raw_profiles, dict) or not raw_profiles:
            raise ValueError("O arquivo de conversão não possui perfis válidos.")

        profiles: dict[str, ConversionProfile] = {}
        for profile_id, payload in raw_profiles.items():
            if not isinstance(payload, dict):
                raise ValueError(f"Perfil '{profile_id}' deve ser um objeto JSON.")
            profile = self._parse_profile(str(profile_id), payload)
            if profile.profile_id in profiles:
                raise ValueError(f"Perfil de conversão duplicado: {profile.profile_id}")
            profiles[profile.profile_id] = profile

        self._profiles = profiles
        self._loaded = True

    def list_profiles(self) -> list[ConversionProfile]:
        self._ensure_loaded()
        return sorted(self._profiles.values(), key=lambda item: item.profile_id.casefold())

    def compatible_profiles(self, signal_type: SignalType) -> list[ConversionProfile]:
        return [
            profile
            for profile in self.list_profiles()
            if profile.signal_type is None or profile.signal_type == signal_type
        ]

    def get(self, profile_id: str) -> ConversionProfile:
        self._ensure_loaded()
        try:
            return self._profiles[profile_id]
        except KeyError as exc:
            raise KeyError(f"Perfil de conversão não encontrado: {profile_id}") from exc

    def snapshot(self, profile_ids: Iterable[str]) -> dict[str, dict]:
        """Retorna uma cópia serializável dos perfis utilizados pela sessão."""

        result: dict[str, dict] = {}
        for profile_id in sorted(set(profile_ids)):
            result[profile_id] = self.get(profile_id).to_dict()
        return result

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.reload()

    def _parse_profile(self, profile_id: str, payload: dict) -> ConversionProfile:
        raw_signal_type = str(payload.get("signal_type", "*")).strip()
        signal_type = None if raw_signal_type in {"", "*", "any"} else SignalType.from_text(raw_signal_type)

        valid_input_range = self._optional_range(payload.get("valid_input_range"), "valid_input_range")
        valid_output_range = self._optional_range(payload.get("valid_output_range"), "valid_output_range")

        parameters = payload.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ValueError(f"Parâmetros do perfil '{profile_id}' devem ser um objeto.")

        profile = ConversionProfile(
            profile_id=profile_id,
            version=int(payload.get("version", 1)),
            signal_type=signal_type,
            model=ConversionModel(str(payload.get("model", "identity"))),
            input_unit=str(payload.get("input_unit", "count")),
            output_unit=str(payload.get("output_unit", "a.u.")),
            parameters=dict(parameters),
            description=str(payload.get("description", "")),
            valid_input_range=valid_input_range,
            valid_output_range=valid_output_range,
            origin=str(payload.get("origin", "")),
            created_at=str(payload.get("created_at", "")),
            reference_equipment=str(payload.get("reference_equipment", "")),
            estimated_uncertainty=str(payload.get("estimated_uncertainty", "")),
        )
        profile.validate()
        return profile

    @staticmethod
    def _optional_range(value: object, field_name: str) -> tuple[float, float] | None:
        if value is None:
            return None
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError(f"'{field_name}' deve conter [mínimo, máximo].")
        lower, upper = float(value[0]), float(value[1])
        if lower >= upper:
            raise ValueError(f"Faixa inválida em '{field_name}': mínimo deve ser menor que máximo.")
        return lower, upper
