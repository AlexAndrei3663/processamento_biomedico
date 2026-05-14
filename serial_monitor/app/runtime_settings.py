from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Configurações de execução da aplicação.

    Essas opções não pertencem à sessão de aquisição. Elas controlam como a
    interface roda no equipamento alvo, especialmente na Raspberry Pi.
    """

    fullscreen: bool = False
    update_interval_ms: int = 100
    max_plot_points: int = 5000
    data_dir: Path = Path("data")

    @property
    def sessions_dir(self) -> Path:
        return self.data_dir / "sessions"

    @property
    def presets_dir(self) -> Path:
        return self.data_dir / "config_presets"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serial Monitor biomédico")
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="abre a interface em tela cheia",
    )
    parser.add_argument(
        "--update-interval-ms",
        type=int,
        default=100,
        help="intervalo de atualização da GUI em milissegundos (50 a 2000)",
    )
    parser.add_argument(
        "--max-plot-points",
        type=int,
        default=5000,
        help="máximo de pontos renderizados por curva (100 a 100000)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="diretório base para sessões salvas e presets",
    )
    return parser


def parse_runtime_settings(argv: Sequence[str] | None = None) -> RuntimeSettings:
    namespace = build_arg_parser().parse_args(argv)
    if not 50 <= namespace.update_interval_ms <= 2000:
        raise ValueError("--update-interval-ms deve estar entre 50 e 2000 ms.")
    if not 100 <= namespace.max_plot_points <= 100_000:
        raise ValueError("--max-plot-points deve estar entre 100 e 100000 pontos.")

    return RuntimeSettings(
        fullscreen=bool(namespace.fullscreen),
        update_interval_ms=int(namespace.update_interval_ms),
        max_plot_points=int(namespace.max_plot_points),
        data_dir=Path(namespace.data_dir),
    )
