"""DuckDB access. One process-wide connection, guarded by a lock.

Tables are created by the modules that own them (see hive.SCHEMA_SQL).
"""

import shutil
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import duckdb

from . import config, storage

_lock = threading.RLock()
_conn: duckdb.DuckDBPyConnection | None = None


def init() -> None:
    """Open the DuckDB file (restoring it from S3 first when configured) and lock down external access."""
    global _conn
    if _conn is not None:
        return
    path = config.DUCKDB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        storage.restore(path)
    _conn = duckdb.connect(str(path))
    # The app never reads files or URLs through SQL; keep it that way.
    _conn.execute("SET enable_external_access = false")


def close() -> None:
    """Close the connection; called on app shutdown."""
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


@contextmanager
def cursor() -> Iterator[duckdb.DuckDBPyConnection]:
    """Yield a cursor under the global lock, for reads."""
    assert _conn is not None, "db.init() not called"
    with _lock:
        cur = _conn.cursor()
        try:
            yield cur
        finally:
            cur.close()


@contextmanager
def write() -> Iterator[duckdb.DuckDBPyConnection]:
    """Cursor for writes; snapshots the file to S3 afterwards when configured."""
    with cursor() as cur:
        yield cur
        if config.DUCKDB_S3_URI:
            cur.execute("CHECKPOINT")
            copy = config.DUCKDB_PATH.with_suffix(".snapshot")
            shutil.copyfile(config.DUCKDB_PATH, copy)
            storage.snapshot(copy)


def rows(cur: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Return the cursor's result as a list of dicts keyed by column name."""
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=False)) for r in cur.fetchall()]


def new_id() -> str:
    """Return a short random id for bookings, reviews and events."""
    return uuid.uuid4().hex[:12]


def now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(UTC)
