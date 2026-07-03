from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from time import perf_counter

from serial_monitor.application.recording_service import RecordingService
from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.models import CommunicationStats, SampleFrame


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark sintético da gravação HDF5")
    parser.add_argument("--frames", type=int, default=100_000)
    parser.add_argument("--channels", type=int, default=3)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    if args.frames <= 0 or args.channels <= 0:
        raise SystemExit("--frames e --channels devem ser positivos")

    signal_order = ",".join("outro" for _ in range(args.channels))
    session = SessionService().build_session(
        port="BENCHMARK",
        baudrate=921600,
        base_sample_rate_hz=1000,
        window_size=5000,
        signal_order_text=signal_order,
    )

    temporary = None
    output_dir = args.output_dir
    if output_dir is None:
        temporary = tempfile.TemporaryDirectory()
        output_dir = Path(temporary.name)

    recorder = RecordingService(
        output_dir,
        queue_capacity=max(8192, args.frames + 1),
        batch_size=1024,
        flush_interval_s=0.25,
    )
    recorder.start(session)

    started = perf_counter()
    for sequence in range(args.frames):
        values = [float(sequence + channel) for channel in range(args.channels)]
        recorder.enqueue_frame(
            SampleFrame(
                sequence_id=sequence & 0xFFFFFFFF,
                timestamp_us=1_000_000 + sequence * 1000,
                values_by_channel_index=dict(enumerate(values)),
                values_in_order=values,
            )
        )

    status = recorder.finalize(
        CommunicationStats(valid_frames=args.frames),
        reason="benchmark",
        timeout_s=120.0,
    )
    elapsed = perf_counter() - started
    rate = status.frames_written / elapsed if elapsed > 0 else 0.0

    print(f"Estado: {status.state.value}")
    print(f"Frames: {status.frames_written}")
    print(f"Tempo: {elapsed:.3f} s")
    print(f"Taxa média: {rate:.1f} frames/s")
    print(f"Arquivo: {status.output_path}")
    print(f"Tamanho: {status.file_size_bytes} bytes")

    if temporary is not None:
        temporary.cleanup()
    return 0 if status.state.value == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
