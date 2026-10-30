import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client(tmp_path_factory, monkeypatch_session):
    db_path = tmp_path_factory.mktemp("db") / "test.duckdb"
    monkeypatch_session.setenv("DUCKDB_PATH", str(db_path))
    monkeypatch_session.setenv("ANTHROPIC_API_KEY", "")
    from app import config

    monkeypatch_session.setattr(config, "DUCKDB_PATH", db_path)
    monkeypatch_session.setattr(config, "LLM_ENABLED", False)
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def monkeypatch_session():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()
