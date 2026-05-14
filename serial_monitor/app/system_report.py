from __future__ import annotations

import os
import platform
import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemReport:
    python: str
    platform: str
    machine: str
    processor: str
    cpu_count: int
    qt_api: str

    def as_lines(self) -> list[str]:
        return [
            f"Python: {self.python}",
            f"Sistema: {self.platform}",
            f"Arquitetura: {self.machine}",
            f"Processador: {self.processor or 'não informado'}",
            f"CPUs lógicas: {self.cpu_count}",
            f"Qt binding: {self.qt_api}",
        ]


def collect_system_report() -> SystemReport:
    return SystemReport(
        python=sys.version.split()[0],
        platform=platform.platform(),
        machine=platform.machine(),
        processor=platform.processor(),
        cpu_count=os.cpu_count() or 1,
        qt_api="PyQt5",
    )
