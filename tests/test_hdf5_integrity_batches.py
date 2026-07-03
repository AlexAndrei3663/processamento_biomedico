from __future__ import annotations

from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.models import SampleFrame
from serial_monitor.infrastructure.storage.hdf5_session_writer import Hdf5SessionWriter
from serial_monitor.infrastructure.storage.session_repository import SessionRepository


def test_integrity_hash_is_independent_of_writer_batch_boundaries(tmp_path) -> None:
    session = SessionService().build_session(
        port="test",
        baudrate=115200,
        base_sample_rate_hz=500,
        window_size=20,
        signal_order_text="ecg",
    )
    writer = Hdf5SessionWriter(
        base_dir=tmp_path,
        session_id="multi_batch",
        session=session,
        chunk_size=7,
    )
    writer.open()
    for start in range(0, 50, 7):
        writer.append_batch(
            [
                SampleFrame(
                    sequence_id=seq,
                    timestamp_us=seq * 2000,
                    values_by_channel_index={0: float(seq)},
                    values_in_order=[float(seq)],
                )
                for seq in range(start, min(50, start + 7))
            ]
        )
        writer.flush()
    writer.finalize(
        communication=LiveAcquisitionService().snapshot().communication,
        end_reason="test",
    )

    repository = SessionRepository(tmp_path)
    assert repository.verify_integrity("multi_batch") == "verified"
