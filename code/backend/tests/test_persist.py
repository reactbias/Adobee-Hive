"""Data survives a redeploy: with DATABASE_URL set, the DuckDB file is kept as a snapshot in Postgres."""

import os
import threading

import pytest

from app import config, db, storage


@pytest.fixture
def store(monkeypatch):
    """A fake Postgres: one snapshot slot in memory. Nothing leaves the test."""
    state: dict[str, bytes | None] = {"data": None}
    saved = threading.Event()

    def save(data: bytes) -> None:
        state["data"] = data
        saved.set()

    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://fake")
    monkeypatch.setattr(storage, "_disabled", False)
    monkeypatch.setattr(storage, "load", lambda: state["data"])
    monkeypatch.setattr(storage, "save", save)
    state["saved"] = saved  # type: ignore[assignment]
    yield state
    storage.flush()


def test_off_without_database_url(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "DATABASE_URL", "")
    assert not storage.enabled()
    storage.restore(tmp_path / "x.duckdb")
    assert not (tmp_path / "x.duckdb").exists()


def test_restore_writes_the_last_snapshot(store, tmp_path):
    store["data"] = b"duckdb bytes"
    path = tmp_path / "abh.duckdb"
    storage.restore(path)
    assert path.read_bytes() == b"duckdb bytes"


def test_restore_without_snapshot_starts_fresh(store, tmp_path):
    path = tmp_path / "abh.duckdb"
    storage.restore(path)
    assert not path.exists()
    assert storage.enabled()


def test_unreachable_database_never_overwrites_the_snapshot(store, monkeypatch, tmp_path):
    """If Postgres is down at boot we run on the seed, and must not replace the real data with it later."""

    def down() -> bytes:
        raise OSError("connection refused")

    monkeypatch.setattr(storage, "load", down)
    storage.restore(tmp_path / "abh.duckdb")
    assert not storage.enabled()
    storage.snapshot(b"seed only")
    storage.flush()
    assert store["data"] is None


def test_snapshots_coalesce_to_the_latest(store):
    for i in range(20):
        storage.snapshot(f"v{i}".encode())
    storage.flush()
    assert store["data"] == b"v19"


def test_every_write_is_snapshotted(client, store):
    store["saved"].clear()
    with db.write() as cur:
        cur.execute("SELECT 1")
    assert store["saved"].wait(5)
    storage.flush()
    assert store["data"] == config.DUCKDB_PATH.read_bytes()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="needs a Postgres; CI provides one")
def test_round_trip_through_real_postgres(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    storage.save(b"first")
    storage.save(b"\x00second\xff")
    assert storage.load() == b"\x00second\xff"
