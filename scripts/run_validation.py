#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from serial_monitor.validation.plan_repository import ValidationPlanRepository
from serial_monitor.validation.runner import ValidationRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Executa a validação progressiva e reprodutível do sistema."
    )
    parser.add_argument(
        "--plan",
        type=Path,
        default=Path("config/validation_plan.json"),
        help="arquivo JSON com os ciclos progressivos",
    )
    parser.add_argument(
        "--cycle",
        default="cycle1_ecg",
        help="cycle_id a executar ou 'all' para executar todos",
    )
    parser.add_argument(
        "--profile",
        default="smoke",
        help="perfil de duração: smoke, one_minute, one_hour ou eight_hours",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        help="sobrescreve a duração definida pelo perfil",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/validation"),
        help="diretório para HDF5, CSV e relatórios",
    )
    parser.add_argument(
        "--conversion-profiles",
        type=Path,
        default=Path("config/conversion_profiles.json"),
    )
    parser.add_argument(
        "--real-time",
        action="store_true",
        help="respeita o tempo de aquisição; sem esta opção o teste é acelerado",
    )
    parser.add_argument(
        "--skip-csv",
        action="store_true",
        help="não exporta CSV; útil em ensaios prolongados exploratórios",
    )
    parser.add_argument("--seed", type=int, default=2026)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plans = ValidationPlanRepository(args.plan)
    duration = (
        args.duration_seconds
        if args.duration_seconds is not None
        else plans.duration_for_profile(args.profile)
    )
    cycles = plans.list_cycles() if args.cycle == "all" else [plans.get(args.cycle)]
    runner = ValidationRunner(
        output_dir=args.output_dir,
        conversion_profiles_path=args.conversion_profiles,
    )

    failed = False
    for cycle in cycles:
        print(f"Executando {cycle.label} por {duration:g} s...", flush=True)
        report = runner.run(
            cycle,
            duration_seconds=duration,
            real_time=args.real_time,
            export_csv=not args.skip_csv,
            seed=args.seed,
        )
        result = "APROVADO" if report.passed else "REPROVADO"
        print(
            f"{result}: {cycle.cycle_id} | frames={report.recorded_frames} | "
            f"relatório={report.report_markdown_path}",
            flush=True,
        )
        failed = failed or not report.passed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
