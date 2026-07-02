from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List

import h5py
import numpy as np

from serial_monitor.domain.enums import ProtocolMode, SignalType
from serial_monitor.domain.models import (
    AcquisitionSnapshot,
    ChannelBufferSnapshot,
    CommunicationStats,
    SequenceDiagnostics,
    SessionConfig,
    SignalChannelConfig,
    StoredSessionData,
    StoredSessionSummary,
)
from serial_monitor.infrastructure.storage.hdf5_session_writer import Hdf5SessionWriter


class SessionRepository:
    """Consulta, abre, exporta e exclui sessões HDF5 finalizadas.

    A gravação contínua é responsabilidade de ``RecordingService``. Este repositório
    nunca salva snapshots de buffers circulares.
    """

    DATA_SUFFIX = ".h5"
    PARTIAL_SUFFIX = ".partial.h5"
    FORMAT_VERSION = Hdf5SessionWriter.FORMAT_VERSION

    def __init__(self, base_dir: str | Path = "data/sessions") -> None:
        self.base_dir = Path(base_dir)

    def list_sessions(self) -> List[StoredSessionSummary]:
        if not self.base_dir.exists():
            return []

        summaries: List[StoredSessionSummary] = []
        for data_path in self.base_dir.glob(f"*{self.DATA_SUFFIX}"):
            if data_path.name.endswith(self.PARTIAL_SUFFIX):
                continue
            try:
                summaries.append(self._summary_from_file(data_path))
            except Exception:
                continue
        return sorted(summaries, key=lambda item: item.created_at, reverse=True)

    def load(self, session_id: str) -> StoredSessionData:
        data_path = self.base_dir / f"{session_id}{self.DATA_SUFFIX}"
        if not data_path.exists():
            raise FileNotFoundError(f"Sessão não encontrada: {data_path}")

        with h5py.File(data_path, "r") as h5:
            self._validate_version(h5)
            summary = self._summary_from_open_file(h5, data_path)
            session = self._session_from_file(h5)
            active_filters = self._active_filters_from_file(h5)

            frame_count = int(h5["frames/sequence_id"].shape[0]) # pyright: ignore[reportAttributeAccessIssue]
            start = max(0, frame_count - session.window_size)
            sequence_ids = np.asarray(h5["frames/sequence_id"][start:frame_count], dtype=np.uint32) # pyright: ignore[reportIndexIssue]
            timestamps_us = np.asarray(h5["frames/timestamp_us"][start:frame_count], dtype=np.uint64) # pyright: ignore[reportIndexIssue]
            raw_values = np.asarray(h5["frames/raw_values"][start:frame_count, :], dtype=np.float64) # pyright: ignore[reportIndexIssue]

            channel_snapshots: Dict[int, ChannelBufferSnapshot] = {}
            for channel in session.channels:
                values = raw_values[:, channel.index] if raw_values.size else np.array([], dtype=float)
                if len(values):
                    x_seconds = (
                        timestamps_us.astype(np.float64) - float(timestamps_us[0])
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
        )

    def export_csv(
        self,
        session_id: str,
        output_path: str | Path | None = None,
        *,
        chunk_size: int = 4096,
    ) -> Path:
        data_path = self.base_dir / f"{session_id}{self.DATA_SUFFIX}"
        if not data_path.exists():
            raise FileNotFoundError(f"Sessão não encontrada: {data_path}")

        if output_path is None:
            output_path = self.base_dir / f"{session_id}.csv"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        chunk_size = max(1, int(chunk_size))

        with h5py.File(data_path, "r") as h5, output_path.open(
            "w", newline="", encoding="utf-8"
        ) as fp:
            self._validate_version(h5)
            session = self._session_from_file(h5)
            sequences = h5["frames/sequence_id"]
            timestamps = h5["frames/timestamp_us"]
            values = h5["frames/raw_values"]
            frame_count = int(sequences.shape[0]) # pyright: ignore[reportAttributeAccessIssue]
            if frame_count <= 0:
                raise ValueError("A sessão não possui amostras exportáveis.")

            header = ["sample_index", "sequence_id", "timestamp_us"]
            for channel in session.channels:
                unit = channel.unit.replace(" ", "_") or "value"
                header.append(f"ch{channel.index}_{channel.signal_type.value}_{unit}")

            writer = csv.writer(fp)
            writer.writerow(header)
            for start in range(0, frame_count, chunk_size):
                end = min(frame_count, start + chunk_size)
                seq_chunk = np.asarray(sequences[start:end], dtype=np.uint32) # pyright: ignore[reportIndexIssue]
                time_chunk = np.asarray(timestamps[start:end], dtype=np.uint64) # pyright: ignore[reportIndexIssue]
                value_chunk = np.asarray(values[start:end, :], dtype=np.float64) # pyright: ignore[reportIndexIssue]
                for offset in range(end - start):
                    writer.writerow(
                        [
                            start + offset,
                            int(seq_chunk[offset]),
                            int(time_chunk[offset]),
                            *(float(item) for item in value_chunk[offset, :]),
                        ]
                    )
        return output_path

    def delete(self, session_id: str) -> None:
        data_path = self.base_dir / f"{session_id}{self.DATA_SUFFIX}"
        partial_path = self.base_dir / f"{session_id}{self.PARTIAL_SUFFIX}"
        csv_path = self.base_dir / f"{session_id}.csv"

        removed = False
        for path in (data_path, partial_path, csv_path):
            if path.exists():
                path.unlink()
                removed = True
        if not removed:
            raise FileNotFoundError(f"Sessão não encontrada: {session_id}")

    def _summary_from_file(self, data_path: Path) -> StoredSessionSummary:
        with h5py.File(data_path, "r") as h5:
            self._validate_version(h5)
            return self._summary_from_open_file(h5, data_path)

    def _summary_from_open_file(
        self,
        h5: h5py.File,
        data_path: Path,
    ) -> StoredSessionSummary:
        channels = self._channels_metadata(h5)
        communication = self._communication_from_file(h5)
        frames_written = int(h5.attrs.get("frames_written", h5["frames/sequence_id"].shape[0])) # pyright: ignore[reportAttributeAccessIssue]
        labels = [
            f"ch{channel['index']}:{channel.get('display_name', channel.get('signal_type', 'sinal'))}"
            for channel in channels
        ]
        return StoredSessionSummary(
            session_id=str(h5.attrs.get("session_id", data_path.stem)),
            created_at=str(h5.attrs.get("created_at", "")),
            frames_received=frames_written,
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
            state=str(h5.attrs.get("state", "completed")),
            duration_seconds=float(h5.attrs.get("duration_seconds", 0.0)),
            end_reason=str(h5.attrs.get("end_reason", "")) or None,
        )

    def _session_from_file(self, h5: h5py.File) -> SessionConfig:
        channels = []
        for source in self._channels_metadata(h5):
            channels.append(
                SignalChannelConfig(
                    index=int(source["index"]),
                    signal_type=SignalType.from_text(str(source["signal_type"])),
                    display_name=str(source["display_name"]),
                    unit=str(source["unit"]),
                    sample_rate_hz=float(source["sample_rate_hz"]),
                    scale=float(source.get("scale", 1.0)),
                    offset=float(source.get("offset", 0.0)),
                    default_filters=list(source.get("default_filters", [])),
                )
            )

        return SessionConfig(
            port=str(h5.attrs.get("port", "stored-session")),
            baudrate=max(1, int(h5.attrs.get("baudrate", 1))),
            base_sample_rate_hz=int(h5.attrs["base_sample_rate_hz"]), # pyright: ignore[reportArgumentType]
            window_size=int(h5.attrs["window_size"]), # pyright: ignore[reportArgumentType]
            protocol_mode=ProtocolMode(str(h5.attrs.get("protocol_mode", ProtocolMode.FRAME_CSV.value))),
            channels=channels,
        )

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
        if received != self.FORMAT_VERSION:
            raise ValueError(
                f"Versão HDF5 incompatível. Esperado {self.FORMAT_VERSION}, recebido {received}."
            )
