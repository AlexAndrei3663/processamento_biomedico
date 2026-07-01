from __future__ import annotations

import numpy as np

from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser
from serial_monitor.processing.filter_pipeline import ProcessingService, remove_dc, moving_average


def test_dc_remove_subtracts_mean() -> None:
    values = np.array([1.0, 2.0, 3.0])
    channel = SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=10,
        signal_order_text="ecg",
    ).channels[0]

    output = remove_dc(values, 1000.0, channel)

    assert np.allclose(output, [-1.0, 0.0, 1.0])


def test_moving_average_preserves_vector_size() -> None:
    values = np.arange(21, dtype=float)
    channel = SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=30,
        signal_order_text="ppg",
    ).channels[0]

    output = moving_average(values, 1000.0, channel)

    assert output.shape == values.shape


def test_processing_service_keeps_raw_values_when_no_filter_is_active() -> None:
    session = SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=10,
        signal_order_text="ecg,ppg",
    )
    acquisition = LiveAcquisitionService()
    acquisition.configure(session)
    frame = FrameCsvParser().parse_line("FRAME,1,1000000,1.0,2.0", session).frame
    acquisition.ingest_frame(frame)

    processor = ProcessingService()
    processor.configure(session)
    processed = processor.process(acquisition.snapshot())

    assert np.allclose(processed.channels[0].raw_values, processed.channels[0].processed_values)
    assert processed.channels[0].filter_status == ["Sem filtros ativos."]


def test_processing_service_applies_enabled_filter() -> None:
    session = SessionService().build_session(
        port="COM1",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=10,
        signal_order_text="ecg",
    )
    acquisition = LiveAcquisitionService()
    acquisition.configure(session)
    parser = FrameCsvParser()
    for index, value in enumerate([1.0, 2.0, 3.0], start=1):
        acquisition.ingest_frame(parser.parse_line(f"FRAME,{index},{index * 10_000},{value}", session).frame)

    processor = ProcessingService()
    processor.configure(session)
    processor.set_filter_enabled(0, "dc_remove", True)
    processed = processor.process(acquisition.snapshot())

    assert np.allclose(processed.channels[0].processed_values, [-1.0, 0.0, 1.0])
    assert processed.channels[0].active_filters == ["dc_remove"]
