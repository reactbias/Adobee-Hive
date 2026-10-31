"""Optional Postgres snapshot of the DuckDB file, so data survives redeploys.

Free hosting disks are ephemeral. With DATABASE_URL set we restore the file from Postgres on boot and save a fresh
copy after every write: one row, latest version wins. A background thread saves, and coalesces bursts of writes
into one upload. Good enough for a single-instance demo. Without DATABASE_URL nothing here runs.
"""

import logging
import threading
from pathlib import Path

from . import config

log = logging.getLogger(__name__)

_SCHEMA = "CREATE TABLE IF NOT EXISTS hive_snapshot (id INT PRIMARY KEY, data BYTEA NOT NULL, saved_at TIMESTAMPTZ)"

_cond = threading.Condition()
_pending: bytes | None = None
_busy = False
_worker: threading.Thread | None = None
# Set when the boot restore failed: the process then runs on the seed and must never overwrite the real snapshot.
_disabled = False


def enabled() -> bool:
    """Return whether snapshots are on: DATABASE_URL is set and the boot restore did not fail."""
    return bool(config.DATABASE_URL) and not _disabled


def _connect():  # psycopg is imported lazily: local runs without DATABASE_URL never load it
    import psycopg

    return psycopg.connect(config.DATABASE_URL, connect_timeout=10)


def load() -> bytes | None:
    """Return the last saved DuckDB file from Postgres, or None if there is none yet."""
    with _connect() as conn:
        conn.execute(_SCHEMA)
        row = conn.execute("SELECT data FROM hive_snapshot WHERE id = 1").fetchone()
    return bytes(row[0]) if row else None


def save(data: bytes) -> None:
    """Store the DuckDB file in Postgres, replacing the previous snapshot."""
    with _connect() as conn:
        conn.execute(_SCHEMA)
        conn.execute(
            "INSERT INTO hive_snapshot (id, data, saved_at) VALUES (1, %s, now()) "
            "ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, saved_at = EXCLUDED.saved_at",
            [data],
        )


def restore(path: Path) -> None:
    """Write the last snapshot to `path` before the database opens; no-op without DATABASE_URL.

    If Postgres cannot be reached we log it, start from the seed, and switch snapshots off for this process.
    """
    global _disabled
    if not enabled():
        return
    try:
        data = load()
    except Exception:
        log.exception("Could not restore from Postgres; running on seed data, snapshots off until next deploy")
        _disabled = True
        return
    if data:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        log.info("Restored the Hive from Postgres (%d bytes)", len(data))
    else:
        log.info("No snapshot in Postgres yet, starting fresh")


def _run() -> None:
    global _pending, _busy
    while True:
        with _cond:
            while _pending is None:
                _cond.wait()
            data, _pending, _busy = _pending, None, True
        try:
            save(data)
        except Exception:  # never break a request because the backup failed
            log.exception("Postgres snapshot failed")
        finally:
            with _cond:
                _busy = False
                _cond.notify_all()


def snapshot(data: bytes) -> None:
    """Queue `data` for saving in the background; a newer snapshot replaces one not yet saved."""
    global _pending, _worker
    if not enabled():
        return
    with _cond:
        _pending = data
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_run, name="hive-snapshot", daemon=True)
            _worker.start()
        _cond.notify_all()


def flush(timeout: float = 15.0) -> None:
    """Wait until the queued snapshot is saved; called on shutdown so the last write is kept."""
    with _cond:
        _cond.wait_for(lambda: _pending is None and not _busy, timeout=timeout)
