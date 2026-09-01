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
    assert "sys.path.insert(0, str(ROOT))" in source
    assert "time.sleep(deadline - now)" in source
    assert "communication.missing_frames == 0" in source
    assert "status.frames_written == total_frames" in source
    assert '"cpu": cpu_percent_one_core <= args.max_cpu_one_core_percent' in source
    assert '"memory": max_rss_mib is None or max_rss_mib <= args.max_rss_mib' in source
    assert '"lag": maximum_lag_ms <= args.max_lag_ms' in source
    assert '"queue": queue_usage_percent <= args.max_queue_usage_percent' in source
    assert "json.dumps(report" in source
