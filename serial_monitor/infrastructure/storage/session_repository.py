from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, cast

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


class SessionRepository:
    """Repositório de sessões em JSON + NPZ.
    """

    METADATA_SUFFIX = ".json"
    DATA_SUFFIX = ".npz"
    FORMAT_VERSION = 3

    def __init__(self, base_dir: str | Path = "data/sessions") -> None:
        self.base_dir = Path(base_dir)

    def save(
        self,
        session: SessionConfig,
        snapshot: AcquisitionSnapshot,
        active_filters: Dict[int, List[str]] | None = None,
    ) -> StoredSessionSummary:
        if not snapshot.configured:
            raise ValueError("A aquisição ainda não foi configurada.")
        if snapshot.frames_received <= 0:
            raise ValueError("Não há frames recebidos para salvar.")
        if not snapshot.channels:
            raise ValueError("Não há canais com dados para salvar.")

        self.base_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        session_id = now.strftime("session_%Y%m%d_%H%M%S_%f")[:-3]
        metadata_path = self.base_dir / f"{session_id}{self.METADATA_SUFFIX}"
        data_path = self.base_dir / f"{session_id}{self.DATA_SUFFIX}"

        metadata = self._build_metadata(
            session_id=session_id,
            created_at=now.isoformat(timespec="seconds"),
            session=session,
            snapshot=snapshot,
            active_filters=active_filters or {},
            data_filename=data_path.name,
        )

        arrays: Dict[str, np.ndarray] = {}
        for channel_index, channel_snapshot in snapshot.channels.items():
            arrays[f"ch{channel_index}_values"] = np.asarray(channel_snapshot.values, dtype=float)
            arrays[f"ch{channel_index}_timestamps_us"] = np.asarray(
                channel_snapshot.timestamps_us,
                dtype=np.uint64,
            )
            arrays[f"ch{channel_index}_sequence_ids"] = np.asarray(
                channel_snapshot.sequence_ids,
                dtype=np.uint32,
            )

        cast(Any, np.savez_compressed)(data_path, **arrays)
        metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        return self._summary_from_metadata(metadata, metadata_path)

    def list_sessions(self) -> List[StoredSessionSummary]:
        if not self.base_dir.exists():
            return []

        summaries: List[StoredSessionSummary] = []
        for metadata_path in self.base_dir.glob(f"*{self.METADATA_SUFFIX}"):
            try:
                metadata = self._read_metadata(metadata_path)
                summary = self._summary_from_metadata(metadata, metadata_path)
                if summary.data_path.exists():
                    summaries.append(summary)
            except Exception:
                continue
        return sorted(summaries, key=lambda item: item.created_at, reverse=True)

    def load(self, session_id: str) -> StoredSessionData:
        metadata_path = self.base_dir / f"{session_id}{self.METADATA_SUFFIX}"
        if not metadata_path.exists():
            raise FileNotFoundError(f"Metadados da sessão não encontrados: {metadata_path}")

        metadata = self._read_metadata(metadata_path)
        if int(metadata.get("version", 0)) != self.FORMAT_VERSION:
            raise ValueError(
                "Versão de sessão incompatível com a Etapa 12 revisada. "
                f"Esperado {self.FORMAT_VERSION}, recebido {metadata.get('version')}."
            )

        summary = self._summary_from_metadata(metadata, metadata_path)
        if not summary.data_path.exists():
            raise FileNotFoundError(f"Dados da sessão não encontrados: {summary.data_path}")

        session = self._session_from_metadata(metadata)
        active_filters = {
            int(index): list(filters)
            for index, filters in metadata.get("active_filters", {}).items()
        }

        with np.load(summary.data_path, allow_pickle=False) as data:
            channel_snapshots: Dict[int, ChannelBufferSnapshot] = {}
            for channel in session.channels:
                prefix = f"ch{channel.index}"
                values = np.asarray(data.get(f"{prefix}_values", np.array([], dtype=float)), dtype=float)
                timestamps_us = np.asarray(
                    data.get(f"{prefix}_timestamps_us", np.array([], dtype=np.uint64)),
                    dtype=np.uint64,
                )
                sequence_ids = np.asarray(
                    data.get(f"{prefix}_sequence_ids", np.array([], dtype=np.uint32)),
                    dtype=np.uint32,
                )

                lengths = {len(values), len(timestamps_us), len(sequence_ids)}
                if len(lengths) != 1:
                    raise ValueError(f"Arrays inconsistentes no canal {channel.index}.")

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
                    values=values,
                    timestamps_us=timestamps_us,
                    sequence_ids=sequence_ids,
                    last_value=last_value,
                    last_timestamp_us=last_timestamp_us,
                )

        snapshot = AcquisitionSnapshot(
            configured=True,
            running=False,
            communication=self._communication_from_metadata(metadata),
            last_sequence_id=metadata.get("last_sequence_id"),
            last_timestamp_us=metadata.get("last_timestamp_us"),
            channels=channel_snapshots,
        )
        return StoredSessionData(
            summary=summary,
            session=session,
            snapshot=snapshot,
            active_filters=active_filters,
        )

    def export_csv(self, session_id: str, output_path: str | Path | None = None) -> Path:
        """Exporta o snapshot salvo no formato tabular provisório da Etapa 12."""

        stored = self.load(session_id)
        if output_path is None:
            output_path = self.base_dir / f"{session_id}.csv"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        channels = [stored.snapshot.channels[index] for index in sorted(stored.snapshot.channels)]
        max_len = max((channel.sample_count for channel in channels), default=0)
        if max_len <= 0:
            raise ValueError("A sessão não possui amostras exportáveis.")

        header = ["sample_index"]
        for channel_snapshot in channels:
            channel = channel_snapshot.channel
            signal = channel.signal_type.value
            unit = channel.unit.replace(" ", "_") or "value"
            prefix = f"ch{channel.index}_{signal}"
            header.extend(
                [
                    f"{prefix}_timestamp_us",
                    f"{prefix}_sequence_id",
                    f"{prefix}_{unit}",
                ]
            )

        with output_path.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.writer(fp)
            writer.writerow(header)
            for row_index in range(max_len):
                row: list[object] = [row_index]
                for channel_snapshot in channels:
                    if row_index < channel_snapshot.sample_count:
                        row.extend(
                            [
                                int(channel_snapshot.timestamps_us[row_index]),
                                int(channel_snapshot.sequence_ids[row_index]),
                                float(channel_snapshot.values[row_index]),
                            ]
                        )
                    else:
                        row.extend(["", "", ""])
                writer.writerow(row)
        return output_path

    def delete(self, session_id: str) -> None:
        metadata_path = self.base_dir / f"{session_id}{self.METADATA_SUFFIX}"
        data_path: Path | None = None
        if metadata_path.exists():
            try:
                metadata = self._read_metadata(metadata_path)
                data_path = self._summary_from_metadata(metadata, metadata_path).data_path
            except Exception:
                data_path = metadata_path.with_suffix(self.DATA_SUFFIX)
        else:
            raise FileNotFoundError(f"Sessão não encontrada: {session_id}")

        paths = [metadata_path]
        if data_path is not None:
            paths.append(data_path)
        paths.append(self.base_dir / f"{session_id}.csv")

        removed = False
        for path in paths:
            if path.exists():
                path.unlink()
                removed = True
        if not removed:
            raise FileNotFoundError(f"Sessão não encontrada: {session_id}")

    def _build_metadata(
        self,
        *,
        session_id: str,
        created_at: str,
        session: SessionConfig,
        snapshot: AcquisitionSnapshot,
        active_filters: Dict[int, List[str]],
        data_filename: str,
    ) -> dict:
        communication = snapshot.communication
        return {
            "version": self.FORMAT_VERSION,
            "session_id": session_id,
            "created_at": created_at,
            "data_filename": data_filename,
            "protocol_contract": {
                "sequence_id": "uint32; incremento por ciclo multicanal; wrap em 2^32; reinício no boot",
                "timestamp_us": "uint64; microssegundos desde o boot; primeira conversão do ciclo",
            },
            "communication": self._communication_to_dict(communication),
            "last_sequence_id": snapshot.last_sequence_id,
            "last_timestamp_us": snapshot.last_timestamp_us,
            "active_filters": {str(index): list(filters) for index, filters in active_filters.items()},
            "session": {
                "port": session.port,
                "baudrate": session.baudrate,
                "base_sample_rate_hz": session.base_sample_rate_hz,
                "window_size": session.window_size,
                "protocol_mode": session.protocol_mode.value,
                "channels": [
                    {
                        "index": channel.index,
                        "signal_type": channel.signal_type.value,
                        "display_name": channel.display_name,
                        "unit": channel.unit,
                        "sample_rate_hz": channel.sample_rate_hz,
                        "scale": channel.scale,
                        "offset": channel.offset,
                        "default_filters": list(channel.default_filters),
                        "sample_count": snapshot.channels[channel.index].sample_count
                        if channel.index in snapshot.channels
                        else 0,
                    }
                    for channel in session.channels
                ],
            },
        }

    @staticmethod
    def _communication_to_dict(stats: CommunicationStats) -> dict:
        def sequence_dict(sequence: SequenceDiagnostics) -> dict:
            return {
                "gap_events": sequence.gap_events,
                "missing_items": sequence.missing_items,
                "duplicate_items": sequence.duplicate_items,
                "out_of_order_items": sequence.out_of_order_items,
            }

        return {
            "valid_frames": stats.valid_frames,
            "invalid_frames": stats.invalid_frames,
            "checksum_errors": stats.checksum_errors,
            "timestamp_regressions": stats.timestamp_regressions,
            "sequence": sequence_dict(stats.sequence),
        }

    @staticmethod
    def _communication_from_metadata(metadata: dict) -> CommunicationStats:
        communication = metadata.get("communication", {})

        def parse_sequence(name: str) -> SequenceDiagnostics:
            source = communication.get(name, {})
            return SequenceDiagnostics(
                gap_events=int(source.get("gap_events", 0)),
                missing_items=int(source.get("missing_items", 0)),
                duplicate_items=int(source.get("duplicate_items", 0)),
                out_of_order_items=int(source.get("out_of_order_items", 0)),
            )

        return CommunicationStats(
            valid_frames=int(communication.get("valid_frames", 0)),
            invalid_frames=int(communication.get("invalid_frames", 0)),
            checksum_errors=int(communication.get("checksum_errors", 0)),
            timestamp_regressions=int(communication.get("timestamp_regressions", 0)),
            sequence=parse_sequence("sequence"),
        )

    @staticmethod
    def _read_metadata(metadata_path: Path) -> dict:
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    def _summary_from_metadata(self, metadata: dict, metadata_path: Path) -> StoredSessionSummary:
        session_metadata = metadata.get("session", {})
        channels = session_metadata.get("channels", [])
        data_filename = metadata.get("data_filename", metadata_path.with_suffix(self.DATA_SUFFIX).name)
        labels = [
            f"ch{channel.get('index')}:{channel.get('display_name', channel.get('signal_type', 'sinal'))}"
            for channel in channels
        ]
        stats = self._communication_from_metadata(metadata)
        return StoredSessionSummary(
            session_id=str(metadata.get("session_id", metadata_path.stem)),
            created_at=str(metadata.get("created_at", "")),
            frames_received=stats.valid_frames,
            gap_events=stats.gap_events,
            missing_frames=stats.missing_frames,
            duplicate_frames=stats.duplicate_frames,
            out_of_order_frames=stats.out_of_order_frames,
            invalid_frames=stats.invalid_frames,
            timestamp_regressions=stats.timestamp_regressions,
            channel_count=len(channels),
            base_sample_rate_hz=int(session_metadata.get("base_sample_rate_hz", 0)),
            channel_labels=labels,
            metadata_path=metadata_path,
            data_path=metadata_path.parent / data_filename,
        )

    @staticmethod
    def _session_from_metadata(metadata: dict) -> SessionConfig:
        session_metadata = metadata["session"]
        channels = []
        for channel_metadata in session_metadata.get("channels", []):
            channels.append(
                SignalChannelConfig(
                    index=int(channel_metadata["index"]),
                    signal_type=SignalType.from_text(str(channel_metadata["signal_type"])),
                    display_name=str(channel_metadata["display_name"]),
                    unit=str(channel_metadata["unit"]),
                    sample_rate_hz=float(channel_metadata["sample_rate_hz"]),
                    scale=float(channel_metadata.get("scale", 1.0)),
                    offset=float(channel_metadata.get("offset", 0.0)),
                    default_filters=list(channel_metadata.get("default_filters", [])),
                )
            )

        return SessionConfig(
            port=str(session_metadata.get("port", "stored-session")),
            baudrate=int(session_metadata.get("baudrate", 1)),
            base_sample_rate_hz=int(session_metadata["base_sample_rate_hz"]),
            window_size=int(session_metadata["window_size"]),
            protocol_mode=ProtocolMode(
                str(session_metadata.get("protocol_mode", ProtocolMode.FRAME_CSV.value))
            ),
            channels=channels,
        )
