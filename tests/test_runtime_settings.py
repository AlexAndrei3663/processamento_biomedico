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
    ])
    assert settings.fullscreen is True
    assert settings.update_interval_ms == 150
    assert settings.max_plot_points == 3000
    assert settings.data_dir == Path("runtime_data")


@pytest.mark.parametrize(
    "args",
    [
        ["--update-interval-ms", "10"],
        ["--update-interval-ms", "5000"],
        ["--max-plot-points", "10"],
        ["--max-plot-points", "200000"],
    ],
)
def test_parse_runtime_settings_rejects_invalid_ranges(args: list[str]) -> None:
    with pytest.raises(ValueError):
        parse_runtime_settings(args)
