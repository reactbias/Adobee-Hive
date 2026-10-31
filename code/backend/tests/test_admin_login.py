"""Signing in to the hub's administration: a password, a short-lived session, and a hard limit on guessing.

A password endpoint with no limit is a brute-force oracle, so most of this file is about the limit rather
than about the happy path.
"""

import logging
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app import config, guard

PASSWORD = "a-passphrase-only-this-test-knows"
BLOCK = {"kind": "hub", "subject": "login-test.example", "reason": "testing the admin door"}


def _req(host: str = "10.0.0.1") -> SimpleNamespace:
    return SimpleNamespace(client=SimpleNamespace(host=host), headers={})


@pytest.fixture(autouse=True)
def fresh_limiter():
    """The limiter is a module-level global, so every test here starts with an empty attempt window."""
    before = guard.admin_logins.per_client, guard.admin_logins.total
    guard.admin_logins.hits.clear()
    yield
    guard.admin_logins.hits.clear()
    guard.admin_logins.per_client, guard.admin_logins.total = before


@pytest.fixture
def password(monkeypatch):
    """A hub with a password configured and no static token, which is how a browser operator arrives."""
    monkeypatch.setattr(config, "ADMIN_PASSWORD", PASSWORD)
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    return PASSWORD


def _login(client, secret: str):
    return client.post("/api/admin/login", json={"password": secret})


def test_the_right_password_opens_a_session_that_can_write(client, password):
    out = _login(client, password)
    assert out.status_code == 200
    body = out.json()
    assert body["expires_in"] > 0 and body["token"]

    wrote = client.post("/api/admin/blocklist", json=BLOCK, headers={"X-Admin-Token": body["token"]})
    assert wrote.status_code == 200, "a session token is enough to write, so a browser can administer the hub"


def test_a_wrong_password_is_refused(client, password):
    out = _login(client, "not-the-passphrase")
    assert out.status_code == 403
    assert "token" not in out.json(), "a refusal hands out nothing"


def test_a_session_token_from_a_wrong_password_cannot_be_forged(client, password):
    """The token is signed, so inventing one that merely looks right does not open the door."""
    forged = "v1.99999999999.0000000000000000000000000000000000000000000000000000000000000000"
    assert client.post("/api/admin/blocklist", json=BLOCK, headers={"X-Admin-Token": forged}).status_code == 403


def test_the_limiter_locks_out_after_the_configured_number_of_attempts(client, password):
    tries = guard.admin_logins.per_client
    for _ in range(tries):
        assert _login(client, "guess").status_code == 403, "each wrong guess is refused, not rate-limited yet"

    locked = _login(client, "guess")
    assert locked.status_code == 429, f"{tries} wrong guesses from one client is as far as it gets"


def test_a_lockout_holds_even_for_the_right_password(client, password):
    """Otherwise the limit is advisory: an attacker who got there first would still be told when it hit."""
    for _ in range(guard.admin_logins.per_client + 1):
        _login(client, "guess")
    assert _login(client, password).status_code == 429


def test_a_locked_out_response_says_when_to_try_again(client, password):
    for _ in range(guard.admin_logins.per_client + 1):
        locked = _login(client, "guess")

    assert locked.status_code == 429
    assert int(locked.headers["Retry-After"]) > 0, "a machine reads the header"
    assert any(c.isdigit() for c in locked.json()["detail"]), "a person reads the sentence"


def test_the_login_limit_is_global_as_well_as_per_client(client, password):
    """One fresh IP per attempt defeats a per-client limit, so the whole backend has a cap too."""
    guard.admin_logins.per_client = 99
    guard.admin_logins.total = 2

    assert _login(client, "guess").status_code == 403
    assert _login(client, "guess").status_code == 403
    assert _login(client, "guess").status_code == 429, "the backend's own budget for guesses is spent"


def test_a_correct_password_clears_that_client_s_attempts(client, password):
    """A person who mistypes twice and then gets it right should not be left one try from a lockout."""
    for _ in range(guard.admin_logins.per_client - 1):
        _login(client, "guess")
    assert _login(client, password).status_code == 200

    for _ in range(guard.admin_logins.per_client):
        assert _login(client, "guess").status_code == 403


def test_an_expired_session_is_refused(client, password):
    stale = guard.mint_admin_session(password, ttl_s=-1)
    assert client.post("/api/admin/blocklist", json=BLOCK, headers={"X-Admin-Token": stale}).status_code == 403


def test_logging_out_ends_the_session(client, password):
    token = _login(client, password).json()["token"]
    assert client.post("/api/admin/logout", headers={"X-Admin-Token": token}).status_code == 200
    assert client.post("/api/admin/blocklist", json=BLOCK, headers={"X-Admin-Token": token}).status_code == 403


def test_a_session_does_not_survive_a_password_change(client, password, monkeypatch):
    token = _login(client, password).json()["token"]
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "a-different-passphrase")
    assert client.post("/api/admin/blocklist", json=BLOCK, headers={"X-Admin-Token": token}).status_code == 403


def test_no_password_configured_means_administration_is_disabled(client, monkeypatch):
    """Fail closed, exactly as the blocklist writes already do: unset is shut, never open."""
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")

    assert _login(client, "anything").status_code == 503
    assert client.post("/api/admin/blocklist", json=BLOCK).status_code == 503


def test_the_static_token_still_works_for_curl_and_ci(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    assert client.post("/api/admin/blocklist", json=BLOCK, headers={"X-Admin-Token": "s3cret"}).status_code == 200


def test_the_docs_show_a_box_for_the_admin_header(client):
    """FastAPI only renders an input for a header it knows about, so the header is a declared parameter."""
    paths = client.get("/openapi.json").json()["paths"]
    for path, method in [
        ("/api/admin/blocklist", "post"),
        ("/api/admin/blocklist/{kind}/{subject}", "delete"),
        ("/api/admin/logout", "post"),
    ]:
        names = [(p["name"].lower(), p["in"]) for p in paths[path][method].get("parameters", [])]
        assert ("x-admin-token", "header") in names, f"{method.upper()} {path} hides the header from /docs"


def test_the_password_and_the_token_never_reach_the_logs(client, password, caplog):
    with caplog.at_level(logging.DEBUG):
        token = _login(client, password).json()["token"]
        _login(client, "guess")
        client.post("/api/admin/blocklist", json=BLOCK, headers={"X-Admin-Token": token})

    written = "\n".join(r.getMessage() for r in caplog.records)
    assert password not in written and token not in written


def test_the_limiter_says_how_long_to_wait_from_a_sliding_window(monkeypatch):
    """Unit-level: the wait is what is left of the window for the oldest attempt still counted."""
    now = [1000.0]
    monkeypatch.setattr(guard.time, "monotonic", lambda: now[0])
    limit = guard.RateLimiter(per_client=1, total=10, window_s=900, what="sign-in attempts")
    limit.check(_req())

    now[0] += 300
    with pytest.raises(HTTPException) as err:
        limit.check(_req())
    assert err.value.status_code == 429
    assert 595 <= int(err.value.headers["Retry-After"]) <= 605, "900 s window, 300 s gone"
