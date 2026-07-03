from __future__ import annotations

import json
from pathlib import Path

from serial_monitor.domain.enums import SignalType
from serial_monitor.validation.models import ValidationCycleSpec


class ValidationPlanRepository:
    """Carrega os ciclos progressivos de um arquivo JSON versionado."""

    def __init__(self, path: str | Path = "config/validation_plan.json") -> None:
        self.path = Path(path)

    def list_cycles(self) -> list[ValidationCycleSpec]:
        source = self._load_source()
        cycles = source.get("cycles", [])
        if not isinstance(cycles, list):
            raise ValueError("O campo 'cycles' do plano de validação deve ser uma lista.")
        result = [self._parse_cycle(item) for item in cycles]
        if not result:
            raise ValueError("O plano de validação não possui ciclos.")
        ids = [item.cycle_id for item in result]
        if len(ids) != len(set(ids)):
            raise ValueError("O plano de validação possui cycle_id duplicado.")
        return result

    def get(self, cycle_id: str) -> ValidationCycleSpec:
        for cycle in self.list_cycles():
            if cycle.cycle_id == cycle_id:
                return cycle
        raise KeyError(f"Ciclo de validação desconhecido: {cycle_id}")

    def duration_for_profile(self, profile: str) -> float:
        source = self._load_source()
        profiles = source.get("duration_profiles", {})
        if not isinstance(profiles, dict) or profile not in profiles:
            raise KeyError(f"Perfil de duração desconhecido: {profile}")
        duration = float(profiles[profile])
        if duration <= 0:
            raise ValueError(f"Duração inválida no perfil '{profile}'.")
        return duration

    def _load_source(self) -> dict:
        source = json.loads(self.path.read_text(encoding="utf-8"))
        if int(source.get("schema_version", 0)) != 1:
            raise ValueError("Versão do plano de validação incompatível.")
        return source

    @staticmethod
    def _parse_cycle(source: object) -> ValidationCycleSpec:
        if not isinstance(source, dict):
            raise ValueError("Cada ciclo deve ser um objeto JSON.")
        signals = tuple(SignalType.from_text(str(item)) for item in source.get("signals", []))
        if not signals:
            raise ValueError("Cada ciclo deve possuir ao menos um sinal.")

        filters_source = source.get("filters_by_channel", {})
        conversions_source = source.get("conversion_profile_by_channel", {})
        filters = {
            int(index): tuple(str(item) for item in values)
            for index, values in dict(filters_source).items()
        }
        conversions = {
            int(index): str(profile_id)
            for index, profile_id in dict(conversions_source).items()
        }
        criteria = dict(source.get("criteria", {}))
        return ValidationCycleSpec(
            cycle_id=str(source["cycle_id"]),
            label=str(source.get("label", source["cycle_id"])),
            signals=signals,
            base_sample_rate_hz=int(source.get("base_sample_rate_hz", 500)),
            window_size=int(source.get("window_size", 5000)),
            filters_by_channel=filters,
            conversion_profile_by_channel=conversions,
            max_sample_rate_error_percent=float(
                criteria.get("max_sample_rate_error_percent", 1.0)
            ),
            max_missing_frames=int(criteria.get("max_missing_frames", 0)),
            max_invalid_frames=int(criteria.get("max_invalid_frames", 0)),
            max_queue_usage_percent=float(
                criteria.get("max_queue_usage_percent", 80.0)
            ),
        )
