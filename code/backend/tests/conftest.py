import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def client(tmp_path_factory, monkeypatch_session):
    db_path = tmp_path_factory.mktemp("db") / "test.duckdb"
    monkeypatch_session.setenv("DUCKDB_PATH", str(db_path))
    monkeypatch_session.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch_session.setenv("OPENAI_API_KEY", "")
    from app import config

    monkeypatch_session.setattr(config, "DUCKDB_PATH", db_path)
    monkeypatch_session.setattr(config, "LLM_ENABLED", False)
    # config computes these at import, so clearing the environment above is not enough on its own:
    # a key left in a developer's shell has already frozen LLM_PROVIDER to "openai" by the time this
    # fixture runs, and the agent tests then make real API calls. They fail locally and
    # non-deterministically while CI stays green, because CI has no key.
    monkeypatch_session.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch_session.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch_session.setattr(config, "LLM_PROVIDER", "offline")
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def monkeypatch_session():
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()
