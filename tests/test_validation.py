from __future__ import annotations

import json
from pathlib import Path

from serial_monitor.validation.plan_repository import ValidationPlanRepository
from serial_monitor.validation.runner import ValidationRunner


ROOT = Path(__file__).parents[1]


def test_validation_cycle_runs_end_to_end_and_generates_reports(tmp_path) -> None:
    plans = ValidationPlanRepository(ROOT / "config" / "validation_plan.json")
    cycle = plans.get("cycle1_ecg")
    runner = ValidationRunner(
        output_dir=tmp_path,
        conversion_profiles_path=ROOT / "config" / "conversion_profiles.json",
        queue_capacity=512,
        batch_size=16,
        flush_interval_s=0.05,
    )

    report = runner.run(
        cycle,
        duration_seconds=0.1,
        export_csv=True,
        seed=1,
    )

    assert report.passed is True
    assert report.recorded_frames == 50
    assert report.exported_rows == 50
    assert report.integrity_status == "verified"
    assert report.timing.effective_sample_rate_hz == 500.0
    assert report.report_json_path is not None
    assert report.report_markdown_path is not None
    payload = json.loads(Path(report.report_json_path).read_text(encoding="utf-8"))
    assert payload["passed"] is True


def test_validation_plan_is_progressive() -> None:
    cycles = ValidationPlanRepository(
        ROOT / "config" / "validation_plan.json"
    ).list_cycles()
    assert [len(cycle.signals) for cycle in cycles] == [1, 2, 3, 4]
    assert [cycle.signals[-1].value for cycle in cycles] == [
        "ecg",
        "ecg",
        "ppg",
        "oximetria",
    ]
