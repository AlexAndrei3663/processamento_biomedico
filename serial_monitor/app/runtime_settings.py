from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Configurações de execução da aplicação e do gravador contínuo."""

    fullscreen: bool = False
    update_interval_ms: int = 100
    max_plot_points: int = 5000
    data_dir: Path = Path("data")
    recording_queue_capacity: int = 8192
    recording_batch_size: int = 256
    recording_flush_interval_ms: int = 1000
    conversion_profiles_path: Path = Path("config/conversion_profiles.json")

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
    parser.add_argument(
        "--conversion-profiles",
        type=Path,
        default=Path("config/conversion_profiles.json"),
        help="arquivo JSON versionado com perfis de conversão",
    )
    parser.add_argument(
        "--recording-queue-capacity",
        type=int,
        default=8192,
        help="quantidade máxima de frames aguardando escrita HDF5",
    )
    parser.add_argument(
        "--recording-batch-size",
        type=int,
        default=256,
        help="quantidade de frames por lote de escrita HDF5",
    )
    parser.add_argument(
        "--recording-flush-interval-ms",
        type=int,
        default=1000,
        help="intervalo máximo entre flushes do HDF5",
    )
    return parser


def parse_runtime_settings(argv: Sequence[str] | None = None) -> RuntimeSettings:
    namespace = build_arg_parser().parse_args(argv)
    if not 50 <= namespace.update_interval_ms <= 2000:
        raise ValueError("--update-interval-ms deve estar entre 50 e 2000 ms.")
    if not 100 <= namespace.max_plot_points <= 100_000:
        raise ValueError("--max-plot-points deve estar entre 100 e 100000 pontos.")
    if not 128 <= namespace.recording_queue_capacity <= 1_000_000:
        raise ValueError("--recording-queue-capacity deve estar entre 128 e 1000000.")
    if not 1 <= namespace.recording_batch_size <= namespace.recording_queue_capacity:
        raise ValueError(
            "--recording-batch-size deve estar entre 1 e a capacidade da fila."
        )
    if not 50 <= namespace.recording_flush_interval_ms <= 60_000:
        raise ValueError(
            "--recording-flush-interval-ms deve estar entre 50 e 60000 ms."
        )

    return RuntimeSettings(
        fullscreen=bool(namespace.fullscreen),
        update_interval_ms=int(namespace.update_interval_ms),
        max_plot_points=int(namespace.max_plot_points),
        data_dir=Path(namespace.data_dir),
        recording_queue_capacity=int(namespace.recording_queue_capacity),
        recording_batch_size=int(namespace.recording_batch_size),
        recording_flush_interval_ms=int(namespace.recording_flush_interval_ms),
        conversion_profiles_path=Path(namespace.conversion_profiles),
    )
