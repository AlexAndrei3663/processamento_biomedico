from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from serial_monitor.domain.enums import ConversionModel
from serial_monitor.domain.models import SignalChannelConfig


@dataclass(frozen=True, slots=True)
class ConversionResult:
    values: np.ndarray
    enabled: bool
    profile_id: str | None
    input_unit: str
    output_unit: str
    status: tuple[str, ...]
    out_of_input_range: int = 0
    out_of_output_range: int = 0


class ConversionService:
    """Aplica conversões reproduzíveis sem modificar os dados brutos."""

    def convert(self, values: np.ndarray, channel: SignalChannelConfig) -> ConversionResult:
        raw = np.asarray(values, dtype=float)
        config = channel.conversion

        if not config.enabled:
            return ConversionResult(
                values=raw.copy(),
                enabled=False,
                profile_id=None,
                input_unit=channel.raw_unit,
                output_unit=channel.raw_unit,
                status=("Conversão desabilitada; valores brutos preservados.",),
            )

        profile = channel.conversion_profile
        if profile is None:
            raise RuntimeError(
                f"Canal ch{channel.index} habilitou conversão sem snapshot de perfil."
            )
        if config.profile_id != profile.profile_id:
            raise RuntimeError(
                f"Canal ch{channel.index} referencia '{config.profile_id}', mas recebeu "
                f"o snapshot '{profile.profile_id}'."
            )
        if profile.signal_type is not None and profile.signal_type != channel.signal_type:
            raise ValueError(
                f"Perfil '{profile.profile_id}' não é compatível com {channel.signal_type.value}."
            )
        if raw.size and not np.all(np.isfinite(raw)):
            raise ValueError(f"Canal ch{channel.index} contém NaN ou infinito.")

        input_outside = self._count_outside(raw, profile.valid_input_range)
        converted = self._apply_model(raw, profile.model, profile.parameters)
        if converted.shape != raw.shape:
            raise ValueError(
                f"Perfil '{profile.profile_id}' produziu um vetor com tamanho inválido."
            )
        if converted.size and not np.all(np.isfinite(converted)):
            raise ValueError(
                f"Perfil '{profile.profile_id}' produziu NaN ou infinito."
            )
        output_outside = self._count_outside(converted, profile.valid_output_range)

        status = [
            f"Conversão aplicada: {profile.profile_id} ({profile.model.value})."
        ]
        if input_outside:
            status.append(
                f"Aviso: {input_outside} amostra(s) fora da faixa de entrada do perfil."
            )
        if output_outside:
            status.append(
                f"Aviso: {output_outside} amostra(s) fora da faixa de saída esperada."
            )

        return ConversionResult(
            values=converted,
            enabled=True,
            profile_id=profile.profile_id,
            input_unit=profile.input_unit,
            output_unit=profile.output_unit,
            status=tuple(status),
            out_of_input_range=input_outside,
            out_of_output_range=output_outside,
        )

    def _apply_model(
        self,
        values: np.ndarray,
        model: ConversionModel,
        parameters: dict,
    ) -> np.ndarray:
        if model == ConversionModel.IDENTITY:
            return values.copy()

        if model == ConversionModel.LINEAR:
            scale = self._required_float(parameters, "scale")
            offset = self._required_float(parameters, "offset")
            return values * scale + offset

        if model == ConversionModel.POLYNOMIAL:
            coefficients = parameters.get("coefficients")
            if not isinstance(coefficients, list) or not coefficients:
                raise ValueError("Conversão polinomial exige a lista 'coefficients'.")
            result = np.zeros_like(values, dtype=float)
            for power, coefficient in enumerate(coefficients):
                result += float(coefficient) * np.power(values, power)
            return result

        if model == ConversionModel.LOOKUP_TABLE:
            x_values = parameters.get("input")
            y_values = parameters.get("output")
            if not isinstance(x_values, list) or not isinstance(y_values, list):
                raise ValueError("Conversão por tabela exige as listas 'input' e 'output'.")
            if len(x_values) != len(y_values) or len(x_values) < 2:
                raise ValueError("Tabela de conversão exige ao menos dois pares ordenados.")
            x = np.asarray(x_values, dtype=float)
            y = np.asarray(y_values, dtype=float)
            if not np.all(np.diff(x) > 0):
                raise ValueError("Os valores de entrada da tabela devem ser estritamente crescentes.")
            return np.interp(values, x, y)

        raise ValueError(f"Modelo de conversão não implementado: {model.value}")

    @staticmethod
    def _required_float(parameters: dict, name: str) -> float:
        if name not in parameters:
            raise ValueError(f"Parâmetro obrigatório ausente: {name}")
        return float(parameters[name])

    @staticmethod
    def _count_outside(
        values: np.ndarray,
        valid_range: tuple[float, float] | None,
    ) -> int:
        if valid_range is None or values.size == 0:
            return 0
        lower, upper = valid_range
        return int(np.count_nonzero((values < lower) | (values > upper)))
