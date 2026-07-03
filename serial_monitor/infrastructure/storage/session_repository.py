from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List

import h5py
import numpy as np

from serial_monitor import PROTOCOL_VERSION, SOFTWARE_VERSION
from serial_monitor.domain.enums import ConversionModel, ProtocolMode, SignalType
from serial_monitor.domain.models import (
    AdcConfig,
    AcquisitionSnapshot,
    ChannelBufferSnapshot,
    CommunicationStats,
    ConversionConfig,
    ConversionProfile,
    SequenceDiagnostics,
    SessionConfig,
    SessionRecoveryResult,
    SignalChannelConfig,
    StoredSessionData,
    StoredSessionSummary,
)
from serial_monitor.infrastructure.storage.hdf5_integrity import calculate_content_sha256
from serial_monitor.infrastructure.storage.hdf5_session_writer import Hdf5SessionWriter


class ExportCancelledError(RuntimeError):
    """Sinaliza cancelamento solicitado pelo usuário durante exportação."""


class SessionRepository:
    """Consulta, recupera, abre, exporta e exclui sessões HDF5."""

    DATA_SUFFIX = ".h5"
    PARTIAL_SUFFIX = ".partial.h5"
    FORMAT_VERSION = Hdf5SessionWriter.FORMAT_VERSION
    SUPPORTED_FORMAT_VERSIONS = {4, 5, 6, 7, 8}

    def __init__(self, base_dir: str | Path = "data/sessions") -> None:
        self.base_dir = Path(base_dir)

    def list_sessions(self, *, include_partial: bool = False) -> List[StoredSessionSummary]:
        if not self.base_dir.exists():
            return []

        paths = [
            path
            for path in self.base_dir.glob(f"*{self.DATA_SUFFIX}")
            if include_partial or not path.name.endswith(self.PARTIAL_SUFFIX)
        ]
        summaries: List[StoredSessionSummary] = []
        for data_path in paths:
            try:
                summaries.append(self._summary_from_file(data_path))
            except Exception as exc:
                summaries.append(self._unreadable_summary(data_path, str(exc)))
        return sorted(summaries, key=lambda item: item.created_at, reverse=True)

    def get_summary(self, session_id: str) -> StoredSessionSummary:
        path = self._resolve_session_path(session_id, allow_partial=True)
        return self._summary_from_file(path)

    def load(self, session_id: str) -> StoredSessionData:
        """Carrega a janela final da sessão para compatibilidade com a tela ao vivo."""

        path = self._resolve_session_path(session_id, allow_partial=True)
        with h5py.File(path, "r") as h5:
            self._validate_version(h5)
            session = self._session_from_file(h5)
            frame_count = self._consistent_frame_count(h5)
            start_index = max(0, frame_count - session.window_size)
        return self._load_index_range(
            session_id,
            start_index=start_index,
            end_index=frame_count,
            max_points=session.window_size,
        )

    def load_window(
        self,
        session_id: str,
        *,
        start_us: int | None = None,
        end_us: int | None = None,
        max_points: int | None = None,
    ) -> StoredSessionData:
        """Carrega apenas um intervalo temporal da sessão.

        A busca dos limites usa acesso binário ao dataset de timestamps, evitando a
        leitura integral do vetor temporal. Quando ``max_points`` é informado, somente
        índices uniformemente distribuídos são lidos do HDF5 para apresentação.
        """

        path = self._resolve_session_path(session_id, allow_partial=True)
        with h5py.File(path, "r") as h5:
            self._validate_version(h5)
            timestamps = h5["frames/timestamp_us"]
            frame_count = self._consistent_frame_count(h5)
            if frame_count <= 0:
                return self._load_index_range(
                    session_id,
                    start_index=0,
                    end_index=0,
                    max_points=max_points,
                )

            first_timestamp = int(timestamps[0])
            last_timestamp = int(timestamps[frame_count - 1])
            requested_start = first_timestamp if start_us is None else max(first_timestamp, int(start_us))
            requested_end = last_timestamp if end_us is None else min(last_timestamp, int(end_us))
            if requested_end < requested_start:
                raise ValueError("O fim do intervalo deve ser maior ou igual ao início.")

            start_index = self._lower_bound(timestamps, requested_start, frame_count)
            end_index = self._upper_bound(timestamps, requested_end, frame_count)

        return self._load_index_range(
            session_id,
            start_index=start_index,
            end_index=end_index,
            max_points=max_points,
        )

    def export_csv(
        self,
        session_id: str,
        output_path: str | Path | None = None,
        *,
        chunk_size: int = 4096,
        progress_callback: Callable[[int, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> Path:
        """Exporta toda a sessão em fluxo, com progresso e cancelamento."""

        data_path = self._resolve_session_path(session_id, allow_partial=True)
        if output_path is None:
            output_path = self.base_dir / f"{session_id}.csv"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(output_path.name + ".partial")
        chunk_size = max(1, int(chunk_size))

        if temporary_path.exists():
            temporary_path.unlink()

        try:
            with h5py.File(data_path, "r") as h5, temporary_path.open(
                "w", newline="", encoding="utf-8"
            ) as fp:
                self._validate_version(h5)
                session = self._session_from_file(h5)
                sequences = h5["frames/sequence_id"]
                timestamps = h5["frames/timestamp_us"]
                values = h5["frames/raw_values"]
                frame_count = self._consistent_frame_count(h5)
                if frame_count <= 0:
                    raise ValueError("A sessão não possui amostras exportáveis.")

                header = ["sample_index", "sequence_id", "timestamp_us"]
                for channel in session.channels:
                    unit = channel.raw_unit.replace(" ", "_") or "value"
                    header.append(
                        f"ch{channel.index}_{channel.signal_type.value}_raw_{unit}"
                    )

                writer = csv.writer(fp)
                writer.writerow(header)
                if progress_callback is not None:
                    progress_callback(0, frame_count)

                for start in range(0, frame_count, chunk_size):
                    if cancel_check is not None and cancel_check():
                        raise ExportCancelledError("Exportação CSV cancelada pelo usuário.")

                    end = min(frame_count, start + chunk_size)
                    seq_chunk = np.asarray(sequences[start:end], dtype=np.uint32)
                    time_chunk = np.asarray(timestamps[start:end], dtype=np.uint64)
                    value_chunk = np.asarray(values[start:end, :], dtype=np.float64)
                    for offset in range(end - start):
                        writer.writerow(
                            [
                                start + offset,
                                int(seq_chunk[offset]),
                                int(time_chunk[offset]),
                                *(float(item) for item in value_chunk[offset, :]),
                            ]
                        )
                    if progress_callback is not None:
                        progress_callback(end, frame_count)

            os.replace(temporary_path, output_path)
            return output_path
        except Exception:
            if temporary_path.exists():
                temporary_path.unlink()
            raise

    def verify_integrity(self, session_id: str) -> str:
        """Recalcula o SHA-256 dos datasets e retorna o estado da verificação."""

        path = self._resolve_session_path(session_id, allow_partial=True)
        with h5py.File(path, "r+") as h5:
            self._validate_version(h5)
            expected = str(h5.attrs.get("content_sha256", ""))
            if not expected:
                h5.attrs["integrity_status"] = "not_available"
                h5.flush()
                return "not_available"
            calculated = calculate_content_sha256(h5)
            status = "verified" if calculated == expected else "failed"
            h5.attrs["integrity_status"] = status
            h5.attrs["integrity_checked_at"] = datetime.now().isoformat(timespec="milliseconds")
            h5.flush()
            return status

    def finalize_incomplete_sessions(self) -> list[SessionRecoveryResult]:
        """Finaliza automaticamente arquivos ``.partial.h5`` encontrados na inicialização.

        O menor comprimento consistente entre os datasets é mantido. A sessão recebe
        estado ``completed`` e motivo ``unexpected_shutdown``. Não há fluxo de
        recuperação manual: o arquivo passa a ser uma sessão finalizada comum.
        """

        if not self.base_dir.exists():
            return []

        results: list[SessionRecoveryResult] = []
        for partial_path in sorted(self.base_dir.glob(f"*{self.PARTIAL_SUFFIX}")):
            session_id = partial_path.name[: -len(self.PARTIAL_SUFFIX)]
            results.append(self._finalize_partial_file(session_id))
        return results

    def recover_partial(self, session_id: str) -> SessionRecoveryResult:
        """Compatibilidade interna: finaliza a sessão como encerramento inesperado."""

        return self._finalize_partial_file(session_id)

    def _finalize_partial_file(self, session_id: str) -> SessionRecoveryResult:
        partial_path = self.base_dir / f"{session_id}{self.PARTIAL_SUFFIX}"
        if not partial_path.exists():
            raise FileNotFoundError(f"Sessão incompleta não encontrada: {partial_path}")
        final_path = self.base_dir / f"{session_id}{self.DATA_SUFFIX}"
        if final_path.exists():
            raise FileExistsError(f"Já existe uma sessão finalizada com o ID {session_id}.")

        with h5py.File(partial_path, "r+") as h5:
            self._validate_version(h5)
            self._validate_structure(h5)
            sequences = h5["frames/sequence_id"]
            timestamps = h5["frames/timestamp_us"]
            values = h5["frames/raw_values"]
            source_lengths = [
                int(sequences.shape[0]),
                int(timestamps.shape[0]),
                int(values.shape[0]),
            ]
            safe_count = min(source_lengths)

            sequences.resize((safe_count,))
            timestamps.resize((safe_count,))
            values.resize((safe_count, int(values.shape[1])))

            now = datetime.now()
            started_at = self._parse_datetime(str(h5.attrs.get("started_at", "")))
            digest = calculate_content_sha256(h5)
            h5.attrs["state"] = "completed"
            h5.attrs["integrity_status"] = "verified"
            h5.attrs["content_sha256"] = digest
            h5.attrs["frames_written"] = safe_count
            h5.attrs["confirmed_frames"] = safe_count
            h5.attrs["ended_at"] = now.isoformat(timespec="milliseconds")
            h5.attrs["end_reason"] = "unexpected_shutdown"
            h5.attrs["finalized_after_interruption"] = True
            h5.attrs["finalized_at_startup"] = now.isoformat(timespec="milliseconds")
            h5.attrs["software_version_recovery"] = SOFTWARE_VERSION
            h5.attrs["protocol_version"] = str(
                h5.attrs.get("protocol_version", PROTOCOL_VERSION)
            )
            h5.attrs["duration_seconds"] = (
                max(0.0, (now - started_at).total_seconds())
                if started_at is not None
                else 0.0
            )
            h5.attrs["first_timestamp_us"] = int(timestamps[0]) if safe_count else -1
            h5.attrs["last_timestamp_us"] = (
                int(timestamps[safe_count - 1]) if safe_count else -1
            )
            h5.flush()

        os.replace(partial_path, final_path)
        return SessionRecoveryResult(
            session_id=session_id,
            source_path=partial_path,
            output_path=final_path,
            frames_recovered=safe_count,
            frames_discarded=max(source_lengths) - safe_count,
            integrity_status="verified",
        )

    def delete(self, session_id: str) -> None:
        data_path = self.base_dir / f"{session_id}{self.DATA_SUFFIX}"
        partial_path = self.base_dir / f"{session_id}{self.PARTIAL_SUFFIX}"
        csv_path = self.base_dir / f"{session_id}.csv"
        csv_partial_path = self.base_dir / f"{session_id}.csv.partial"

        removed = False
        for path in (data_path, partial_path, csv_path, csv_partial_path):
            if path.exists():
                path.unlink()
                removed = True
        if not removed:
            raise FileNotFoundError(f"Sessão não encontrada: {session_id}")

    def _load_index_range(
        self,
        session_id: str,
        *,
        start_index: int,
        end_index: int,
        max_points: int | None,
    ) -> StoredSessionData:
        path = self._resolve_session_path(session_id, allow_partial=True)
        with h5py.File(path, "r") as h5:
            self._validate_version(h5)
            self._validate_structure(h5)
            summary = self._summary_from_open_file(h5, path)
            session = self._session_from_file(h5)
            active_filters = self._active_filters_from_file(h5)
            total_frames = self._consistent_frame_count(h5)
            start_index = max(0, min(int(start_index), total_frames))
            end_index = max(start_index, min(int(end_index), total_frames))
            requested_count = end_index - start_index

            decimated = False
            if max_points is not None and max_points > 0 and requested_count > max_points:
                indices = np.unique(
                    np.linspace(start_index, end_index - 1, int(max_points), dtype=np.int64)
                )
                sequence_ids = np.asarray(h5["frames/sequence_id"][indices], dtype=np.uint32)
                timestamps_us = np.asarray(h5["frames/timestamp_us"][indices], dtype=np.uint64)
                raw_values = np.asarray(h5["frames/raw_values"][indices, :], dtype=np.float64)
                decimated = True
            else:
                sequence_ids = np.asarray(
                    h5["frames/sequence_id"][start_index:end_index], dtype=np.uint32
                )
                timestamps_us = np.asarray(
                    h5["frames/timestamp_us"][start_index:end_index], dtype=np.uint64
                )
                raw_values = np.asarray(
                    h5["frames/raw_values"][start_index:end_index, :], dtype=np.float64
                )

            channel_snapshots: Dict[int, ChannelBufferSnapshot] = {}
            for channel in session.channels:
                values = raw_values[:, channel.index] if raw_values.size else np.array([], dtype=float)
                if len(values):
                    time_origin_us = (
                        summary.first_timestamp_us
                        if summary.first_timestamp_us is not None
                        else int(timestamps_us[0])
                    )
                    x_seconds = (
                        timestamps_us.astype(np.float64) - float(time_origin_us)
                    ) / 1_000_000.0
                    last_value = float(values[-1])
                    last_timestamp_us = int(timestamps_us[-1])
                else:
                    x_seconds = np.array([], dtype=float)
                    last_value = None
                    last_timestamp_us = None

                channel_snapshots[channel.index] = ChannelBufferSnapshot(
                    channel=channel,
                    sample_count=int(len(values)),
                    x_seconds=x_seconds,
                    values=np.asarray(values, dtype=float),
                    timestamps_us=timestamps_us.copy(),
                    sequence_ids=sequence_ids.copy(),
                    last_value=last_value,
                    last_timestamp_us=last_timestamp_us,
                )

            communication = self._communication_from_file(h5)
            snapshot = AcquisitionSnapshot(
                configured=True,
                running=False,
                communication=communication,
                last_sequence_id=int(sequence_ids[-1]) if len(sequence_ids) else None,
                last_timestamp_us=int(timestamps_us[-1]) if len(timestamps_us) else None,
                channels=channel_snapshots,
            )

        return StoredSessionData(
            summary=summary,
            session=session,
            snapshot=snapshot,
            active_filters=active_filters,
            loaded_start_us=int(timestamps_us[0]) if len(timestamps_us) else None,
            loaded_end_us=int(timestamps_us[-1]) if len(timestamps_us) else None,
            loaded_frames=int(len(timestamps_us)),
            total_frames=total_frames,
            decimated_for_display=decimated,
        )

    def _summary_from_file(self, data_path: Path) -> StoredSessionSummary:
        with h5py.File(data_path, "r") as h5:
            self._validate_version(h5)
            self._validate_structure(h5)
            return self._summary_from_open_file(h5, data_path)

    def _summary_from_open_file(
        self,
        h5: h5py.File,
        data_path: Path,
    ) -> StoredSessionSummary:
        channels = self._channels_metadata(h5)
        communication = self._communication_from_file(h5)
        frame_count = self._consistent_frame_count(h5)
        labels = [
            f"ch{channel['index']}:{channel.get('display_name', channel.get('signal_type', 'sinal'))}"
            for channel in channels
        ]
        first_timestamp = int(h5["frames/timestamp_us"][0]) if frame_count else None
        last_timestamp = int(h5["frames/timestamp_us"][frame_count - 1]) if frame_count else None
        duration = float(h5.attrs.get("duration_seconds", 0.0))
        if duration <= 0 and first_timestamp is not None and last_timestamp is not None:
            duration = max(0.0, (last_timestamp - first_timestamp) / 1_000_000.0)
        is_partial = data_path.name.endswith(self.PARTIAL_SUFFIX)
        try:
            file_size = int(data_path.stat().st_size)
        except OSError:
            file_size = 0

        return StoredSessionSummary(
            session_id=str(h5.attrs.get("session_id", self._session_id_from_path(data_path))),
            created_at=str(h5.attrs.get("created_at", "")),
            frames_received=frame_count,
            gap_events=communication.gap_events,
            missing_frames=communication.missing_frames,
            duplicate_frames=communication.duplicate_frames,
            out_of_order_frames=communication.out_of_order_frames,
            invalid_frames=communication.invalid_frames,
            timestamp_regressions=communication.timestamp_regressions,
            channel_count=len(channels),
            base_sample_rate_hz=int(h5.attrs.get("base_sample_rate_hz", 0)),
            channel_labels=labels,
            metadata_path=data_path,
            data_path=data_path,
            state=str(h5.attrs.get("state", "recording" if is_partial else "completed")),
            duration_seconds=duration,
            end_reason=str(h5.attrs.get("end_reason", "")) or None,
            is_partial=is_partial,
            format_version=int(h5.attrs.get("format_version", 0)),
            software_version=str(h5.attrs.get("software_version", "unknown")),
            protocol_version=str(h5.attrs.get("protocol_version", "unknown")),
            integrity_status=str(h5.attrs.get("integrity_status", "unknown")),
            content_sha256=str(h5.attrs.get("content_sha256", "")) or None,
            first_timestamp_us=first_timestamp,
            last_timestamp_us=last_timestamp,
            file_size_bytes=file_size,
        )

    def _unreadable_summary(self, data_path: Path, error: str) -> StoredSessionSummary:
        try:
            modified = datetime.fromtimestamp(data_path.stat().st_mtime).isoformat(
                timespec="milliseconds"
            )
            file_size = int(data_path.stat().st_size)
        except OSError:
            modified = ""
            file_size = 0
        is_partial = data_path.name.endswith(self.PARTIAL_SUFFIX)
        return StoredSessionSummary(
            session_id=self._session_id_from_path(data_path),
            created_at=modified,
            frames_received=0,
            gap_events=0,
            missing_frames=0,
            duplicate_frames=0,
            out_of_order_frames=0,
            invalid_frames=0,
            timestamp_regressions=0,
            channel_count=0,
            base_sample_rate_hz=0,
            channel_labels=[],
            metadata_path=data_path,
            data_path=data_path,
            state="unreadable",
            end_reason=error,
            is_partial=is_partial,
            integrity_status="unreadable",
            file_size_bytes=file_size,
        )

    def _session_from_file(self, h5: h5py.File) -> SessionConfig:
        channels = []
        for source in self._channels_metadata(h5):
            conversion_source = source.get("conversion", {})
            if not isinstance(conversion_source, dict):
                conversion_source = {}
            enabled = bool(conversion_source.get("enabled", False))
            profile_id_raw = conversion_source.get("profile_id")
            profile_id = str(profile_id_raw) if profile_id_raw else None
            profile_source = source.get("conversion_profile_snapshot")
            profile = (
                self._conversion_profile_from_dict(profile_source)
                if isinstance(profile_source, dict)
                else None
            )

            # Versões anteriores não continham conversão reproduzível.
            if int(h5.attrs.get("format_version", 0)) < 6:
                enabled = False
                profile_id = None
                profile = None

            raw_unit = str(source.get("raw_unit", source.get("unit", "count")))
            unit = str(source.get("unit", raw_unit)) if enabled else raw_unit
            channels.append(
                SignalChannelConfig(
                    index=int(source["index"]),
                    signal_type=SignalType.from_text(str(source["signal_type"])),
                    display_name=str(source["display_name"]),
                    unit=unit,
                    raw_unit=raw_unit,
                    sample_rate_hz=float(source["sample_rate_hz"]),
                    conversion=ConversionConfig(enabled=enabled, profile_id=profile_id),
                    conversion_profile=profile,
                    default_filters=list(source.get("default_filters", [])),
                )
            )

        adc = AdcConfig(
            model=str(h5.attrs.get("adc_model", "ADS1256")),
            input_mode=str(h5.attrs.get("adc_input_mode", "differential")),
            reference_voltage_v=float(
                h5.attrs.get("adc_reference_voltage_v", 2.5)
            ),
            gain=int(h5.attrs.get("adc_gain", 1)),
        )
        return SessionConfig(
            port=str(h5.attrs.get("port", "stored-session")),
            baudrate=max(1, int(h5.attrs.get("baudrate", 1))),
            base_sample_rate_hz=max(1, int(h5.attrs.get("base_sample_rate_hz", 1))),
            window_size=max(1, int(h5.attrs.get("window_size", 1))),
            protocol_mode=ProtocolMode(
                str(h5.attrs.get("protocol_mode", ProtocolMode.FRAME_CSV.value))
            ),
            channels=channels,
            adc=adc,
        )

    @staticmethod
    def _conversion_profile_from_dict(source: dict) -> ConversionProfile:
        signal_value = str(source.get("signal_type", "*"))
        signal_type = None if signal_value in {"", "*", "any"} else SignalType.from_text(signal_value)

        def optional_range(name: str) -> tuple[float, float] | None:
            value = source.get(name)
            if not isinstance(value, list) or len(value) != 2:
                return None
            return float(value[0]), float(value[1])

        profile = ConversionProfile(
            profile_id=str(source["profile_id"]),
            version=int(source.get("version", 1)),
            signal_type=signal_type,
            model=ConversionModel(str(source.get("model", "identity"))),
            input_unit=str(source.get("input_unit", "count")),
            output_unit=str(source.get("output_unit", "a.u.")),
            parameters=dict(source.get("parameters", {})),
            description=str(source.get("description", "")),
            valid_input_range=optional_range("valid_input_range"),
            valid_output_range=optional_range("valid_output_range"),
            origin=str(source.get("origin", "")),
            created_at=str(source.get("created_at", "")),
            reference_equipment=str(source.get("reference_equipment", "")),
            estimated_uncertainty=str(source.get("estimated_uncertainty", "")),
        )
        profile.validate()
        return profile

    @staticmethod
    def _channels_metadata(h5: h5py.File) -> list[dict]:
        raw = h5.attrs.get("channels_json", "[]")
        return list(json.loads(str(raw)))

    @staticmethod
    def _active_filters_from_file(h5: h5py.File) -> Dict[int, List[str]]:
        raw = h5.attrs.get("active_filters_json", "{}")
        source = json.loads(str(raw))
        return {int(index): list(filters) for index, filters in source.items()}

    @staticmethod
    def _communication_from_file(h5: h5py.File) -> CommunicationStats:
        raw = h5.attrs.get("communication_json", "{}")
        source = json.loads(str(raw)) if str(raw) else {}
        sequence = source.get("sequence", {})
        return CommunicationStats(
            valid_frames=int(source.get("valid_frames", h5.attrs.get("frames_written", 0))),
            invalid_frames=int(source.get("invalid_frames", 0)),
            checksum_errors=int(source.get("checksum_errors", 0)),
            timestamp_regressions=int(source.get("timestamp_regressions", 0)),
            sequence=SequenceDiagnostics(
                gap_events=int(sequence.get("gap_events", 0)),
                missing_items=int(sequence.get("missing_items", 0)),
                duplicate_items=int(sequence.get("duplicate_items", 0)),
                out_of_order_items=int(sequence.get("out_of_order_items", 0)),
            ),
        )

    def _validate_version(self, h5: h5py.File) -> None:
        received = int(h5.attrs.get("format_version", 0))
        if received not in self.SUPPORTED_FORMAT_VERSIONS:
            supported = ", ".join(str(item) for item in sorted(self.SUPPORTED_FORMAT_VERSIONS))
            raise ValueError(
                f"Versão HDF5 incompatível. Versões suportadas: {supported}; recebida: {received}."
            )

    @staticmethod
    def _validate_structure(h5: h5py.File) -> None:
        required = ("frames/sequence_id", "frames/timestamp_us", "frames/raw_values")
        missing = [name for name in required if name not in h5]
        if missing:
            raise ValueError("Estrutura HDF5 incompleta: " + ", ".join(missing))
        values = h5["frames/raw_values"]
        if len(values.shape) != 2:
            raise ValueError("Dataset frames/raw_values deve possuir duas dimensões.")
        channels_raw = h5.attrs.get("channels_json", "[]")
        try:
            channel_count = len(json.loads(str(channels_raw)))
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("Metadados de canais inválidos.") from exc
        if channel_count <= 0:
            raise ValueError("A sessão não possui canais definidos nos metadados.")
        if int(values.shape[1]) != channel_count:
            raise ValueError(
                "Quantidade de colunas de raw_values incompatível com os metadados de canais."
            )

    @staticmethod
    def _consistent_frame_count(h5: h5py.File) -> int:
        return min(
            int(h5["frames/sequence_id"].shape[0]),
            int(h5["frames/timestamp_us"].shape[0]),
            int(h5["frames/raw_values"].shape[0]),
        )

    def _resolve_session_path(self, session_id: str, *, allow_partial: bool) -> Path:
        final_path = self.base_dir / f"{session_id}{self.DATA_SUFFIX}"
        if final_path.exists():
            return final_path
        partial_path = self.base_dir / f"{session_id}{self.PARTIAL_SUFFIX}"
        if allow_partial and partial_path.exists():
            return partial_path
        raise FileNotFoundError(f"Sessão não encontrada: {session_id}")

    @staticmethod
    def _session_id_from_path(path: Path) -> str:
        name = path.name
        if name.endswith(SessionRepository.PARTIAL_SUFFIX):
            return name[: -len(SessionRepository.PARTIAL_SUFFIX)]
        if name.endswith(SessionRepository.DATA_SUFFIX):
            return name[: -len(SessionRepository.DATA_SUFFIX)]
        return path.stem

    @staticmethod
    def _lower_bound(dataset: h5py.Dataset, value: int, count: int) -> int:
        low, high = 0, count
        while low < high:
            mid = (low + high) // 2
            if int(dataset[mid]) < value:
                low = mid + 1
            else:
                high = mid
        return low

    @staticmethod
    def _upper_bound(dataset: h5py.Dataset, value: int, count: int) -> int:
        low, high = 0, count
        while low < high:
            mid = (low + high) // 2
            if int(dataset[mid]) <= value:
                low = mid + 1
            else:
                high = mid
        return low

    @staticmethod
    def _parse_datetime(value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
