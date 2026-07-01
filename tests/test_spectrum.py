from __future__ import annotations

import numpy as np

from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser
from serial_monitor.processing.filter_pipeline import ProcessingService
from serial_monitor.processing.spectrum import calculate_single_sided_spectrum


def test_single_sided_spectrum_detects_dominant_frequency() -> None:
    sample_rate_hz = 1000.0
    frequency_hz = 10.0
    t = np.arange(1000, dtype=float) / sample_rate_hz
    values = np.sin(2 * np.pi * frequency_hz * t)

    spectrum = calculate_single_sided_spectrum(values, sample_rate_hz)

    assert spectrum.peak_frequency_hz is not None
    assert spectrum.resolution_hz is not None
    assert abs(spectrum.peak_frequency_hz - frequency_hz) <= spectrum.resolution_hz
    assert spectrum.magnitudes.size == spectrum.frequencies_hz.size


def test_spectrum_returns_empty_for_short_or_invalid_input() -> None:
    spectrum = calculate_single_sided_spectrum(np.array([1.0]), 1000.0)

    assert spectrum.frequencies_hz.size == 0
    assert spectrum.magnitudes.size == 0
    assert spectrum.peak_frequency_hz is None


def test_processing_snapshot_contains_raw_and_processed_spectra() -> None:
    session = SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=32,
        signal_order_text="ecg",
    )
    acquisition = LiveAcquisitionService()
    acquisition.configure(session)
    parser = FrameCsvParser()
    for sequence_id in range(1, 33):
        value = float(np.sin(2 * np.pi * 10 * sequence_id / 1000.0))
        acquisition.ingest_frame(parser.parse_line(f"FRAME,{sequence_id},{sequence_id},{sequence_id * 1000},{value}", session).frame)

    processor = ProcessingService()
    processor.configure(session)
    snapshot = processor.process(acquisition.snapshot())
    channel_snapshot = snapshot.channels[0]

    assert channel_snapshot.raw_spectrum.frequencies_hz.size > 0
    assert channel_snapshot.processed_spectrum.frequencies_hz.size > 0
    assert channel_snapshot.raw_spectrum.magnitudes.size == channel_snapshot.processed_spectrum.magnitudes.size
