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


@pytest.fixture(scope="session")
def seed_vaults():
    """tools/seed_vaults.py loaded as a module: it is a script, and its `build_card` is how a folder becomes a Card."""
    import importlib.util
    import sys
    from pathlib import Path

    if "seed_vaults" in sys.modules:
        return sys.modules["seed_vaults"]
    spec = importlib.util.spec_from_file_location(
        "seed_vaults", Path(__file__).resolve().parents[1] / "tools" / "seed_vaults.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_vaults"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fresh_hub(client, tmp_path, monkeypatch):
    """An empty database for one test, so it can publish a whole corpus without changing what other tests see.

    The `client` database is shared by the whole session, and a test that publishes eighteen people into it
    changes every later search that happens to ask for a person. This swaps the connection for a throwaway file
    (signing keys live in the database, so it is self-contained) and puts the shared one back afterwards.
    """
    from app import (
        activity,
        audit,
        blocklist,
        config,
        connections,
        db,
        folder_keys,
        folders,
        hive,
        peers,
        registration,
        removals,
        services,
        waiting,
    )

    saved = config.DUCKDB_PATH
    db.close()
    monkeypatch.setattr(config, "DUCKDB_PATH", tmp_path / "fresh.duckdb")
    db.init()
    for module in (
        hive,
        waiting,
        activity,
        blocklist,
        folders,
        folder_keys,
        connections,
        registration,
        audit,
        removals,
        peers,
        services,
    ):
        module.init()
    folders.reset()
    yield
    folders.reset()
    db.close()
    monkeypatch.setattr(config, "DUCKDB_PATH", saved)
    db.init()
