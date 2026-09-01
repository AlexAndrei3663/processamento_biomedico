import pytest

from serial_monitor.application.sampling_rate_estimator import SamplingRateEstimator


def test_estimator_locks_after_two_windows():
    estimator = SamplingRateEstimator(1000)

    assert not estimator.observe(0, 0)
    assert not estimator.observe(5_000, 5_000_000)
    assert estimator.observe(10_000, 10_000_000)

    snapshot = estimator.snapshot()
    assert snapshot.locked
    assert snapshot.estimated_hz == pytest.approx(1000.0)
    assert snapshot.completed_windows == 2
    assert snapshot.deviation_percent == pytest.approx(0.0)


def test_estimator_uses_sequence_to_ignore_transport_losses():
    estimator = SamplingRateEstimator(1000)

    estimator.observe(0, 0)
    estimator.observe(5_500, 5_000_000)
    estimator.observe(11_000, 10_000_000)

    snapshot = estimator.snapshot()
    assert snapshot.locked
    assert snapshot.estimated_hz == pytest.approx(1100.0)
    assert snapshot.deviation_percent == pytest.approx(10.0)


def test_estimator_keeps_locked_rate_and_reports_later_change():
    estimator = SamplingRateEstimator(1000)

    estimator.observe(0, 0)
    estimator.observe(5_000, 5_000_000)
    estimator.observe(10_000, 10_000_000)
    estimator.observe(15_500, 15_000_000)

    snapshot = estimator.snapshot()
    assert snapshot.estimated_hz == pytest.approx(1000.0)
    assert snapshot.instability_events == 1


def test_estimator_rejects_implausible_window():
    estimator = SamplingRateEstimator(1000)

    estimator.observe(0, 0)
    estimator.observe(30_000, 5_000_000)

    snapshot = estimator.snapshot()
    assert snapshot.estimated_hz is None
    assert snapshot.rejected_windows == 1


def test_reset_window_preserves_locked_rate():
    estimator = SamplingRateEstimator(1000)

    estimator.observe(0, 0)
    estimator.observe(5_000, 5_000_000)
    estimator.observe(10_000, 10_000_000)
    estimator.reset_window()

    assert not estimator.observe(0, 10_001_000)
    assert not estimator.observe(5_000, 15_001_000)
    assert estimator.snapshot().estimated_hz == pytest.approx(1000.0)
