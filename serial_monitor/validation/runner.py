from __future__ import annotations

import csv
import math
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np

from serial_monitor.application.conversion_service import ConversionService
from serial_monitor.application.live_acquisition_service import LiveAcquisitionService
from serial_monitor.application.operational_monitor import OperationalMonitor
from serial_monitor.application.recording_service import RecordingService
from serial_monitor.application.session_service import SessionService
from serial_monitor.domain.enums import RecordingState
from serial_monitor.domain.models import SessionConfig, SystemResourceSnapshot
from serial_monitor.infrastructure.storage.conversion_profile_repository import (
    ConversionProfileRepository,
)
from serial_monitor.infrastructure.storage.session_repository import SessionRepository
from serial_monitor.processing.filter_pipeline import ProcessingService
from serial_monitor.validation.models import (
    ResourcePeaks,
    TimingMetrics,
    ValidationCheck,
    ValidationCycleSpec,
    ValidationReport,
)
from serial_monitor.validation.synthetic_signals import SyntheticFrameGenerator


@dataclass(slots=True)
class _ResourceAccumulator:
    peak_cpu: float | None = None
    peak_memory: float | None = None
    peak_temperature: float | None = None
    minimum_disk_free: int | None = None

    def add(self, snapshot: SystemResourceSnapshot) -> None:
        self.peak_cpu = self._max_optional(self.peak_cpu, snapshot.cpu_percent)
        self.peak_memory = self._max_optional(self.peak_memory, snapshot.memory_percent)
        self.peak_temperature = self._max_optional(
            self.peak_temperature, snapshot.temperature_c
        )
        if snapshot.disk_free_bytes > 0:
            self.minimum_disk_free = (
                snapshot.disk_free_bytes
                if self.minimum_disk_free is None
                else min(self.minimum_disk_free, snapshot.disk_free_bytes)
            )

    def snapshot(self) -> ResourcePeaks:
        return ResourcePeaks(
            cpu_percent=self.peak_cpu,
            memory_percent=self.peak_memory,
            temperature_c=self.peak_temperature,
            minimum_disk_free_bytes=self.minimum_disk_free,
        )

    @staticmethod
    def _max_optional(current: float | None, value: float | None) -> float | None:
        if value is None:
            return current
        return value if current is None else max(current, value)


class ValidationRunner:
    """Executa o ciclo sintético completo e gera relatório auditável.

    O fluxo exercitado é: gerar -> adquirir -> gravar -> reabrir -> converter ->
    filtrar -> calcular espectro -> exportar -> verificar integridade.
    """

    def __init__(
        self,
        *,
        output_dir: str | Path,
        conversion_profiles_path: str | Path = "config/conversion_profiles.json",
        queue_capacity: int = 8192,
        batch_size: int = 256,
        flush_interval_s: float = 0.25,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.sessions_dir = self.output_dir / "sessions"
        self.reports_dir = self.output_dir / "reports"
        self.csv_dir = self.output_dir / "csv"
        self.conversion_profiles_path = Path(conversion_profiles_path)
        self.queue_capacity = max(128, int(queue_capacity))
        self.batch_size = max(1, int(batch_size))
        self.flush_interval_s = max(0.05, float(flush_interval_s))

    def run(
        self,
        cycle: ValidationCycleSpec,
        *,
        duration_seconds: float,
        real_time: bool = False,
        export_csv: bool = True,
        seed: int = 2026,
    ) -> ValidationReport:
        if duration_seconds <= 0:
            raise ValueError("A duração deve ser maior que zero.")

        started = datetime.now()
        requested_frames = max(
            2, int(round(duration_seconds * cycle.base_sample_rate_hz))
        )
        session = self._build_session(cycle)
        acquisition = LiveAcquisitionService()
        processing = ProcessingService(conversion_service=ConversionService())
        repository = SessionRepository(self.sessions_dir)
        recorder = RecordingService(
            self.sessions_dir,
            queue_capacity=self.queue_capacity,
            batch_size=self.batch_size,
            flush_interval_s=self.flush_interval_s,
            minimum_free_disk_bytes=0,
        )
        resource_monitor = OperationalMonitor(self.sessions_dir)
        resources = _ResourceAccumulator()

        acquisition.configure(session)
        acquisition.start()
        processing.configure(session)
        for channel_index, filters in cycle.filters_by_channel.items():
            for filter_id in filters:
                processing.set_filter_enabled(channel_index, filter_id, True)

        status = recorder.start(
            session,
            active_filters=processing.enabled_filters_snapshot(),
            communication_baseline=acquisition.snapshot().communication,
        )
        session_id = status.session_id
        generated_frames = 0
        accepted_frames = 0
        generator = SyntheticFrameGenerator(session, seed=seed)
        next_deadline = time.monotonic()
        sample_resources_every = max(1, cycle.base_sample_rate_hz // 2)

        try:
            for frame in generator.frames(requested_frames):
                generated_frames += 1
                if acquisition.ingest_frame(frame):
                    accepted_frames += 1
                    recorder.enqueue_frame(frame)

                if generated_frames % sample_resources_every == 0:
                    resources.add(resource_monitor.sample())

                if real_time:
                    next_deadline += 1.0 / cycle.base_sample_rate_hz
                    delay = next_deadline - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)

            resources.add(resource_monitor.sample())
            final_status = recorder.finalize(
                acquisition.snapshot().communication,
                reason="validation",
                timeout_s=max(15.0, duration_seconds + 5.0 if real_time else 15.0),
            )
        except Exception:
            if recorder.is_active:
                recorder.fail(
                    "Falha durante a validação sintética.",
                    acquisition.snapshot().communication,
                )
                recorder.finalize(acquisition.snapshot().communication)
            raise
        finally:
            acquisition.stop()

        if final_status.state != RecordingState.COMPLETED:
            raise RuntimeError(
                f"A gravação de validação terminou em {final_status.state.value}: "
                f"{final_status.error_message or 'sem detalhe'}"
            )
        assert session_id is not None

        summary = repository.get_summary(session_id)
        integrity_status = repository.verify_integrity(session_id)
        stored = repository.load(session_id)

        reopened_processing = ProcessingService(conversion_service=ConversionService())
        reopened_processing.configure(stored.session)
        reopened_processing.set_enabled_filters(stored.active_filters)
        processed = reopened_processing.process(stored.snapshot)
        processing_channels_checked = self._validate_processed_snapshot(processed)

        csv_path: Path | None = None
        exported_rows: int | None = None
        if export_csv:
            self.csv_dir.mkdir(parents=True, exist_ok=True)
            csv_path = repository.export_csv(
                session_id,
                self.csv_dir / f"{session_id}.csv",
            )
            exported_rows = self._count_csv_rows(csv_path)

        timing = self._calculate_timing_metrics(
            summary.data_path,
            nominal_sample_rate_hz=cycle.base_sample_rate_hz,
        )
        communication = acquisition.snapshot().communication
        queue_usage_percent = (
            100.0 * final_status.queue_high_watermark / final_status.queue_capacity
            if final_status.queue_capacity > 0
            else 0.0
        )
        rate_error_percent = (
            abs(timing.effective_sample_rate_hz - cycle.base_sample_rate_hz)
            / cycle.base_sample_rate_hz
            * 100.0
            if timing.effective_sample_rate_hz is not None
            else math.inf
        )

        checks = [
            ValidationCheck(
                "aquisição integral",
                accepted_frames == requested_frames,
                f"aceitos={accepted_frames}; esperados={requested_frames}",
            ),
            ValidationCheck(
                "persistência integral",
                summary.frames_received == accepted_frames
                and final_status.frames_written == accepted_frames,
                (
                    f"HDF5={summary.frames_received}; gravador={final_status.frames_written}; "
                    f"aceitos={accepted_frames}"
                ),
            ),
            ValidationCheck(
                "integridade HDF5",
                integrity_status == "verified",
                f"estado={integrity_status}",
            ),
            ValidationCheck(
                "exportação CSV",
                (not export_csv) or exported_rows == accepted_frames,
                (
                    "não executada"
                    if not export_csv
                    else f"linhas={exported_rows}; esperadas={accepted_frames}"
                ),
            ),
            ValidationCheck(
                "conversão, filtragem e espectro",
                processing_channels_checked == session.channel_count,
                (
                    f"canais verificados={processing_channels_checked}; "
                    f"esperados={session.channel_count}"
                ),
            ),
            ValidationCheck(
                "taxa efetiva",
                rate_error_percent <= cycle.max_sample_rate_error_percent,
                (
                    f"erro={rate_error_percent:.6f}%; limite="
                    f"{cycle.max_sample_rate_error_percent:.3f}%"
                ),
            ),
            ValidationCheck(
                "frames ausentes",
                communication.missing_frames <= cycle.max_missing_frames,
                (
                    f"ausentes={communication.missing_frames}; limite="
                    f"{cycle.max_missing_frames}"
                ),
            ),
            ValidationCheck(
                "frames inválidos",
                communication.invalid_frames <= cycle.max_invalid_frames,
                (
                    f"inválidos={communication.invalid_frames}; limite="
                    f"{cycle.max_invalid_frames}"
                ),
            ),
            ValidationCheck(
                "ocupação da fila",
                queue_usage_percent <= cycle.max_queue_usage_percent,
                (
                    f"máximo={queue_usage_percent:.2f}%; limite="
                    f"{cycle.max_queue_usage_percent:.2f}%"
                ),
            ),
            ValidationCheck(
                "monotonicidade temporal",
                timing.non_positive_intervals == 0,
                f"intervalos não positivos={timing.non_positive_intervals}",
            ),
        ]

        ended = datetime.now()
        report = ValidationReport(
            cycle_id=cycle.cycle_id,
            cycle_label=cycle.label,
            started_at=started.isoformat(timespec="seconds"),
            ended_at=ended.isoformat(timespec="seconds"),
            requested_frames=requested_frames,
            generated_frames=generated_frames,
            accepted_frames=accepted_frames,
            recorded_frames=summary.frames_received,
            exported_rows=exported_rows,
            integrity_status=integrity_status,
            session_id=session_id,
            session_path=str(summary.data_path),
            csv_path=str(csv_path) if csv_path else None,
            communication={
                "valid_frames": communication.valid_frames,
                "gap_events": communication.gap_events,
                "missing_frames": communication.missing_frames,
                "duplicate_frames": communication.duplicate_frames,
                "out_of_order_frames": communication.out_of_order_frames,
                "invalid_frames": communication.invalid_frames,
                "checksum_errors": communication.checksum_errors,
                "timestamp_regressions": communication.timestamp_regressions,
            },
            timing=timing,
            resources=resources.snapshot(),
            queue_high_watermark=final_status.queue_high_watermark,
            queue_capacity=final_status.queue_capacity,
            processing_channels_checked=processing_channels_checked,
            checks=checks,
            notes=[
                "O ensaio sintético valida o pipeline de software; não substitui os ensaios com gerador de funções e hardware.",
                "O protocolo FRAME_CSV atual não possui CRC; checksum_errors permanece como infraestrutura reservada.",
                "Os filtros são aplicados por janela com processamento não causal, portanto a nomenclatura correta é tempo quase real.",
            ],
        )
        report.save(self.reports_dir)
        return report

    def _build_session(self, cycle: ValidationCycleSpec) -> SessionConfig:
        profile_repository = ConversionProfileRepository(
            self.conversion_profiles_path
        )
        service = SessionService(profile_repository)
        conversions = [
            {
                "channel_index": index,
                "enabled": index in cycle.conversion_profile_by_channel,
                "profile_id": cycle.conversion_profile_by_channel.get(index),
            }
            for index in range(len(cycle.signals))
        ]
        return service.build_session(
            port="SYNTHETIC",
            baudrate=115200,
            base_sample_rate_hz=cycle.base_sample_rate_hz,
            window_size=cycle.window_size,
            signal_order_text=",".join(signal.value for signal in cycle.signals),
            channel_conversions=conversions,
        )

    @staticmethod
    def _validate_processed_snapshot(snapshot: object) -> int:
        channels = getattr(snapshot, "channels", {})
        checked = 0
        for channel in channels.values():
            arrays = (
                channel.raw_values,
                channel.converted_values,
                channel.processed_values,
            )
            if any(array.shape != channel.raw_values.shape for array in arrays):
                continue
            if any(array.size and not np.all(np.isfinite(array)) for array in arrays):
                continue
            spectra = (
                channel.raw_spectrum,
                channel.converted_spectrum,
                channel.processed_spectrum,
            )
            if any(
                spectrum.frequencies_hz.size != spectrum.magnitudes.size
                for spectrum in spectra
            ):
                continue
            checked += 1
        return checked

    @staticmethod
    def _count_csv_rows(path: Path) -> int:
        with path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            return sum(1 for _ in reader)

    @staticmethod
    def _calculate_timing_metrics(
        path: Path,
        *,
        nominal_sample_rate_hz: float,
        chunk_size: int = 65_536,
    ) -> TimingMetrics:
        with h5py.File(path, "r") as h5:
            dataset = h5["frames/timestamp_us"]
            frame_count = len(dataset)
            if frame_count == 0:
                return TimingMetrics()

            first = int(dataset[0])
            last = int(dataset[frame_count - 1])
            interval_count = 0
            interval_sum = 0.0
            interval_square_sum = 0.0
            maximum_jitter = 0.0
            non_positive = 0
            previous: int | None = None
            nominal_interval = 1_000_000.0 / nominal_sample_rate_hz

            for start in range(0, frame_count, chunk_size):
                values = np.asarray(
                    dataset[start : min(frame_count, start + chunk_size)],
                    dtype=np.int64,
                )
                if values.size == 0:
                    continue
                if previous is not None:
                    values = np.concatenate(
                        (np.asarray([previous], dtype=np.int64), values)
                    )
                deltas = np.diff(values).astype(np.float64)
                if deltas.size:
                    interval_count += int(deltas.size)
                    interval_sum += float(np.sum(deltas))
                    interval_square_sum += float(np.sum(np.square(deltas)))
                    maximum_jitter = max(
                        maximum_jitter,
                        float(np.max(np.abs(deltas - nominal_interval))),
                    )
                    non_positive += int(np.count_nonzero(deltas <= 0))
                previous = int(values[-1])

            mean_interval = (
                interval_sum / interval_count if interval_count else None
            )
            variance = (
                max(
                    0.0,
                    interval_square_sum / interval_count
                    - float(mean_interval) ** 2,
                )
                if interval_count and mean_interval is not None
                else None
            )
            std_interval = math.sqrt(variance) if variance is not None else None
            effective_rate = (
                (frame_count - 1) * 1_000_000.0 / (last - first)
                if frame_count > 1 and last > first
                else None
            )
            return TimingMetrics(
                frame_count=frame_count,
                first_timestamp_us=first,
                last_timestamp_us=last,
                effective_sample_rate_hz=effective_rate,
                mean_interval_us=mean_interval,
                interval_std_us=std_interval,
                maximum_jitter_us=maximum_jitter if interval_count else None,
                non_positive_intervals=non_positive,
            )
