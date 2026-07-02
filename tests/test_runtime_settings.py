from pathlib import Path

import pytest

from serial_monitor.app.runtime_settings import RuntimeSettings, parse_runtime_settings


def test_parse_runtime_settings_defaults() -> None:
    settings = parse_runtime_settings([])
    assert settings == RuntimeSettings()
    assert settings.sessions_dir == Path("data") / "sessions"
    assert settings.presets_dir == Path("data") / "config_presets"


def test_parse_runtime_settings_custom_values() -> None:
    settings = parse_runtime_settings([
        "--fullscreen",
        "--update-interval-ms",
        "150",
        "--max-plot-points",
        "3000",
        "--data-dir",
        "runtime_data",
        "--recording-queue-capacity",
        "4096",
        "--recording-batch-size",
        "128",
        "--recording-flush-interval-ms",
        "500",
    ])
    assert settings.fullscreen is True
    assert settings.update_interval_ms == 150
    assert settings.max_plot_points == 3000
    assert settings.data_dir == Path("runtime_data")
    assert settings.recording_queue_capacity == 4096
    assert settings.recording_batch_size == 128
    assert settings.recording_flush_interval_ms == 500


@pytest.mark.parametrize(
    "args",
    [
        ["--update-interval-ms", "10"],
        ["--update-interval-ms", "5000"],
        ["--max-plot-points", "10"],
        ["--max-plot-points", "200000"],
        ["--recording-queue-capacity", "10"],
        ["--recording-batch-size", "0"],
        ["--recording-queue-capacity", "128", "--recording-batch-size", "256"],
        ["--recording-flush-interval-ms", "10"],
    ],
)
def test_parse_runtime_settings_rejects_invalid_ranges(args: list[str]) -> None:
    with pytest.raises(ValueError):
        parse_runtime_settings(args)
