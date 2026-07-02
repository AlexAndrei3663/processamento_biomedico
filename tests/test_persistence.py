from __future__ import annotations

import h5py
import numpy as np

from serial_monitor.application.conversion_service import ConversionService
from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.enums import ConversionModel, SignalType
from serial_monitor.domain.models import (
    ConversionConfig,
    ConversionProfile,
    SampleFrame,
    SessionConfig,
    SignalChannelConfig,
)
from serial_monitor.infrastructure.storage.hdf5_session_writer import Hdf5SessionWriter
from serial_monitor.infrastructure.storage.session_repository import SessionRepository
from serial_monitor.processing.filter_pipeline import ProcessingService


def build_session() -> SessionConfig:
    profile = ConversionProfile(
        profile_id="linear_snapshot",
        version=1,
        signal_type=SignalType.ECG,
        model=ConversionModel.LINEAR,
        input_unit="count",
        output_unit="mV",
        parameters={"scale": 0.01, "offset": -2.0},
    )
    return SessionConfig(
        port="test",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=100,
        protocol_mode=__import__(
            "serial_monitor.domain.enums", fromlist=["ProtocolMode"]
        ).ProtocolMode.FRAME_CSV,
        channels=[
            SignalChannelConfig(
                index=0,
                signal_type=SignalType.ECG,
                display_name="ECG",
                unit="mV",
                raw_unit="count",
                sample_rate_hz=1000,
                conversion=ConversionConfig(True, profile.profile_id),
                conversion_profile=profile,
            )
        ],
    )


def test_hdf5_preserves_raw_and_conversion_snapshot(tmp_path) -> None:
    session = build_session()
    writer = Hdf5SessionWriter(
        base_dir=tmp_path,
        session_id="session_test",
        session=session,
        chunk_size=4,
    )
    writer.open()
    writer.append_batch(
        [
            SampleFrame(1, 1000, {0: 100.0}, [100.0]),
            SampleFrame(2, 2000, {0: 200.0}, [200.0]),
        ]
    )
    writer.finalize(
        communication=LiveAcquisitionService().snapshot().communication,
        end_reason="test",
    )

    with h5py.File(tmp_path / "session_test.h5", "r") as h5:
        raw_values = np.array(h5["frames/raw_values"])[..., 0]
        np.testing.assert_array_equal(raw_values, [100.0, 200.0])
        assert int(np.asarray(h5.attrs["format_version"])) == 6
        assert "linear_snapshot" in str(h5.attrs["conversion_profiles_json"])
        assert "valores recebidos" in str(h5.attrs["raw_data_policy"])


def test_reopened_session_reproduces_conversion_from_snapshot(tmp_path) -> None:
    session = build_session()
    writer = Hdf5SessionWriter(
        base_dir=tmp_path,
        session_id="session_test",
        session=session,
        chunk_size=4,
    )
    writer.open()
    writer.append_batch([SampleFrame(1, 1000, {0: 100.0}, [100.0])])
    writer.finalize(
        communication=LiveAcquisitionService().snapshot().communication,
        end_reason="test",
    )

    loaded = SessionRepository(tmp_path).load("session_test")
    processing = ProcessingService(conversion_service=ConversionService())
    processing.configure(loaded.session)
    processed = processing.process(loaded.snapshot)

    assert loaded.session.channels[0].conversion_profile is not None
    assert loaded.session.channels[0].conversion_profile.parameters == {
        "scale": 0.01,
        "offset": -2.0,
    }
    np.testing.assert_allclose(processed.channels[0].raw_values, [100.0])
    np.testing.assert_allclose(processed.channels[0].converted_values, [-1.0])


def test_csv_export_is_explicitly_raw(tmp_path) -> None:
    session = build_session()
    writer = Hdf5SessionWriter(
        base_dir=tmp_path,
        session_id="session_test",
        session=session,
        chunk_size=4,
    )
    writer.open()
    writer.append_batch([SampleFrame(1, 1000, {0: 100.0}, [100.0])])
    writer.finalize(
        communication=LiveAcquisitionService().snapshot().communication,
        end_reason="test",
    )

    output = SessionRepository(tmp_path).export_csv("session_test")
    header = output.read_text(encoding="utf-8").splitlines()[0]

    assert "ch0_ecg_raw_count" in header
    assert "mV" not in header
