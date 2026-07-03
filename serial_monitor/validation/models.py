from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from serial_monitor.domain.enums import SignalType


@dataclass(frozen=True, slots=True)
class ValidationCycleSpec:
    cycle_id: str
    label: str
    signals: tuple[SignalType, ...]
    base_sample_rate_hz: int
    window_size: int
    filters_by_channel: dict[int, tuple[str, ...]] = field(default_factory=dict)
    conversion_profile_by_channel: dict[int, str] = field(default_factory=dict)
    max_sample_rate_error_percent: float = 1.0
    max_missing_frames: int = 0
    max_invalid_frames: int = 0
    max_queue_usage_percent: float = 80.0


@dataclass(frozen=True, slots=True)
class TimingMetrics:
    frame_count: int = 0
    first_timestamp_us: int | None = None
    last_timestamp_us: int | None = None
    effective_sample_rate_hz: float | None = None
    mean_interval_us: float | None = None
    interval_std_us: float | None = None
    maximum_jitter_us: float | None = None
    non_positive_intervals: int = 0


@dataclass(frozen=True, slots=True)
class ResourcePeaks:
    cpu_percent: float | None = None
    memory_percent: float | None = None
    temperature_c: float | None = None
    minimum_disk_free_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    name: str
    passed: bool
    detail: str


@dataclass(slots=True)
class ValidationReport:
    cycle_id: str
    cycle_label: str
    started_at: str
    ended_at: str
    requested_frames: int
    generated_frames: int
    accepted_frames: int
    recorded_frames: int
    exported_rows: int | None
    integrity_status: str
    session_id: str | None
    session_path: str | None
    csv_path: str | None
    report_json_path: str | None = None
    report_markdown_path: str | None = None
    communication: dict[str, int] = field(default_factory=dict)
    timing: TimingMetrics = field(default_factory=TimingMetrics)
    resources: ResourcePeaks = field(default_factory=ResourcePeaks)
    queue_high_watermark: int = 0
    queue_capacity: int = 0
    processing_channels_checked: int = 0
    checks: list[ValidationCheck] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["passed"] = self.passed
        return payload

    def save(self, output_dir: str | Path) -> tuple[Path, Path]:
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        stem = f"validation_{self.cycle_id}_{self.started_at.replace(':', '').replace('-', '')}"
        json_path = directory / f"{stem}.json"
        md_path = directory / f"{stem}.md"
        self.report_json_path = str(json_path)
        self.report_markdown_path = str(md_path)
        json_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        md_path.write_text(self.to_markdown(), encoding="utf-8")
        return json_path, md_path

    def to_markdown(self) -> str:
        status = "APROVADO" if self.passed else "REPROVADO"
        lines = [
            f"# Relatório de validação — {self.cycle_label}",
            "",
            f"**Resultado:** {status}",
            f"**Ciclo:** `{self.cycle_id}`",
            f"**Início:** {self.started_at}",
            f"**Fim:** {self.ended_at}",
            "",
            "## Integridade do fluxo",
            "",
            f"- Frames solicitados: {self.requested_frames}",
            f"- Frames gerados: {self.generated_frames}",
            f"- Frames aceitos: {self.accepted_frames}",
            f"- Frames gravados: {self.recorded_frames}",
            f"- Linhas exportadas: {self.exported_rows if self.exported_rows is not None else 'não executado'}",
            f"- Integridade HDF5: {self.integrity_status}",
            f"- Máximo da fila: {self.queue_high_watermark}/{self.queue_capacity}",
            "",
            "## Temporização",
            "",
            f"- Taxa efetiva: {self._fmt(self.timing.effective_sample_rate_hz, ' Hz')}",
            f"- Intervalo médio: {self._fmt(self.timing.mean_interval_us, ' µs')}",
            f"- Desvio-padrão do intervalo: {self._fmt(self.timing.interval_std_us, ' µs')}",
            f"- Jitter máximo: {self._fmt(self.timing.maximum_jitter_us, ' µs')}",
            f"- Intervalos não positivos: {self.timing.non_positive_intervals}",
            "",
            "## Recursos",
            "",
            f"- Pico de CPU: {self._fmt(self.resources.cpu_percent, '%')}",
            f"- Pico de RAM: {self._fmt(self.resources.memory_percent, '%')}",
            f"- Pico de temperatura: {self._fmt(self.resources.temperature_c, ' °C')}",
            f"- Menor espaço livre: {self._format_bytes(self.resources.minimum_disk_free_bytes)}",
            "",
            "## Critérios de aceitação",
            "",
        ]
        for check in self.checks:
            marker = "x" if check.passed else " "
            lines.append(f"- [{marker}] **{check.name}:** {check.detail}")
        if self.notes:
            lines.extend(["", "## Observações", ""])
            lines.extend(f"- {note}" for note in self.notes)
        lines.extend(
            [
                "",
                "## Artefatos",
                "",
                f"- Sessão HDF5: `{self.session_path or '--'}`",
                f"- CSV: `{self.csv_path or '--'}`",
                "",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _fmt(value: float | None, suffix: str) -> str:
        return "--" if value is None else f"{value:.3f}{suffix}"

    @staticmethod
    def _format_bytes(value: int | None) -> str:
        if value is None:
            return "--"
        size = float(max(0, value))
        for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
            if size < 1024.0 or unit == "TiB":
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TiB"
