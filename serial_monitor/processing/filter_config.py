from __future__ import annotations

from dataclasses import dataclass, replace
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class FilterParameters:
    """Parâmetros de filtragem independentes do tipo de sinal.

    Nesta etapa, a interface expõe as frequências de corte do passa-altas e do
    passa-baixas. Os demais campos já ficam centralizados para extensões futuras
    sem alterar a API do processamento.
    """

    highpass_cutoff_hz: float = 0.5
    lowpass_cutoff_hz: float = 40.0
    notch_frequency_hz: float = 60.0
    notch_q: float = 30.0
    moving_average_ms: float = 50.0
    butterworth_order: int = 2

    EDITABLE_IDS: ClassVar[tuple[str, ...]] = (
        "highpass_cutoff_hz",
        "lowpass_cutoff_hz",
    )

    @classmethod
    def defaults_for_sample_rate(cls, sample_rate_hz: float) -> "FilterParameters":
        sample_rate_hz = float(sample_rate_hz)
        if sample_rate_hz <= 0:
            raise ValueError("A taxa de amostragem deve ser maior que zero.")
        limit = sample_rate_hz * 0.45
        lowpass = min(40.0, limit)
        highpass = min(0.5, max(0.001, lowpass * 0.25))
        if lowpass <= highpass:
            lowpass = min(limit, max(0.002, highpass * 2.0))
            highpass = max(0.001, lowpass * 0.25)
        return cls(
            highpass_cutoff_hz=highpass,
            lowpass_cutoff_hz=lowpass,
        ).validated(sample_rate_hz)

    def validated(self, sample_rate_hz: float) -> "FilterParameters":
        sample_rate_hz = float(sample_rate_hz)
        if sample_rate_hz <= 0:
            raise ValueError("A taxa de amostragem deve ser maior que zero.")
        nyquist = sample_rate_hz / 2.0
        if not 0 < self.highpass_cutoff_hz < self.lowpass_cutoff_hz < nyquist:
            raise ValueError(
                "As frequências devem respeitar 0 < passa-altas < passa-baixas < fs/2."
            )
        if self.notch_frequency_hz <= 0:
            raise ValueError("A frequência do notch deve ser maior que zero.")
        if self.notch_q <= 0:
            raise ValueError("O fator Q do notch deve ser maior que zero.")
        if self.moving_average_ms <= 0:
            raise ValueError("A janela da média móvel deve ser maior que zero.")
        if self.butterworth_order <= 0:
            raise ValueError("A ordem do Butterworth deve ser maior que zero.")
        return self

    def with_value(
        self,
        parameter_id: str,
        value: float,
        sample_rate_hz: float,
    ) -> "FilterParameters":
        if parameter_id not in self.EDITABLE_IDS:
            raise ValueError(f"Parâmetro de filtro desconhecido: {parameter_id}")
        updated = replace(self, **{parameter_id: float(value)})
        return updated.validated(sample_rate_hz)

    def to_dict(self) -> dict[str, float | int]:
        return {
            "highpass_cutoff_hz": self.highpass_cutoff_hz,
            "lowpass_cutoff_hz": self.lowpass_cutoff_hz,
            "notch_frequency_hz": self.notch_frequency_hz,
            "notch_q": self.notch_q,
            "moving_average_ms": self.moving_average_ms,
            "butterworth_order": self.butterworth_order,
        }
