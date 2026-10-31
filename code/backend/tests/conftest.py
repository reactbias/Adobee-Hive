import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client(tmp_path_factory, monkeypatch_session):
    db_path = tmp_path_factory.mktemp("db") / "test.duckdb"
    monkeypatch_session.setenv("DUCKDB_PATH", str(db_path))
    # No vendor key reaches the suite, whatever the developer's shell exports. Both are cleared,
    # not only Claude's: a machine with OPENAI_API_KEY in its profile was quietly making the
    # second opinion call OpenAI for real, which is slow, costs money and is not what the test
    # claims to check. Tests that want a vendor patch it themselves.
    monkeypatch_session.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch_session.setenv("OPENAI_API_KEY", "")
    from app import config

    monkeypatch_session.setattr(config, "DUCKDB_PATH", db_path)
    monkeypatch_session.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch_session.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch_session.setattr(config, "LLM_PROVIDER", "offline")
    monkeypatch_session.setattr(config, "LLM_ENABLED", False)
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def monkeypatch_session():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()
