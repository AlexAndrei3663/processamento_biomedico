from __future__ import annotations

import argparse
import tempfile
import time
from pathlib import Path

try:
    import resource
except ImportError:
    resource = None

from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.recording_service import RecordingService
from serial_monitor.application.session_service import SessionService
from serial_monitor.infrastructure.serial.protocol import FrameCsvParser


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--rate", type=float, default=1100.0)
    parser.add_argument("--channels", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()

    if args.duration <= 0 or args.rate <= 0:
        raise SystemExit("--duration e --rate devem ser positivos")
    if args.channels <= 0 or args.batch_size <= 0:
        raise SystemExit("--channels e --batch-size devem ser positivos")

    signal_order = ",".join("outro" for _ in range(args.channels))
    session = SessionService().build_session(
        port="BENCHMARK",
        baudrate=115200,
        base_sample_rate_hz=round(args.rate),
        window_size=max(100, round(args.rate * 10.0)),
        signal_order_text=signal_order,
    )
    frame_parser = FrameCsvParser()
    acquisition = LiveAcquisitionService()
    acquisition.configure(session)

    temporary = None
    output_dir = args.output_dir
    if output_dir is None:
        temporary = tempfile.TemporaryDirectory()
        output_dir = Path(temporary.name)

    recorder = RecordingService(
        output_dir,
        queue_capacity=8192,
        batch_size=512,
        flush_interval_s=2.0,
    )
    recorder.start(session)

    total_frames = round(args.duration * args.rate)
    pending = []
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    maximum_lag_s = 0.0

    for sequence in range(total_frames):
        timestamp_us = round(sequence * 1_000_000.0 / args.rate)
        values = ",".join(str((sequence + index) % 1_000_000) for index in range(args.channels))
        pending.append(
            frame_parser.parse_line(
                f"FRAME,{sequence & 0xFFFFFFFF},{timestamp_us},{values}",
                session,
            ).frame
        )

        if len(pending) < args.batch_size and sequence + 1 < total_frames:
            continue

        accepted = acquisition.ingest_frames(pending)
        recorder.enqueue_frames(accepted)
        pending.clear()

        deadline = started_wall + (sequence + 1) / args.rate
        now = time.perf_counter()
        if now < deadline:
            time.sleep(deadline - now)
        else:
            maximum_lag_s = max(maximum_lag_s, now - deadline)

    acquisition_elapsed_wall = time.perf_counter() - started_wall
    communication = acquisition.snapshot().communication
    finalize_started = time.perf_counter()
    status = recorder.finalize(communication, reason="embedded_benchmark", timeout_s=120.0)
    finalize_elapsed_wall = time.perf_counter() - finalize_started
    elapsed_wall = time.perf_counter() - started_wall
    elapsed_cpu = time.process_time() - started_cpu
    max_rss_mib = None
    if resource is not None:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        max_rss_mib = float(usage.ru_maxrss) / 1024.0

    achieved_rate = (
        total_frames / acquisition_elapsed_wall
        if acquisition_elapsed_wall > 0
        else 0.0
    )
    cpu_percent_one_core = 100.0 * elapsed_cpu / elapsed_wall if elapsed_wall > 0 else 0.0
    success = (
        status.frames_written == total_frames
        and communication.invalid_frames == 0
        and communication.missing_frames == 0
        and achieved_rate >= args.rate * 0.98
    )

    print(f"estado={status.state.value}")
    print(f"frames_planejados={total_frames}")
    print(f"frames_gravados={status.frames_written}")
    print(f"tempo_aquisicao_s={acquisition_elapsed_wall:.3f}")
    print(f"tempo_finalizacao_s={finalize_elapsed_wall:.3f}")
    print(f"tempo_total_s={elapsed_wall:.3f}")
    print(f"taxa_processada_hz={achieved_rate:.3f}")
    print(f"cpu_um_nucleo_percent={cpu_percent_one_core:.3f}")
    print("rss_max_mib=indisponivel" if max_rss_mib is None else f"rss_max_mib={max_rss_mib:.3f}")
    print(f"atraso_max_ms={maximum_lag_s * 1000.0:.3f}")
    print(f"fila_max={status.queue_high_watermark}")
    print(f"frames_ausentes={communication.missing_frames}")
    print(f"frames_invalidos={communication.invalid_frames}")
    print(f"resultado={'aprovado' if success else 'reprovado'}")

    if temporary is not None:
        temporary.cleanup()
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
