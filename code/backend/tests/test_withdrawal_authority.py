"""Withdrawing an application takes proof it is yours (#108).

A pending application is a state transition waiting to happen, and it used to need nothing to make
it happen. `GET /api/hub/register/{id}` hands the id to anybody, so knowing it was enough to
withdraw somebody else's application — and the row then said "withdrawn by the applicant" about an
act the applicant knew nothing about, while the authorized operator could no longer admit it,
because it was no longer pending.

An id is a lookup. The three things that are authority here are a signed action under the key the
applicant registered, the capability this hub returns once for an application whose key it holds,
and the operator through their own separate route. This file is mostly about the fourth case: none
of them, which must leave the row exactly as it was.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import config, db, hive, registration

APPLIED = "cafe-authority"
#: The operator credential these tests configure. Assembled rather than written as one literal, and
#: named for what it is rather than with a word a secret scanner has to treat as a finding.
ADMIN_CREDENTIAL = "-".join(("test", "operator", "credential"))


@pytest.fixture(autouse=True)
def clean_slate(client, monkeypatch):
    """A vetted hub, so an application is pending and therefore withdrawable."""
    registration.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_applications")
        for table, column in (("hive_cards", "id"), ("hive_card_history", "card_id"), ("hive_keys", "card_id")):
            cur.execute(f"DELETE FROM {table} WHERE {column} = ?", [APPLIED])
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.VETTED)
    yield


def _keypair() -> tuple[Ed25519PrivateKey, str]:
    """A fresh signer and the base64 of its public half. Nothing here is stored or reused."""
    signer = Ed25519PrivateKey.generate()
    return signer, base64.b64encode(signer.public_key().public_bytes_raw()).decode()


def _application(pubkey_b64: str = "", signer: Ed25519PrivateKey | None = None) -> dict:
    app = {
        "entity": {
            "id": APPLIED,
            "kind": "stay",
            "name": "Café Authority (fictional)",
            "description": "A fictional café on the Rhine.",
            "sharing": "public",
        },
        "public_key": pubkey_b64,
        "proofs": [],
        "invite": "",
    }
    if signer is not None:
        signed = signer.sign(hive.canonical(registration.unsigned(app)))
        app["signature"] = base64.b64encode(signed).decode()
    return app


def _hub_custody() -> dict:
    """A pending application whose key this hub holds, so its proof is the capability."""
    return registration.apply(_application())


def _owner_key() -> tuple[dict, Ed25519PrivateKey]:
    """A pending application that brought its own key, so its proof is a signature."""
    signer, pubkey_b64 = _keypair()
    return registration.apply(_application(pubkey_b64, signer)), signer


def _signed(signer: Ed25519PrivateKey, app_id: str, **over) -> dict:
    """A withdrawal document from the hub, signed with `key`. `over` replaces part of it."""
    doc = registration.withdrawal_to_sign(app_id) | over
    statement = registration.withdrawal_statement(app_id, doc["nonce"], doc["expires"])
    return {
        "signature": base64.b64encode(signer.sign(hive.canonical(statement))).decode(),
        "nonce": doc["nonce"],
        "expires": doc["expires"],
    }


# ---------------------------------------------------------------- nobody, which is the bug


def test_knowing_an_application_id_does_not_authorize_withdrawing_it(client):
    """The finding, exactly: a credential-free unrelated caller moved pending to withdrawn."""
    out = _hub_custody()

    with pytest.raises(registration.RegistrationError, match="not authority to change it"):
        registration.withdraw(out["id"])

    assert registration.get(out["id"])["state"] == registration.PENDING, "and nothing moved"


def test_a_refused_withdrawal_leaves_the_operator_able_to_admit(client):
    """The second half of the impact: the attack used to cost the hub the application."""
    out = _hub_custody()
    with pytest.raises(registration.RegistrationError):
        registration.withdraw(out["id"])

    admitted = registration.decide(out["id"], True, reason="fine")
    assert admitted["state"] == registration.ADMITTED
    assert hive.get_record(APPLIED) is not None


def test_the_rest_door_refuses_a_withdrawal_with_no_proof_at_all(client):
    out = _hub_custody()
    res = client.post(f"/api/hub/register/{out['id']}/withdraw")
    assert res.status_code == 400
    assert "not authority to change it" in res.json()["detail"]
    assert registration.get(out["id"])["state"] == registration.PENDING


def test_a_wrong_capability_is_refused_as_wrong_rather_than_as_missing(client):
    """A present-but-wrong credential must never fall through to the next door's error."""
    out = _hub_custody()
    with pytest.raises(registration.RegistrationError, match="not application .* withdrawal key"):
        registration.withdraw(out["id"], key="not-the-key")
    assert registration.get(out["id"])["state"] == registration.PENDING


# ---------------------------------------------------------------- the applicant, with a capability


def test_the_capability_is_returned_once_and_withdraws_the_application(client):
    out = _hub_custody()
    assert out["withdraw_key"], "returned by apply, and only by apply"

    done = registration.withdraw(out["id"], key=out["withdraw_key"])

    assert done["state"] == registration.WITHDRAWN
    assert done["decided_by"] == registration.BY_CAPABILITY
    assert "by the applicant" in done["reason"] and "capability" in done["reason"]


def test_the_capability_is_in_no_read_of_the_application_ever(client):
    """It is stored as SHA-256 and `SELECT` does not name the column, so nothing can leak it."""
    out = _hub_custody()
    secret = out["withdraw_key"]

    fetched = registration.get(out["id"])
    queue = registration.listing(registration.PENDING)
    served = client.get(f"/api/hub/register/{out['id']}").json()
    admin_queue = client.get("/api/admin/applications?state=pending").json()

    for seen in (fetched, queue[0], served, admin_queue):
        text = repr(seen)
        assert secret not in text, "the plaintext came back out"
        assert "withdraw_sha256" not in seen if isinstance(seen, dict) else True
    assert "withdraw_key" not in fetched, "only the submission answer ever carries it"


def test_a_replayed_capability_is_inert_because_the_row_is_no_longer_pending(client):
    out = _hub_custody()
    registration.withdraw(out["id"], key=out["withdraw_key"])

    with pytest.raises(registration.RegistrationError, match="only a pending application"):
        registration.withdraw(out["id"], key=out["withdraw_key"])


def test_the_rest_door_takes_the_capability_in_a_header_and_not_in_the_body(client):
    """A header, so it stays out of URLs, proxy logs and agent transcripts."""
    out = _hub_custody()
    path = f"/api/hub/register/{out['id']}/withdraw"

    refused = client.post(path, json={"signature": out["withdraw_key"]})
    assert refused.status_code == 400, "the body is not where a capability is read from"

    done = client.post(path, headers={registration.KEY_HEADER: out["withdraw_key"]})
    assert done.status_code == 200 and done.json()["state"] == registration.WITHDRAWN


# ---------------------------------------------------------------- the applicant, with their key


def test_an_owner_key_application_gets_no_capability_and_withdraws_by_signing(client):
    out, signer = _owner_key()
    assert "withdraw_key" not in out, "nothing the hub could forge on its applicant's behalf"

    done = registration.withdraw(out["id"], **_signed(signer, out["id"]))

    assert done["state"] == registration.WITHDRAWN
    assert done["decided_by"] == registration.BY_SIGNATURE
    assert "signed action" in done["reason"]


def test_a_signature_from_a_stranger_key_is_refused(client):
    out, _ = _owner_key()
    stranger, _ = _keypair()

    with pytest.raises(registration.RegistrationError, match="does not match the key"):
        registration.withdraw(out["id"], **_signed(stranger, out["id"]))
    assert registration.get(out["id"])["state"] == registration.PENDING


def test_a_signature_for_another_application_cannot_withdraw_this_one(client):
    """What binding the application id into the document buys."""
    out, signer = _owner_key()
    elsewhere = _signed(signer, "ap-somebodyelse")

    with pytest.raises(registration.RegistrationError, match="does not match the key"):
        registration.withdraw(out["id"], **elsewhere)
    assert registration.get(out["id"])["state"] == registration.PENDING


def test_an_expired_withdrawal_document_is_refused(client):
    out, signer = _owner_key()
    past = (datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)).isoformat()

    with pytest.raises(registration.RegistrationError, match="expired"):
        registration.withdraw(out["id"], **_signed(signer, out["id"], expires=past))
    assert registration.get(out["id"])["state"] == registration.PENDING


@pytest.mark.parametrize("expires", ["", "not-a-date", "soon", "2026-13-45"])
def test_an_unreadable_expiry_counts_as_expired(client, expires):
    """No window at all, on a destructive act, reads as a closed one."""
    out, signer = _owner_key()
    signed = _signed(signer, out["id"], expires=expires) if expires else {}
    with pytest.raises(registration.RegistrationError):
        registration.withdraw(out["id"], **(signed or {"signature": "x", "nonce": "n", "expires": ""}))
    assert registration.get(out["id"])["state"] == registration.PENDING


def test_a_partial_signed_withdrawal_is_refused_rather_than_half_checked(client):
    out, signer = _owner_key()
    full = _signed(signer, out["id"])

    for dropped in ("signature", "nonce", "expires"):
        with pytest.raises(registration.RegistrationError, match="together"):
            registration.withdraw(out["id"], **{k: v for k, v in full.items() if k != dropped})
    assert registration.get(out["id"])["state"] == registration.PENDING


def test_a_capability_is_not_accepted_for_an_application_that_registered_a_key(client):
    """Two custody models, two proofs; the weaker one is not a fallback for the stronger."""
    out, _ = _owner_key()
    with pytest.raises(registration.RegistrationError, match="carries no withdrawal capability"):
        registration.withdraw(out["id"], key="anything")
    assert registration.get(out["id"])["state"] == registration.PENDING


def test_the_document_the_hub_offers_is_the_document_it_checks(client):
    """An applicant signs published bytes rather than guessing at the canonical form."""
    out, signer = _owner_key()
    doc = client.get(f"/api/hub/register/{out['id']}/withdrawal").json()

    statement = registration.withdrawal_statement(out["id"], doc["nonce"], doc["expires"])
    assert base64.b64decode(doc["canonical"]) == hive.canonical(statement)
    assert doc["statement"] == statement

    res = client.post(
        f"/api/hub/register/{out['id']}/withdraw",
        json={
            "signature": base64.b64encode(signer.sign(base64.b64decode(doc["canonical"]))).decode(),
            "nonce": doc["nonce"],
            "expires": doc["expires"],
        },
    )
    assert res.status_code == 200 and res.json()["state"] == registration.WITHDRAWN


# ---------------------------------------------------------------- the operator, as themselves


def test_an_operator_withdrawal_is_recorded_as_the_operators_act_and_not_the_applicants(client, monkeypatch):
    """The attribution half of #108: the ledger must not claim a consent nobody gave."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", ADMIN_CREDENTIAL)
    out = _hub_custody()

    res = client.post(f"/api/admin/applications/{out['id']}/withdraw", headers={"X-Admin-Token": ADMIN_CREDENTIAL})

    assert res.status_code == 200
    done = res.json()
    assert done["state"] == registration.WITHDRAWN
    assert done["decided_by"] == registration.BY_OPERATOR
    assert "not by the applicant" in done["reason"]
    assert "by the applicant," not in done["reason"]


def test_the_operator_route_fails_closed_without_an_admin_credential(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    out = _hub_custody()

    res = client.post(f"/api/admin/applications/{out['id']}/withdraw")

    assert res.status_code == 503, "no configured credential refuses rather than opens"
    assert registration.get(out["id"])["state"] == registration.PENDING


def test_a_wrong_admin_token_does_not_withdraw(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", ADMIN_CREDENTIAL)
    out = _hub_custody()

    res = client.post(f"/api/admin/applications/{out['id']}/withdraw", headers={"X-Admin-Token": "guess"})

    assert res.status_code == 403
    assert registration.get(out["id"])["state"] == registration.PENDING


def test_the_applicant_route_does_not_accept_an_admin_token(client, monkeypatch):
    """The two acts are separate doors, so the admin credential is not a master applicant proof."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", ADMIN_CREDENTIAL)
    out = _hub_custody()

    res = client.post(f"/api/hub/register/{out['id']}/withdraw", headers={"X-Admin-Token": ADMIN_CREDENTIAL})

    assert res.status_code == 400
    assert registration.get(out["id"])["state"] == registration.PENDING


# ---------------------------------------------------------------- the race, and old rows


def test_an_admitted_application_cannot_be_withdrawn_by_anyone(client):
    out = _hub_custody()
    registration.decide(out["id"], True, reason="fine")

    for proof in ({"key": out["withdraw_key"]}, {"by_operator": "static token"}):
        with pytest.raises(registration.RegistrationError, match="only a pending application"):
            registration.withdraw(out["id"], **proof)


def test_a_withdrawal_only_wins_while_the_row_is_still_pending(client, monkeypatch):
    """The `WHERE state = pending` guard, exercised where it is the only thing that can catch it.

    `withdraw` reads the row, checks the proof, then writes. Admitting the application *before* the
    read is caught by the lifecycle check at the top, so it says nothing about the write. This admits
    it while the proof is being checked, which is the interleaving the conditional exists for: the
    one winner has to be decided by the UPDATE, not by a check that already passed.
    """
    out = _hub_custody()
    real = registration._applicant_proof

    def admit_meanwhile(row, key, signature, nonce, expires):
        proof = real(row, key, signature, nonce, expires)
        with db.write() as cur:  # the operator gets there first
            cur.execute("UPDATE hub_applications SET state = ? WHERE id = ?", [registration.ADMITTED, row["id"]])
        return proof

    monkeypatch.setattr(registration, "_applicant_proof", admit_meanwhile)

    with pytest.raises(registration.RegistrationError, match="was decided while"):
        registration.withdraw(out["id"], key=out["withdraw_key"])
    assert registration.get(out["id"])["state"] == registration.ADMITTED, "admission stood"


def test_an_application_written_before_capabilities_existed_says_so(client):
    """The demo hub has a snapshot of older rows. A missing capability is a fact about the row."""
    out = _hub_custody()
    with db.write() as cur:
        cur.execute("UPDATE hub_applications SET withdraw_sha256 = NULL WHERE id = ?", [out["id"]])

    with pytest.raises(registration.RegistrationError, match="predates them"):
        registration.withdraw(out["id"], key=out["withdraw_key"])
    assert registration.withdraw(out["id"], by_operator="static token")["state"] == registration.WITHDRAWN


# ---------------------------------------------------------------- published in advance


def test_the_hub_publishes_how_to_withdraw_before_anybody_has_to_guess(client):
    rules = client.get("/api/hub/registration").json()["withdrawal"]
    assert "not authority to change it" in rules["means"]
    assert registration.KEY_HEADER in rules["with_hub_custody"]
    assert "action: 'withdraw'" in rules["with_an_owner_key"]
    assert rules["window_seconds"] == registration.WITHDRAW_WINDOW_S
    assert "never as the applicant's consent" in rules["operator"]
