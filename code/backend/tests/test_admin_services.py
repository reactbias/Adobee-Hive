"""Optional services and their keys, set from the admin panel instead of from a redeploy.

Two promises are under test. A key goes in and never comes out — no endpoint returns one, no error
message carries one, `/api/health` and the settings form do not leak one. And with no key set at
all, everything still works, because that is how this hub is meant to be able to run.
"""

from __future__ import annotations

import pytest

from app import config, db, services

TOKEN = "s3cret-for-tests"
ADMIN = {"X-Admin-Token": TOKEN}
KEY = "sk-test-abcdefghijklmnop1234"


@pytest.fixture
def admin(monkeypatch):
    """An administered hub with no vendor keys in its environment."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    monkeypatch.setattr(config, "LLM_PROVIDER", "offline")
    monkeypatch.setattr(config, "LLM_ENABLED", False)


@pytest.fixture(autouse=True)
def no_keys(client):
    """No stored key before or after: a key left behind would turn the demo's offline mode off."""
    services.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_service_keys")
        cur.execute("DELETE FROM hub_admin_log")
    yield
    with db.write() as cur:
        cur.execute("DELETE FROM hub_service_keys")


def _services(client) -> dict:
    return {s["name"]: s for s in client.get("/api/admin/services", headers=ADMIN).json()["services"]}


# ---------------------------------------------------------------- with nothing configured


def test_every_service_says_what_it_is_for_and_what_happens_without_it(client, admin):
    rows = _services(client)

    assert set(rows) == {"openai", "anthropic"}
    for row in rows.values():
        assert row["purpose"] and row["without"], "an optional service has to say what it costs to leave off"
        assert row["configured"] is False and row["source"] == services.NONE
        assert row["working"] is None, "untested is not the same as broken"
        assert "in the clear" in row["storage_warning"], "do not claim a protection we did not build"


def test_the_hub_runs_with_no_key_at_all(client, admin):
    """The existing promise, restated as a test here because this module could quietly break it."""
    assert services.provider() == "offline"
    assert services.enabled() is False
    assert client.get("/api/health").json()["llm"] == "mock"


# ---------------------------------------------------------------- setting one


def test_a_key_can_be_set_and_is_used_at_once(client, admin):
    res = client.post("/api/admin/services/openai", json={"secret": KEY}, headers=ADMIN)

    assert res.status_code == 200
    assert services.key_for("openai") == KEY, "the next call has to pick it up without a restart"
    assert services.provider() == "openai" and services.enabled() is True


def test_a_stored_key_is_never_returned_by_anything(client, admin):
    """The whole rule: write-only. Presence, a fingerprint and four characters, and nothing else."""
    client.post("/api/admin/services/openai", json={"secret": KEY}, headers=ADMIN)

    for path in ("/api/admin/services", "/api/admin/settings", "/api/health", "/api/admin/overview"):
        body = client.get(path, headers=ADMIN).text
        assert KEY not in body, f"{path} leaked the key"
        assert KEY[4:] not in body, f"{path} leaked most of the key"

    row = _services(client)["openai"]
    assert row["stored"] is True and row["configured"] is True and row["source"] == services.STORED
    assert row["last_four"] == KEY[-4:]
    assert row["fingerprint"] == services.fingerprint(KEY) and len(row["fingerprint"]) == 12
    assert "secret" not in row


def test_the_ledger_records_the_change_and_not_the_key(client, admin):
    client.post("/api/admin/services/openai", json={"secret": KEY}, headers=ADMIN)

    out = client.get("/api/admin/audit", headers=ADMIN)
    assert KEY not in out.text and services.fingerprint(KEY) not in out.text
    row = next(r for r in out.json()["entries"] if r["action"] == "service.set")
    assert row["subject"] == "openai" and row["credential"] in ("static token", "session")


def test_an_empty_key_is_refused_rather_than_stored_as_nothing(client, admin):
    assert client.post("/api/admin/services/openai", json={"secret": "   "}, headers=ADMIN).status_code == 400
    assert services.key_for("openai") == ""


def test_an_unknown_service_is_a_bad_request(client, admin):
    res = client.post("/api/admin/services/nothing-here", json={"secret": KEY}, headers=ADMIN)
    assert res.status_code == 400 and "unknown service" in res.json()["detail"]


# ---------------------------------------------------------------- clearing one


def test_clearing_a_key_returns_the_hub_to_its_environment(client, admin, monkeypatch):
    """ "Clear" has to mean something exact: the stored key goes, the deployment's own key comes back."""
    client.post("/api/admin/services/openai", json={"secret": KEY}, headers=ADMIN)
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-from-the-environment")

    assert services.key_for("openai") == KEY, "a stored key wins over the environment"
    assert client.delete("/api/admin/services/openai", headers=ADMIN).status_code == 200

    assert services.key_for("openai") == "sk-from-the-environment"
    assert _services(client)["openai"]["source"] == services.ENVIRONMENT


def test_clearing_the_last_key_turns_the_service_off_without_breaking_the_hub(client, admin):
    client.post("/api/admin/services/openai", json={"secret": KEY}, headers=ADMIN)
    client.delete("/api/admin/services/openai", headers=ADMIN)

    assert services.key_for("openai") == ""
    assert services.provider() == "offline" and services.enabled() is False
    assert client.get("/api/hive/cards").status_code == 200, "the hub itself does not depend on a key"


# ---------------------------------------------------------------- testing one


def test_the_test_button_reports_a_working_key(client, admin, monkeypatch):
    client.post("/api/admin/services/openai", json={"secret": KEY}, headers=ADMIN)
    monkeypatch.setitem(services.PROBES, "openai", lambda secret: "ok")

    out = client.post("/api/admin/services/openai/check", headers=ADMIN).json()

    assert out["working"] is True and out["checked_at"]
    assert _services(client)["openai"]["working"] is True


def test_a_failing_test_is_an_answer_and_never_carries_the_key(client, admin, monkeypatch):
    """A vendor that echoes a bad key back in its error must not put it in our database."""
    client.post("/api/admin/services/openai", json={"secret": KEY}, headers=ADMIN)

    def angry(secret: str) -> str:
        raise RuntimeError(f"401 Incorrect API key provided: {secret}")

    monkeypatch.setitem(services.PROBES, "openai", angry)
    out = client.post("/api/admin/services/openai/check", headers=ADMIN)

    assert out.status_code == 200, "a key that does not work is an answer, not a server error"
    assert out.json()["working"] is False
    assert KEY not in out.text and "[key]" in out.json()["last_error"]
    assert KEY not in client.get("/api/admin/services", headers=ADMIN).text


def test_replacing_a_key_forgets_what_was_known_about_the_old_one(client, admin, monkeypatch):
    client.post("/api/admin/services/openai", json={"secret": KEY}, headers=ADMIN)
    monkeypatch.setitem(services.PROBES, "openai", lambda secret: "ok")
    client.post("/api/admin/services/openai/check", headers=ADMIN)
    assert _services(client)["openai"]["working"] is True

    client.post("/api/admin/services/openai", json={"secret": "sk-a-different-key-9999"}, headers=ADMIN)
    assert _services(client)["openai"]["working"] is None, "that verdict belonged to the old key"


def test_testing_a_service_with_no_key_is_a_bad_request(client, admin):
    res = client.post("/api/admin/services/openai/check", headers=ADMIN)
    assert res.status_code == 400 and "no key" in res.json()["detail"]


# ---------------------------------------------------------------- the door


READS = ["/api/admin/services"]
WRITES = [
    ("post", "/api/admin/services/openai", {"secret": KEY}),
    ("delete", "/api/admin/services/openai", None),
    ("post", "/api/admin/services/openai/check", None),
]


@pytest.mark.parametrize("path", READS)
def test_reading_the_services_needs_the_admin_token(client, admin, path):
    assert client.get(path).status_code == 403
    assert client.get(path, headers={"X-Admin-Token": "wrong"}).status_code == 403


def _write(client, method: str, path: str, body: dict | None, headers: dict | None = None):
    """One write, whichever verb it uses. `delete` takes no json body in the test client."""
    kwargs: dict = {"headers": headers} if headers else {}
    if body is not None:
        kwargs["json"] = body
    return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize("method,path,body", WRITES)
def test_every_key_change_needs_the_admin_token(client, admin, method, path, body):
    assert _write(client, method, path, body).status_code == 403
    assert _write(client, method, path, body, {"X-Admin-Token": "wrong"}).status_code == 403
    assert services.key_for("openai") == "", "a refused write changed something"


@pytest.mark.parametrize("method,path,body", WRITES)
def test_setting_a_key_fails_closed_when_this_hub_has_no_credential(client, monkeypatch, method, path, body):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    assert _write(client, method, path, body).status_code == 503
