"""Hashes para detectar duplicados exactos: por tamaño, luego hash parcial, luego hash completo.

Solo se calculan para archivos que comparten tamaño con otro. Nunca para archivos solo en la nube.
"""

import hashlib
import os
import sqlite3
import threading

from orden_pc import winfs

MIN_SIZE = 4096  # ponytail: duplicados de menos de 4 KB no liberan espacio que valga la pena
PARTIAL = 64 * 1024
CHUNK = 1024 * 1024

NOT_CLOUD = "(cloud IS NULL OR cloud != 'solo_nube')"


def partial_hash(path: str, size: int) -> str:
    h = hashlib.blake2b(digest_size=16)
    h.update(size.to_bytes(8, "little"))
    with open(path, "rb") as f:
        h.update(f.read(PARTIAL))
        if size > 2 * PARTIAL:
            f.seek(-PARTIAL, os.SEEK_END)
            h.update(f.read(PARTIAL))
    return h.hexdigest()


def full_hash(path: str, stop: threading.Event) -> str | None:
    h = hashlib.blake2b(digest_size=32)
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK):
            if stop.is_set():
                return None
            h.update(chunk)
    return h.hexdigest()


def hash_candidates(conn: sqlite3.Connection, progress, stop: threading.Event) -> None:
    from orden_pc.scanner import Cancelled

    same_size = f"""
        SELECT id, path, size FROM entries
        WHERE is_dir = 0 AND size >= :min AND {NOT_CLOUD} AND hash_partial IS NULL AND size IN (
            SELECT size FROM entries WHERE is_dir = 0 AND size >= :min AND {NOT_CLOUD}
            GROUP BY size HAVING count(*) > 1)
    """
    for row in conn.execute(same_size, {"min": MIN_SIZE}).fetchall():
        if stop.is_set():
            raise Cancelled
        progress.current = row["path"]
        if not winfs.safe_to_read(row["path"]):
            continue
        try:
            digest = partial_hash(row["path"], row["size"])
        except OSError:
            continue
        conn.execute("UPDATE entries SET hash_partial = ? WHERE id = ?", (digest, row["id"]))
        progress.hashed += 1
    conn.commit()

    same_partial = f"""
        SELECT id, path FROM entries
        WHERE is_dir = 0 AND {NOT_CLOUD} AND hash_full IS NULL AND hash_partial IN (
            SELECT hash_partial FROM entries WHERE is_dir = 0 AND hash_partial IS NOT NULL AND {NOT_CLOUD}
            GROUP BY hash_partial HAVING count(*) > 1)
    """
    for row in conn.execute(same_partial).fetchall():
        if stop.is_set():
            raise Cancelled
        progress.current = row["path"]
        if not winfs.safe_to_read(row["path"]):
            continue
        try:
            digest = full_hash(row["path"], stop)
        except OSError:
            continue
        if digest is None:
            raise Cancelled
        conn.execute("UPDATE entries SET hash_full = ? WHERE id = ?", (digest, row["id"]))
        conn.commit()
        progress.hashed += 1
