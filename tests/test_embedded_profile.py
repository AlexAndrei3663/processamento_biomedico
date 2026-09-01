import ast
from pathlib import Path


def test_raspberry_profile_uses_conservative_defaults():
    source = Path("scripts/run_raspberry.sh").read_text(encoding="utf-8")

    assert "BIOMED_UPDATE_INTERVAL_MS:-250" in source
    assert "BIOMED_MAX_PLOT_POINTS:-2000" in source
    assert "BIOMED_RECORDING_BATCH_SIZE:-512" in source
    assert "BIOMED_RECORDING_FLUSH_INTERVAL_MS:-2000" in source
    assert "BIOMED_OPERATIONAL_UPDATE_INTERVAL_MS:-2000" in source


def test_embedded_benchmark_is_syntactically_valid_and_paced():
    source = Path("scripts/benchmark_embedded.py").read_text(encoding="utf-8")

    ast.parse(source)
    assert "time.sleep(deadline - now)" in source
    assert "communication.missing_frames == 0" in source
    assert "status.frames_written == total_frames" in source
