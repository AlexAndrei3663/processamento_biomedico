from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

from serial_monitor.domain.models import SystemResourceSnapshot


class OperationalMonitor:
    """Coleta diagnóstico operacional sem exigir dependências externas.

    Na Raspberry Pi, CPU e memória são lidas em ``/proc`` e a temperatura em
    ``/sys/class/thermal``. Em outras plataformas, os campos indisponíveis são
    retornados como ``None``; o espaço em disco continua sendo informado.
    """

    def __init__(
        self,
        data_path: str | Path,
        *,
        proc_root: str | Path = "/proc",
        sys_root: str | Path = "/sys",
        disk_usage: Callable[[str | Path], object] = shutil.disk_usage,
    ) -> None:
        self.data_path = Path(data_path)
        self.proc_root = Path(proc_root)
        self.sys_root = Path(sys_root)
        self._disk_usage = disk_usage
        self._previous_cpu: tuple[int, int] | None = None

    def sample(self) -> SystemResourceSnapshot:
        disk_path = self._existing_disk_path(self.data_path)
        try:
            usage = self._disk_usage(disk_path)
            disk_free = int(getattr(usage, "free"))
            disk_total = int(getattr(usage, "total"))
            # Alguns ambientes virtualizados expõem 2**63 como valor sentinela.
            if disk_total <= 0 or disk_free < 0 or disk_free > disk_total or disk_total >= (1 << 62):
                disk_free = 0
                disk_total = 0
        except (OSError, ValueError, AttributeError, TypeError):
            disk_free = 0
            disk_total = 0

        return SystemResourceSnapshot(
            captured_at=datetime.now().isoformat(timespec="milliseconds"),
            disk_free_bytes=disk_free,
            disk_total_bytes=disk_total,
            cpu_percent=self._read_cpu_percent(),
            memory_percent=self._read_memory_percent(),
            temperature_c=self._read_temperature_c(),
        )

    @staticmethod
    def _existing_disk_path(path: Path) -> Path:
        current = path.expanduser()
        while not current.exists() and current.parent != current:
            current = current.parent
        return current if current.exists() else Path.cwd()

    def _read_cpu_percent(self) -> float | None:
        cpu_line = self._read_first_line(self.proc_root / "stat")
        if cpu_line is None or not cpu_line.startswith("cpu "):
            return None
        try:
            values = [int(item) for item in cpu_line.split()[1:]]
        except ValueError:
            return None
        if len(values) < 4:
            return None

        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        current = (idle, total)
        previous = self._previous_cpu
        self._previous_cpu = current
        if previous is None:
            return None

        idle_delta = idle - previous[0]
        total_delta = total - previous[1]
        if total_delta <= 0:
            return None
        percent = 100.0 * (1.0 - idle_delta / total_delta)
        return max(0.0, min(100.0, percent))

    def _read_memory_percent(self) -> float | None:
        try:
            lines = (self.proc_root / "meminfo").read_text(
                encoding="utf-8", errors="replace"
            ).splitlines()
        except OSError:
            return None

        values: dict[str, int] = {}
        for line in lines:
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            token = raw.strip().split()[0] if raw.strip() else ""
            try:
                values[key] = int(token)
            except ValueError:
                continue

        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable")
        if available is None:
            available = values.get("MemFree", 0) + values.get("Buffers", 0) + values.get(
                "Cached", 0
            )
        if total <= 0:
            return None
        used = max(0, total - available)
        return max(0.0, min(100.0, 100.0 * used / total))

    def _read_temperature_c(self) -> float | None:
        thermal_root = self.sys_root / "class" / "thermal"
        try:
            candidates = sorted(thermal_root.glob("thermal_zone*/temp"))
        except OSError:
            return None

        for path in candidates:
            try:
                value = float(path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                continue
            if abs(value) > 1000.0:
                value /= 1000.0
            if -20.0 <= value <= 150.0:
                return value
        return None

    @staticmethod
    def _read_first_line(path: Path) -> str | None:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                return handle.readline().strip()
        except OSError:
            return None
