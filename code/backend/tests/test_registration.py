"""Joining a hub: the signed application, the checks, and who gets in."""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import blocklist, config, db, hive, registration

#: Ids these tests register. Admission publishes into the shared index, so they are cleared
#: between tests or the availability check fails on the leftovers of the previous one.
TEST_IDS = ("cafe-neu", "cafe-two", "cafe-three")


@pytest.fixture(autouse=True)
def clean_slate(client, monkeypatch):
    """An empty queue, an empty blocklist, no leftover entities, and a hub that admits on its checks."""
    blocklist.init()
    registration.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_applications")
        cur.execute("DELETE FROM hub_blocklist")
        for table, column in (("hive_cards", "id"), ("hive_card_history", "card_id"), ("hive_keys", "card_id")):
            cur.execute(f"DELETE FROM {table} WHERE {column} IN (?, ?, ?)", list(TEST_IDS))
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.OPEN)
    yield


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    key = Ed25519PrivateKey.generate()
    return key, base64.b64encode(key.public_key().public_bytes_raw()).decode()


def _application(entity_id="cafe-neu", key=None, public_key="", **extra) -> dict:
    app = {
        "entity": {
            "id": entity_id,
            "kind": "stay",
            "name": "Café Neu (fictional)",
            "description": "A fictional café on the Rhine.",
            "sharing": "public",
        },
        "public_key": public_key,
        "proofs": [],
        "invite": "",
        **extra,
    }
    if key is not None:
        app["signature"] = base64.b64encode(key.sign(hive.canonical(registration.unsigned(app)))).decode()
    return app


# ---------------------------------------------------------------- the happy path


def test_an_applicant_who_brings_a_key_and_signs_is_admitted_and_findable(client):
    """The whole journey: generate a keypair, sign the document, join, appear in the index."""
    key, public_key = _keypair()

    out = registration.apply(_application(key=key, public_key=public_key))

    assert out["state"] == registration.ADMITTED
    assert out["custody"] == "owner", "the applicant keeps the private half"
    assert out["verification"] == "signed"
    assert [c["check"] for c in out["checks"] if c["ok"]] == [
        "shape",
        "size",
        "signature",
        "blocklist",
        "availability",
        "invite",
    ]
    assert hive.get_record("cafe-neu") is not None, "an admitted entity is in the index"
    assert out["next"]


def test_the_hub_pins_the_owners_key_and_never_sees_the_private_half(client):
    key, public_key = _keypair()
    registration.apply(_application(key=key, public_key=public_key))

    card = hive.get_record("cafe-neu")["data"]
    assert card["owner_public_key"] == public_key
    assert card["custody"] == "owner"
    assert "private" not in str(card).lower()


def test_an_applicant_without_a_key_is_admitted_but_recorded_as_hub_custody(client):
    """The demo path. Weaker, and said so plainly rather than dressed up."""
    out = registration.apply(_application())

    assert out["state"] == registration.ADMITTED
    assert out["custody"] == "hub" and out["verification"] == "none"
    assert "demo custody" in next(c["detail"] for c in out["checks"] if c["check"] == "signature")


# ---------------------------------------------------------------- the checks bite


def test_a_bad_signature_is_refused(client):
    """What the signature proves is key possession. Someone else's key proves nothing."""
    _, public_key = _keypair()
    other, _ = _keypair()

    out = registration.apply(_application(key=other, public_key=public_key))

    assert out["state"] == registration.REJECTED
    assert "does not match" in out["reason"]
    assert hive.get_record("cafe-neu") is None, "a refused application publishes nothing"


def test_bringing_a_key_without_signing_is_refused(client):
    _, public_key = _keypair()
    out = registration.apply(_application(public_key=public_key))

    assert out["state"] == registration.REJECTED
    assert "must be signed" in out["reason"]


def test_a_tampered_application_is_refused(client):
    """Signing covers the whole document, so changing the name after signing breaks it."""
    key, public_key = _keypair()
    app = _application(key=key, public_key=public_key)
    app["entity"]["name"] = "Something Else"

    assert registration.apply(app)["state"] == registration.REJECTED


def test_a_malformed_id_is_refused_with_a_useful_reason(client):
    for bad in ("", "A", "Café", "x" * 70, "has space"):
        out = registration.apply(_application(entity_id=bad))
        assert out["state"] == registration.REJECTED
        assert "id is" in out["reason"]


def test_an_entity_without_a_name_is_refused(client):
    app = _application()
    app["entity"]["name"] = "  "
    assert "needs a name" in registration.apply(app)["reason"]


def test_a_blocked_id_cannot_register(client):
    blocklist.block(blocklist.ENTITY, "cafe-neu", "fabricated reviews last time")
    out = registration.apply(_application())

    assert out["state"] == registration.REJECTED and "blocked" in out["reason"]


def test_an_id_already_in_the_index_cannot_be_taken(client):
    registration.apply(_application())
    again = registration.apply(_application())

    assert again["state"] == registration.REJECTED
    assert "already registered" in again["reason"]


def test_the_checks_stop_at_the_first_failure(client):
    """A malformed document gets a useful answer rather than a pile of consequential ones."""
    out = registration.apply(_application(entity_id="has space"))

    assert [c["check"] for c in out["checks"]] == ["shape"]


def test_an_id_is_normalised_to_lower_case_rather_than_refused(client):
    """Ids are case-insensitive. Refusing CAFE-NEU would be pedantry; silently serving two is worse."""
    assert registration.apply(_application(entity_id="CAFE-NEU"))["state"] == registration.ADMITTED
    assert hive.get_record("cafe-neu") is not None

    clash = registration.apply(_application(entity_id="Cafe-Neu"))
    assert clash["state"] == registration.REJECTED and "already registered" in clash["reason"]


# ---------------------------------------------------------------- admission policy


def test_a_vetted_hub_queues_an_application_for_a_person(client, monkeypatch):
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.VETTED)
    out = registration.apply(_application())

    assert out["state"] == registration.PENDING
    assert hive.get_record("cafe-neu") is None, "nothing is published until a person says yes"
    assert registration.listing(registration.PENDING)[0]["id"] == out["id"]

    admitted = registration.decide(out["id"], True, decided_by="ole")
    assert admitted["state"] == registration.ADMITTED
    assert hive.get_record("cafe-neu") is not None


def test_a_refusal_needs_a_reason_and_the_applicant_is_told_it(client, monkeypatch):
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.VETTED)
    out = registration.apply(_application())

    with pytest.raises(registration.RegistrationError, match="needs a reason"):
        registration.decide(out["id"], False)

    refused = registration.decide(out["id"], False, reason="we only carry Basel businesses")
    assert refused["state"] == registration.REJECTED
    assert refused["reason"] == "we only carry Basel businesses"
    assert "apply again" in refused["next"]


def test_an_invite_only_hub_refuses_without_a_token_and_admits_with_one(client, monkeypatch):
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.INVITE)
    monkeypatch.setattr(config, "INVITE_TOKENS", ["let-me-in"])

    assert registration.apply(_application())["state"] == registration.REJECTED
    assert registration.apply(_application(entity_id="cafe-two", invite="wrong"))["state"] == registration.REJECTED
    assert (
        registration.apply(_application(entity_id="cafe-three", invite="let-me-in"))["state"] == registration.ADMITTED
    )


def test_a_closed_hub_admits_nobody_but_still_says_why(client, monkeypatch):
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.CLOSED)
    out = registration.apply(_application())

    assert out["state"] == registration.REJECTED
    assert "not accepting" in out["reason"]
    assert all(c["ok"] for c in out["checks"]), "the application was fine; the hub is shut"


def test_an_applicant_can_withdraw_before_a_decision(client, monkeypatch):
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.VETTED)
    out = registration.apply(_application())

    assert registration.withdraw(out["id"])["state"] == registration.WITHDRAWN
    with pytest.raises(registration.RegistrationError):
        registration.decide(out["id"], True)


# ---------------------------------------------------------------- what is published


def test_proofs_are_recorded_but_raise_nothing_until_something_checks_them(client):
    """A claim is not a verification, and registration never blocks on a DNS lookup."""
    key, public_key = _keypair()
    app = _application(key=None, public_key=public_key)
    app["proofs"] = [{"type": "dns-txt", "subject": "cafe-neu.example"}]
    app["signature"] = base64.b64encode(key.sign(hive.canonical(registration.unsigned(app)))).decode()

    out = registration.apply(app)
    assert out["state"] == registration.ADMITTED
    assert out["proofs"] == [{"type": "dns-txt", "subject": "cafe-neu.example"}]
    assert out["verification"] == "signed", "an unconfirmed proof raises nothing"


def test_an_unknown_proof_type_is_refused_rather_than_ignored(client):
    app = _application()
    app["proofs"] = [{"type": "vibes", "subject": "trust me"}]
    assert "each proof needs a type" in registration.apply(app)["reason"]


def test_the_policy_is_published_so_an_applicant_can_read_the_rules_first(client, monkeypatch):
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.VETTED)
    policy = registration.policy()

    assert policy["policy"] == registration.VETTED and policy["means"]
    assert policy["checks"] == [name for name, _ in registration.CHECKS]
    assert policy["example"]["entity"]["id"] and policy["key_custody"]


def test_the_hub_publishes_the_exact_bytes_to_sign(client):
    """A client that disagrees with the hub about canonical form cannot register at all."""
    key, public_key = _keypair()
    app = _application(public_key=public_key)
    to_sign = base64.b64decode(registration.canonical_to_sign(app))
    app["signature"] = base64.b64encode(key.sign(to_sign)).decode()

    assert registration.apply(app)["state"] == registration.ADMITTED


# ---------------------------------------------------------------- over the wire


def test_registering_over_rest_returns_the_decision_not_an_error(client, monkeypatch):
    """A refusal is an outcome. 200 with state rejected, so a client reads one shape either way."""
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.OPEN)
    res = client.post("/api/hub/register", json=_application())
    assert res.status_code == 200 and res.json()["state"] == registration.ADMITTED

    refused = client.post("/api/hub/register", json=_application(entity_id="has space"))
    assert refused.status_code == 200, "a refusal is an answer, not a 4xx"
    assert refused.json()["state"] == registration.REJECTED


def test_the_admin_queue_needs_a_token_to_decide_but_not_to_read(client, monkeypatch):
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.VETTED)
    out = registration.apply(_application())
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")

    assert client.get("/api/admin/applications?state=pending").status_code == 200
    assert client.post(f"/api/admin/applications/{out['id']}", json={"admit": True}).status_code == 403
    ok = client.post(f"/api/admin/applications/{out['id']}", json={"admit": True}, headers={"X-Admin-Token": "s3cret"})
    assert ok.status_code == 200 and ok.json()["state"] == registration.ADMITTED


def test_an_agent_can_read_the_rules_and_apply_over_mcp(client):
    import asyncio

    from mcp import Client

    from app.mcp_server import server

    async def go():
        async with Client(server) as c:
            rules = (await c.call_tool("hub_registration", {})).structured_content
            applied = (await c.call_tool("hub_register", {"entity": _application()["entity"]})).structured_content
            return rules, applied

    rules, applied = asyncio.run(go())
    assert rules["policy"] in registration.POLICIES
    assert applied["state"] == registration.ADMITTED


# ---------------------------------------------------------------- choosing a hub


def test_the_directory_lists_hubs_the_way_a_person_choosing_one_needs(client):
    """instances.social for Hives: before you can join a federated network you must pick a door."""
    out = client.get("/api/hub/directory").json()
    home = next(h for h in out["hubs"] if h["home"])

    assert home["name"] and home["description"]
    assert home["admission"] in registration.POLICIES
    assert home["accepting"] is (config.ADMISSION_POLICY != registration.CLOSED)
    # Absolute, since #156: a person choosing a hub is given this link to use, and the home row used to
    # be the one row whose link could not be used. tests/test_home_hub_row.py is where that lives.
    assert home["url"] and home["apply_at"] == f"{home['url']}/api/hub/register"
    assert home["entities"] >= 0
    assert out["admission_meanings"], "a policy name means nothing without its sentence"


def test_the_directory_does_not_invent_what_it_has_not_asked(client):
    """A peer's own description comes from its discovery document. Until asked, say so."""
    out = client.get("/api/hub/directory").json()

    for row in (h for h in out["hubs"] if not h["home"]):
        assert row["admission"] == "unknown" and row["accepting"] is None
        assert row["verdict"] in ("unproven", "calibrated", "over-promises", "under-promises")


def test_a_closed_hub_says_it_is_not_accepting_rather_than_hiding(client, monkeypatch):
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.CLOSED)
    home = next(h for h in client.get("/api/hub/directory").json()["hubs"] if h["home"])

    assert home["accepting"] is False and home["admission"] == registration.CLOSED
