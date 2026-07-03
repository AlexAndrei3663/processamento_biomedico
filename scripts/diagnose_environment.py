from __future__ import annotations

import importlib
import platform
import sys
from pathlib import Path

REQUIRED_MODULES = ["PyQt5", "pyqtgraph", "serial", "numpy", "scipy", "h5py"]


def main() -> int:
    print("Diagnóstico do ambiente")
    print("=======================")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Sistema: {platform.platform()}")
    print(f"Arquitetura: {platform.machine()}")
    print(f"Diretório atual: {Path.cwd()}")
    print()

    status = 0
    for module_name in REQUIRED_MODULES:
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "versão não informada")
            print(f"[OK] {module_name}: {version}")
        except Exception as exc:
            print(f"[ERRO] {module_name}: {exc}")
            status = 1

    print()
    validation_plan = Path("config/validation_plan.json")
    if validation_plan.exists():
        print(f"[OK] Plano de validação: {validation_plan}")
    else:
        print(f"[ERRO] Plano de validação ausente: {validation_plan}")
        status = 1

    legacy_profiles = Path("config/conversion_profiles.json")
    if legacy_profiles.exists():
        print(f"[OK] Perfis legados para validação: {legacy_profiles}")
    else:
        print(
            "[AVISO] Perfis legados ausentes; a aplicação gráfica funciona, "
            "mas alguns ensaios de compatibilidade podem não executar."
        )

    print()
    print("Portas seriais detectadas:")
    try:
        from serial.tools import list_ports

        ports = list(list_ports.comports())
        if not ports:
            print("  nenhuma porta encontrada")
        for port in ports:
            print(f"  {port.device} - {port.description}")
    except Exception as exc:
        print(f"  erro ao listar portas: {exc}")
        status = 1

    return status


if __name__ == "__main__":
    raise SystemExit(main())
