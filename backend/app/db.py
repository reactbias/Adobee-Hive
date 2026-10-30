"""DuckDB access. One process-wide connection, guarded by a lock.

Tables
- jobs:          open positions (S1 job posting)
- candidates:    one row per parsed CV (S2), with funnel stage
- experiences:   work history rows per candidate
- cv_documents:  raw CV text, kept apart so the NL query never exposes it
- profiles:      applicant-owned personas (JSON document per applicant)
"""

import json
import shutil
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

import duckdb

from . import config, storage

STAGES = ["received", "screened", "shortlisted", "interview", "offer", "rejected"]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    id VARCHAR PRIMARY KEY,
    title VARCHAR NOT NULL,
    location VARCHAR,
    description VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS candidates (
    id VARCHAR PRIMARY KEY,
    job_id VARCHAR,
    full_name VARCHAR,
    email VARCHAR,
    location VARCHAR,
    headline VARCHAR,
    current_role VARCHAR,
    current_company VARCHAR,
    years_experience DOUBLE,
    seniority VARCHAR,
    skills VARCHAR[],
    languages VARCHAR[],
    highest_education VARCHAR,
    summary VARCHAR,
    remote_ok BOOLEAN,
    stage VARCHAR DEFAULT 'received',
    source VARCHAR,
    created_at TIMESTAMP DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS experiences (
    candidate_id VARCHAR,
    company VARCHAR,
    role VARCHAR,
    start_year INTEGER,
    end_year INTEGER,
    description VARCHAR
);
CREATE TABLE IF NOT EXISTS cv_documents (
    candidate_id VARCHAR PRIMARY KEY,
    filename VARCHAR,
    raw_text VARCHAR
);
CREATE TABLE IF NOT EXISTS profiles (
    id VARCHAR PRIMARY KEY,
    data JSON,
    updated_at TIMESTAMP DEFAULT current_timestamp
);
"""

# The part of the schema the NL-query LLM is allowed to see. No raw CV text, no profiles.
QUERYABLE_TABLES = ["jobs", "candidates", "experiences"]
PRIVATE_TABLES = ["cv_documents", "profiles"]

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
    _conn.execute(SCHEMA_SQL)
    # The NL query runs model-written SQL on this connection: no file or network access.
    _conn.execute("SET enable_external_access = false")
    _conn.execute("SET lock_configuration = true")


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


def schema_description() -> str:
    """Human/LLM-readable schema of the queryable tables."""
    lines = []
    with cursor() as cur:
        for table in QUERYABLE_TABLES:
            cols = cur.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [table],
            ).fetchall()
            lines.append(f"TABLE {table} (")
            lines.extend(f"  {name} {dtype}," for name, dtype in cols)
            lines.append(")")
    lines.append(f"candidates.stage is one of: {', '.join(STAGES)}")
    lines.append("experiences.candidate_id references candidates.id; candidates.job_id references jobs.id")
    lines.append("experiences.end_year is NULL for a current position")
    return "\n".join(lines)


# ---------- candidates ----------

def insert_candidate(parsed: dict[str, Any], *, job_id: str | None, raw_text: str, filename: str, source: str) -> str:
    cid = new_id()
    with write() as cur:
        cur.execute(
            """INSERT INTO candidates (id, job_id, full_name, email, location, headline, current_role,
                current_company, years_experience, seniority, skills, languages, highest_education,
                summary, remote_ok, stage, source, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'received', ?, ?)""",
            [
                cid, job_id, parsed.get("full_name"), parsed.get("email"), parsed.get("location"),
                parsed.get("headline"), parsed.get("current_role"), parsed.get("current_company"),
                parsed.get("years_experience"), parsed.get("seniority"), parsed.get("skills") or [],
                parsed.get("languages") or [], parsed.get("highest_education"), parsed.get("summary"),
                parsed.get("remote_ok"), source, now(),
            ],
        )
        for exp in parsed.get("experiences") or []:
            cur.execute(
                "INSERT INTO experiences VALUES (?, ?, ?, ?, ?, ?)",
                [cid, exp.get("company"), exp.get("role"), exp.get("start_year"), exp.get("end_year"), exp.get("description")],
            )
        cur.execute("INSERT INTO cv_documents VALUES (?, ?, ?)", [cid, filename, raw_text])
    return cid


def list_candidates(job_id: str | None = None, stage: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT * FROM candidates WHERE 1=1"
    params: list[Any] = []
    if job_id:
        sql += " AND job_id = ?"
        params.append(job_id)
    if stage:
        sql += " AND stage = ?"
        params.append(stage)
    sql += " ORDER BY created_at DESC"
    with cursor() as cur:
        return rows(cur.execute(sql, params))


def get_candidate(cid: str) -> dict[str, Any] | None:
    with cursor() as cur:
        found = rows(cur.execute("SELECT * FROM candidates WHERE id = ?", [cid]))
        if not found:
            return None
        cand = found[0]
        cand["experiences"] = rows(
            cur.execute(
                "SELECT company, role, start_year, end_year, description FROM experiences "
                "WHERE candidate_id = ? ORDER BY start_year DESC NULLS LAST",
                [cid],
            )
        )
        return cand


def set_stage(cid: str, stage: str) -> None:
    with write() as cur:
        cur.execute("UPDATE candidates SET stage = ? WHERE id = ?", [stage, cid])


def funnel(job_id: str | None = None) -> list[dict[str, Any]]:
    sql = "SELECT stage, count(*) AS count FROM candidates"
    params: list[Any] = []
    if job_id:
        sql += " WHERE job_id = ?"
        params.append(job_id)
    sql += " GROUP BY stage"
    with cursor() as cur:
        counts = dict(cur.execute(sql, params).fetchall())
    return [{"stage": s, "count": counts.get(s, 0)} for s in STAGES]


# ---------- jobs ----------

def list_jobs() -> list[dict[str, Any]]:
    with cursor() as cur:
        return rows(cur.execute("SELECT * FROM jobs ORDER BY created_at"))


def get_job(job_id: str) -> dict[str, Any] | None:
    with cursor() as cur:
        found = rows(cur.execute("SELECT * FROM jobs WHERE id = ?", [job_id]))
    return found[0] if found else None


def upsert_job(job: dict[str, Any]) -> None:
    with write() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO jobs (id, title, location, description, created_at) VALUES (?, ?, ?, ?, ?)",
            [job["id"], job["title"], job.get("location"), job.get("description"), now()],
        )


# ---------- profiles ----------

def get_profile(pid: str) -> dict[str, Any] | None:
    with cursor() as cur:
        found = cur.execute("SELECT data FROM profiles WHERE id = ?", [pid]).fetchone()
    return json.loads(found[0]) if found else None


def save_profile(pid: str, data: dict[str, Any]) -> None:
    with write() as cur:
        cur.execute(
            "INSERT OR REPLACE INTO profiles (id, data, updated_at) VALUES (?, ?, ?)",
            [pid, json.dumps(data), now()],
        )


def count(table: str) -> int:
    assert table in QUERYABLE_TABLES + PRIVATE_TABLES
    with cursor() as cur:
        return cur.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
