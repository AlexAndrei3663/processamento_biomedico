from __future__ import annotations

import json
from pathlib import Path

import h5py

from serial_monitor.domain.enums import ProtocolMode, SignalType
from serial_monitor.domain.models import (
    AdcConfig,
    CommunicationStats,
    SampleFrame,
    SessionConfig,
    SignalChannelConfig,
)
from serial_monitor.infrastructure.storage.hdf5_session_writer import Hdf5SessionWriter
from serial_monitor.infrastructure.storage.session_repository import SessionRepository


def _session() -> SessionConfig:
    channel = SignalChannelConfig(
        index=0,
        signal_type=SignalType.ECG,
        display_name="ECG 1",
        unit="count",
        raw_unit="count",
        sample_rate_hz=1000.0,
        default_filters=["highpass", "lowpass"],
    )
    return SessionConfig(
        port="/dev/ttyACM0",
        baudrate=115200,
        base_sample_rate_hz=1000,
        window_size=1000,
        protocol_mode=ProtocolMode.FRAME_CSV,
        channels=[channel],
        adc=AdcConfig(reference_voltage_v=2.5, gain=1),
    )


def _write_session(tmp_path: Path) -> Path:
    writer = Hdf5SessionWriter(
        base_dir=tmp_path,
        session_id="session_test",
        session=_session(),
        active_filters={0: ["highpass", "lowpass"]},
        source_metadata={
            "firmware_version": "future-placeholder",
            "firmware_commit": "unknown",
            "board": "blackpill-f411",
            "transport": "usb-cdc-csv",
        },
        chunk_size=8,
    )
    writer.open()
    writer.append_batch(
        [
            SampleFrame(
                sequence_id=1,
                timestamp_us=1000,
                values_by_channel_index={0: 123.0},
                values_in_order=[123.0],
            )
        ]
    )
    return writer.finalize(
        communication=CommunicationStats(valid_frames=1),
        end_reason="test",
    )


def test_hdf5_contains_only_raw_datasets_and_acquisition_metadata(
    tmp_path: Path,
) -> None:
    path = _write_session(tmp_path)
    with h5py.File(path, "r") as h5:
        assert set(h5["frames"].keys()) == {
            "sequence_id",
            "timestamp_us",
            "raw_values",
        }
        assert "active_filters_json" not in h5.attrs
        assert int(h5.attrs["metadata_schema_version"]) == 3
        assert str(h5.attrs["storage_policy"]) == "raw_samples_only"
        assert not bool(h5.attrs["processing_state_persisted"])

        channels = json.loads(str(h5.attrs["channels_json"]))
        assert "default_filters" not in channels[0]

        source = json.loads(str(h5.attrs["source_metadata_json"]))
        assert source["board"] == "blackpill-f411"
        assert source["firmware_version"] == "future-placeholder"


def test_repository_ignores_legacy_filters_and_reads_source_metadata(
    tmp_path: Path,
) -> None:
    path = _write_session(tmp_path)
    with h5py.File(path, "r+") as h5:
        h5.attrs["active_filters_json"] = json.dumps(
            {"0": ["notch", "lowpass"]}
        )
        channels = json.loads(str(h5.attrs["channels_json"]))
        channels[0]["default_filters"] = ["notch"]
        h5.attrs["channels_json"] = json.dumps(channels)

    stored = SessionRepository(tmp_path).load_window(
        "session_test",
        max_points=100,
    )
    assert stored.active_filters == {}
    assert stored.session.channels[0].default_filters == []
    assert stored.source_metadata["board"] == "blackpill-f411"


def test_invalid_source_metadata_is_rejected(tmp_path: Path) -> None:
    try:
        Hdf5SessionWriter(
            base_dir=tmp_path,
            session_id="invalid_metadata",
            session=_session(),
            source_metadata={"invalid": object()},
        )
    except ValueError as exc:
        assert "serializáveis em JSON" in str(exc)
    else:
        raise AssertionError("Metadado não serializável deveria ser rejeitado.")


def test_controller_does_not_save_or_restore_filter_state() -> None:
    source = Path("serial_monitor/app/bootstrap.py").read_text(encoding="utf-8")
    assert (
        "active_filters=self.processing_service.enabled_filters_snapshot()"
        not in source
    )
    assert "set_enabled_filters(stored.active_filters)" not in source
    assert "self.processing_service.set_enabled_filters({})" in source
