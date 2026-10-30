"""DuckDB access. One process-wide connection, guarded by a lock.

Tables are created by the modules that own them (see hive.SCHEMA_SQL).
"""

import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import duckdb

from . import config, storage

_lock = threading.RLock()
_conn: duckdb.DuckDBPyConnection | None = None


def init() -> None:
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
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


@contextmanager
def cursor() -> Iterator[duckdb.DuckDBPyConnection]:
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
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now() -> datetime:
    return datetime.now(timezone.utc)
