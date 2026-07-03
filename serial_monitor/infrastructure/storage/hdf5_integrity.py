from __future__ import annotations

import hashlib
from typing import Protocol

import h5py
import numpy as np


HASH_LAYOUT_V2 = "sha256-dataset-digests-v1"


class HashLike(Protocol):
    def update(self, data: bytes) -> None: ...
    def digest(self) -> bytes: ...
    def hexdigest(self) -> str: ...


def update_content_hash(
    hasher: HashLike,
    sequence_ids: np.ndarray,
    timestamps_us: np.ndarray,
    raw_values: np.ndarray,
) -> None:
    """Layout legado: intercala os três datasets por lote de escrita."""

    hasher.update(np.asarray(sequence_ids, dtype="<u4").tobytes(order="C"))
    hasher.update(np.asarray(timestamps_us, dtype="<u8").tobytes(order="C"))
    hasher.update(np.asarray(raw_values, dtype="<f8").tobytes(order="C"))


def update_dataset_hashes(
    sequence_hasher: HashLike,
    timestamp_hasher: HashLike,
    values_hasher: HashLike,
    sequence_ids: np.ndarray,
    timestamps_us: np.ndarray,
    raw_values: np.ndarray,
) -> None:
    """Atualiza hashes independentes, tornando o resultado imune ao lote usado."""

    sequence_hasher.update(np.asarray(sequence_ids, dtype="<u4").tobytes(order="C"))
    timestamp_hasher.update(np.asarray(timestamps_us, dtype="<u8").tobytes(order="C"))
    values_hasher.update(np.asarray(raw_values, dtype="<f8").tobytes(order="C"))


def finalize_dataset_hashes(
    sequence_hasher: HashLike,
    timestamp_hasher: HashLike,
    values_hasher: HashLike,
) -> str:
    """Combina os hashes dos datasets em um SHA-256 canônico."""

    final = hashlib.sha256()
    final.update(b"sequence_id\0")
    final.update(sequence_hasher.digest())
    final.update(b"timestamp_us\0")
    final.update(timestamp_hasher.digest())
    final.update(b"raw_values\0")
    final.update(values_hasher.digest())
    return final.hexdigest()


def calculate_content_sha256(h5: h5py.File, *, chunk_size: int = 8192) -> str:
    """Calcula SHA-256 dos datasets sem carregar a sessão inteira.

    Arquivos novos usam hashes independentes por dataset. Arquivos antigos, sem
    ``content_hash_layout``, mantêm o algoritmo legado para compatibilidade.
    """

    sequences = h5["frames/sequence_id"]
    timestamps = h5["frames/timestamp_us"]
    values = h5["frames/raw_values"]
    frame_count = min(int(sequences.shape[0]), int(timestamps.shape[0]), int(values.shape[0]))
    chunk_size = max(1, int(chunk_size))

    if str(h5.attrs.get("content_hash_layout", "")) == HASH_LAYOUT_V2:
        sequence_hasher = hashlib.sha256()
        timestamp_hasher = hashlib.sha256()
        values_hasher = hashlib.sha256()
        for start in range(0, frame_count, chunk_size):
            end = min(frame_count, start + chunk_size)
            update_dataset_hashes(
                sequence_hasher,
                timestamp_hasher,
                values_hasher,
                np.asarray(sequences[start:end], dtype=np.uint32),
                np.asarray(timestamps[start:end], dtype=np.uint64),
                np.asarray(values[start:end, :], dtype=np.float64),
            )
        return finalize_dataset_hashes(
            sequence_hasher, timestamp_hasher, values_hasher
        )

    hasher = hashlib.sha256()
    for start in range(0, frame_count, chunk_size):
        end = min(frame_count, start + chunk_size)
        update_content_hash(
            hasher,
            np.asarray(sequences[start:end], dtype=np.uint32),
            np.asarray(timestamps[start:end], dtype=np.uint64),
            np.asarray(values[start:end, :], dtype=np.float64),
        )
    return hasher.hexdigest()
