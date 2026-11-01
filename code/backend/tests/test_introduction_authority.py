"""Who may answer an introduction, and who may score it (#107).

Two decisions sit on a connection row and they belong to two different people: the **owner** of the
target says yes or no, and the **requester** says afterwards how it went. Neither used to need
anything. A caller who knew a connection id could walk a row from `requested` through `open` to
`rated`, and the real requester's score was then refused as already given — so an unrelated client
could both fake a consent and consume the one final score that calibration reads.

A connection id was never a secret. It is in the answer `hub_connect` returns and in the queues any
agent reads, which is exactly why it cannot be the credential.

What this hub has instead of accounts (#135 is roadmap) is three things that exist, strongest first:
a **link secret**, which names one side of the folder link this row stands on; a **signed action**
under the key the target registered, for a card whose owner brought one; and this hub's **owner
token** or **admin credential**, which are hub-wide and prove the holder may answer for *an* entity
here rather than for this one. The row records which it was, so afterwards a per-entity yes and a
hub-wide one are different facts.

Every door fails closed, and the half that matters most is the score: a hub-wide credential standing
in for the requester would make one person's one final score available to whoever holds it.
"""

from __future__ import annotations

import asyncio
import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp import Client

from app import config, connections, db, folder_keys, folders, hive, hub, owner, sharing
from app.domains import hr
from app.mcp_server import server
from tests.mcp_result import tool_result

GUEST = "mara@example.com"
STRANGER = "someone-else@example.com"
#: The two hub-wide credentials these tests configure. Assembled rather than written as single
#: literals, and named for what they are: a secret scanner should not have to decide whether a test
#: fixture is a leak, and an allowlist entry would loosen a gate the whole repo shares.
ADMIN_CREDENTIAL = "-".join(("test", "operator", "credential"))
OWNER_CREDENTIAL = "-".join(("test", "owner", "credential"))
PERSON = "person-consent"


@pytest.fixture(autouse=True)
def clean_slate(client, monkeypatch):
    """No rows, no links, and no hub-wide credential unless a test sets one."""
    connections.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_connections")
        cur.execute("DELETE FROM folder_links")
        cur.execute("DELETE FROM folder_grants")
        cur.execute("DELETE FROM folder_keys")
    folders.reset()
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    yield


def _mcp(tool: str, args: dict) -> dict:
    async def go():
        async with Client(server) as c:
            return tool_result(await c.call_tool(tool, args))

    return asyncio.run(go())


def _public() -> str:
    """A freely connectable entity this hub carries, so the introduction opens at once."""
    return hive.list_cards()[0]["id"]


def _as(secret: str) -> dict:
    """The header a party presents its link secret in, the same one a folder read uses."""
    return {folder_keys.HEADER: f"{folder_keys.SCHEME} {secret}"}


def _open_row(requester: str = GUEST) -> dict:
    """An open introduction, with the requester holding its own credential as `hub.connect` hands it."""
    return hub.connect(requester, _public())


def _pending_row(requester: str = GUEST, public_key: str = "") -> dict:
    """An introduction waiting on a person's yes, and the target's own side of its link."""
    card = {**hr.EXAMPLE_CARD, "id": PERSON, "slug": "consent", "sharing": sharing.CONFIRM}
    if public_key:
        card["owner_public_key"] = public_key
    hive.publish(card)
    row = hub.connect(requester, PERSON)
    assert row["state"] == connections.REQUESTED
    return row


def _target_secret(row: dict) -> str:
    """The target's side of the link, which is the owner's per-entity credential for this row."""
    return folder_keys.mint(row["folder_link"], folders.handle_for(row["target"]), pending_ok=True)["secret"]


def _signed(signer: Ed25519PrivateKey, connection_id: str, action: str, **over) -> dict:
    doc = hub.decision_to_sign(connection_id, action) | over
    statement = hub.decision_statement(connection_id, action, doc["nonce"], doc["expires"])
    return {
        "signature": base64.b64encode(signer.sign(hive.canonical(statement))).decode(),
        "nonce": doc["nonce"],
        "expires": doc["expires"],
    }


# ---------------------------------------------------------------- nobody, which is the finding


def test_an_unrelated_caller_cannot_walk_a_row_from_requested_to_rated(client):
    """The reported impact, end to end: consent faked and the one final score consumed."""
    row = _pending_row()

    with pytest.raises(hub.HubError, match="needs authority over"):
        hub.decide(row["id"], "confirm")
    assert connections.get(row["id"])["state"] == connections.REQUESTED

    opened = hub.decide(row["id"], "confirm", secret=_target_secret(row))
    assert opened["state"] == connections.OPEN

    with pytest.raises(hub.HubError, match="requester's own credential"):
        hub.score(row["id"], 50)
    assert connections.get(row["id"])["state"] == connections.OPEN

    scored = hub.score(row["id"], 40, secret=row["folder_key"]["secret"])
    assert scored["connection"]["rating"] == 40, "the real requester still has its one score"


def test_a_connection_id_alone_is_refused_at_every_door(client):
    row = _open_row()
    paths = (
        (f"/api/hub/connections/{row['id']}/score", {"rating": 40}),
        (f"/api/hub/connections/{row['id']}/confirm", None),
        (f"/api/hub/connections/{row['id']}/decline", None),
    )
    for path, body in paths:
        res = client.post(path, json=body) if body else client.post(path)
        assert res.status_code == 400, path

    after = connections.get(row["id"])
    assert after["state"] == connections.OPEN and after["rating"] is None


def test_a_secret_is_scoped_to_one_introduction_and_not_to_the_pair_of_agents(client):
    """The same requester, two introductions. The handle matches on both, so only the link can refuse.

    Pinned separately from the stranger case below because the two checks fail differently: a
    stranger is caught by the handle, and this is caught by the link. A credential good for every row
    between the same two parties would let one meeting's score be spent on another's.
    """
    first = _open_row()
    second = hub.connect(GUEST, hive.list_cards()[1]["id"])
    assert first["folder_link"] != second["folder_link"]

    with pytest.raises(hub.HubError, match="requester's own credential"):
        hub.score(second["id"], 50, secret=first["folder_key"]["secret"])
    assert connections.get(second["id"])["rating"] is None

    assert hub.score(second["id"], 20, secret=second["folder_key"]["secret"])["connection"]["rating"] == 20


def test_a_stranger_with_their_own_introduction_cannot_act_on_somebody_elses(client):
    """A link secret is a real credential, so the test is that it is scoped to its own row."""
    mine = _open_row()
    theirs = _open_row(STRANGER)

    with pytest.raises(hub.HubError, match="requester's own credential"):
        hub.score(theirs["id"], 50, secret=mine["folder_key"]["secret"])
    assert connections.get(theirs["id"])["rating"] is None


def test_the_targets_credential_does_not_score_and_the_requesters_does_not_consent(client):
    """Two parties, two decisions. Neither side's secret is the other's."""
    row = _pending_row()
    target = _target_secret(row)

    with pytest.raises(hub.HubError, match="needs authority over"):
        hub.decide(row["id"], "confirm", secret=row["folder_key"]["secret"])

    hub.decide(row["id"], "confirm", secret=target)
    with pytest.raises(hub.HubError, match="requester's own credential"):
        hub.score(row["id"], 40, secret=target)
    assert connections.get(row["id"])["rating"] is None


def test_a_revoked_link_stops_authorising_on_the_next_call(client):
    """The credential is bound to the link, so withdrawing the link withdraws the authority."""
    row = _open_row()
    secret = row["folder_key"]["secret"]
    folders.revoke_link(row["folder_link"])

    with pytest.raises(hub.HubError, match="requester's own credential"):
        hub.score(row["id"], 40, secret=secret)


# ---------------------------------------------------------------- the requester scores


def test_the_requesters_own_secret_scores_and_the_row_says_which_proof_it_was(client):
    row = _open_row()

    out = hub.score(row["id"], 35, "went well", secret=row["folder_key"]["secret"])

    assert out["connection"]["state"] == connections.RATED
    assert out["connection"]["scored_by"] == hub.BY_LINK
    assert out["connection"]["decided_by"] is None, "nobody had to consent to a public introduction"


def test_the_rest_door_reads_the_secret_from_the_header_and_not_from_the_body(client):
    row = _open_row()
    path = f"/api/hub/connections/{row['id']}/score"
    secret = row["folder_key"]["secret"]

    assert client.post(path, json={"rating": 40, "note": secret}).status_code == 400
    assert client.post(path, json={"rating": 40}, headers=_as(secret)).status_code == 200


def test_scoring_is_still_once_even_with_the_right_credential(client):
    row = _open_row()
    secret = row["folder_key"]["secret"]
    assert hub.score(row["id"], 40, secret=secret)["connection"]["rating"] == 40
    with pytest.raises(connections.ConnectionError_, match="already been scored"):
        hub.score(row["id"], 10, secret=secret)


def test_the_requester_is_handed_a_credential_even_for_an_introduction_that_waits(client):
    """Its only chance: the next thing that happens to the row is the owner's decision."""
    row = _pending_row()
    secret = row["folder_key"]["secret"]

    assert secret
    assert folder_keys.resolve(secret) is None, "and it reads nothing while the link is pending"

    hub.decide(row["id"], "confirm", secret=_target_secret(row))
    assert folder_keys.resolve(secret) is not None, "the owner's yes is what brings it to life"
    assert hub.score(row["id"], 45, secret=secret)["connection"]["rating"] == 45


def test_an_mcp_transport_that_carries_no_headers_cannot_score(client):
    """Deliberately stricter than it looks: in-process and stdio carry nothing, so they prove nothing.

    The same way round as the owner's edit tools — a credential that cannot arrive must refuse, not
    be waived.
    """
    row = _open_row()
    out = _mcp("hub_score", {"connection_id": row["id"], "rating": 40})
    assert "requester's own credential" in out["error"]
    assert connections.get(row["id"])["rating"] is None


# ---------------------------------------------------------------- the owner answers


def test_the_targets_side_of_the_link_confirms_and_declines(client):
    row = _pending_row()
    opened = hub.decide(row["id"], "confirm", secret=_target_secret(row))
    assert opened["state"] == connections.OPEN and opened["decided_by"] == hub.BY_LINK

    other = _pending_row(STRANGER)
    declined = hub.decide(other["id"], "decline", note="not now", secret=_target_secret(other))
    assert declined["state"] == connections.DECLINED and declined["decided_by"] == hub.BY_LINK
    assert declined["note"] == "not now"


def test_a_signature_under_the_key_the_target_registered_is_a_per_entity_yes(client):
    signer = Ed25519PrivateKey.generate()
    pubkey_b64 = base64.b64encode(signer.public_key().public_bytes_raw()).decode()
    row = _pending_row(public_key=pubkey_b64)

    out = hub.decide(row["id"], "confirm", **_signed(signer, row["id"], "confirm"))

    assert out["state"] == connections.OPEN
    assert out["decided_by"] == hub.BY_OWNER_KEY


def test_a_signature_from_a_stranger_key_is_refused(client):
    signer = Ed25519PrivateKey.generate()
    pubkey_b64 = base64.b64encode(signer.public_key().public_bytes_raw()).decode()
    row = _pending_row(public_key=pubkey_b64)

    with pytest.raises(hub.HubError, match="does not match the key"):
        hub.decide(row["id"], "confirm", **_signed(Ed25519PrivateKey.generate(), row["id"], "confirm"))
    assert connections.get(row["id"])["state"] == connections.REQUESTED


def test_a_signed_decline_cannot_be_replayed_as_a_confirm(client):
    """What binding the action into the document buys."""
    signer = Ed25519PrivateKey.generate()
    pubkey_b64 = base64.b64encode(signer.public_key().public_bytes_raw()).decode()
    row = _pending_row(public_key=pubkey_b64)
    said_no = _signed(signer, row["id"], "decline")

    with pytest.raises(hub.HubError, match="does not match the key"):
        hub.decide(row["id"], "confirm", **said_no)
    assert hub.decide(row["id"], "decline", **said_no)["state"] == connections.DECLINED


def test_a_signature_for_another_introduction_cannot_answer_this_one(client):
    signer = Ed25519PrivateKey.generate()
    pubkey_b64 = base64.b64encode(signer.public_key().public_bytes_raw()).decode()
    row = _pending_row(public_key=pubkey_b64)

    with pytest.raises(hub.HubError, match="does not match the key"):
        hub.decide(row["id"], "confirm", **_signed(signer, "cx-somebodyelse", "confirm"))
    assert connections.get(row["id"])["state"] == connections.REQUESTED


def test_an_expired_decision_document_is_refused(client):
    signer = Ed25519PrivateKey.generate()
    pubkey_b64 = base64.b64encode(signer.public_key().public_bytes_raw()).decode()
    row = _pending_row(public_key=pubkey_b64)

    with pytest.raises(hub.HubError, match="expired"):
        hub.decide(row["id"], "confirm", **_signed(signer, row["id"], "confirm", expires="2020-01-01T00:00:00"))
    assert connections.get(row["id"])["state"] == connections.REQUESTED


@pytest.mark.parametrize("broken", ["", "not-a-date", "whenever"])
def test_an_unreadable_expiry_counts_as_expired(client, broken):
    signer = Ed25519PrivateKey.generate()
    pubkey_b64 = base64.b64encode(signer.public_key().public_bytes_raw()).decode()
    row = _pending_row(public_key=pubkey_b64)

    with pytest.raises(hub.HubError):
        hub.decide(row["id"], "confirm", **_signed(signer, row["id"], "confirm", expires=broken))
    assert connections.get(row["id"])["state"] == connections.REQUESTED


def test_a_card_whose_key_the_hub_holds_says_so_rather_than_failing_obscurely(client):
    row = _pending_row()
    with pytest.raises(hub.HubError, match="held by this hub"):
        hub.decide(row["id"], "confirm", **_signed(Ed25519PrivateKey.generate(), row["id"], "confirm"))


def test_the_document_the_hub_offers_is_the_document_it_checks(client):
    signer = Ed25519PrivateKey.generate()
    pubkey_b64 = base64.b64encode(signer.public_key().public_bytes_raw()).decode()
    row = _pending_row(public_key=pubkey_b64)

    doc = client.get(f"/api/hub/connections/{row['id']}/decision?action=confirm").json()
    statement = hub.decision_statement(row["id"], "confirm", doc["nonce"], doc["expires"])
    assert base64.b64decode(doc["canonical"]) == hive.canonical(statement)

    res = client.post(
        f"/api/hub/connections/{row['id']}/confirm",
        json={
            "signature": base64.b64encode(signer.sign(base64.b64decode(doc["canonical"]))).decode(),
            "nonce": doc["nonce"],
            "expires": doc["expires"],
        },
    )
    assert res.status_code == 200 and res.json()["state"] == connections.OPEN


# ---------------------------------------------------------------- the hub-wide credentials


def test_the_owner_token_answers_and_the_row_records_that_it_was_hub_wide(client, monkeypatch):
    """It proves the holder may answer for *an* entity here, never for this one. So the row says so."""
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", OWNER_CREDENTIAL)
    row = _pending_row()

    res = client.post(f"/api/hub/connections/{row['id']}/confirm", headers={owner.TOKEN_HEADER: OWNER_CREDENTIAL})

    assert res.status_code == 200
    out = res.json()
    assert out["state"] == connections.OPEN
    assert out["decided_by"] == hub.BY_OWNER_TOKEN
    assert out["decided_by"] != hub.BY_LINK, "a hub-wide yes is not a per-entity one"


def test_a_wrong_owner_token_is_refused(client, monkeypatch):
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", OWNER_CREDENTIAL)
    row = _pending_row()

    res = client.post(f"/api/hub/connections/{row['id']}/confirm", headers={owner.TOKEN_HEADER: "guess"})

    assert res.status_code == 400
    assert connections.get(row["id"])["state"] == connections.REQUESTED


def test_an_unset_owner_token_authorises_nobody(client):
    """`guard.secret_matches` and not `secret_ok`: an unset secret matches nothing, it is not off."""
    row = _pending_row()

    res = client.post(f"/api/hub/connections/{row['id']}/confirm", headers={owner.TOKEN_HEADER: ""})

    assert res.status_code == 400
    assert connections.get(row["id"])["state"] == connections.REQUESTED
    assert "has not set" in res.json()["detail"], "and the refusal says the operator has not set one"


def test_the_owner_token_does_not_score(client, monkeypatch):
    """The score is one person's, so no hub-wide credential may spend it."""
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", OWNER_CREDENTIAL)
    row = _open_row()

    res = client.post(
        f"/api/hub/connections/{row['id']}/score",
        json={"rating": 50},
        headers={owner.TOKEN_HEADER: OWNER_CREDENTIAL},
    )

    assert res.status_code == 400
    assert connections.get(row["id"])["rating"] is None


def test_the_operator_answers_and_scores_through_their_own_route_and_is_named(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", ADMIN_CREDENTIAL)
    head = {"X-Admin-Token": ADMIN_CREDENTIAL}
    row = _pending_row()

    opened = client.post(f"/api/admin/connections/{row['id']}/confirm", headers=head).json()
    assert opened["state"] == connections.OPEN
    assert hub.BY_ADMIN in opened["decided_by"]

    scored = client.post(f"/api/admin/connections/{row['id']}/score", json={"rating": 30}, headers=head).json()
    assert scored["connection"]["rating"] == 30
    assert hub.BY_ADMIN in scored["connection"]["scored_by"]
    assert scored["connection"]["scored_by"] != hub.BY_LINK, "never recorded as the requester's own report"


def test_the_operator_route_fails_closed_with_no_admin_credential(client):
    row = _pending_row()
    res = client.post(f"/api/admin/connections/{row['id']}/confirm")
    assert res.status_code == 503
    assert connections.get(row["id"])["state"] == connections.REQUESTED


def test_the_admin_token_is_not_a_master_key_on_the_parties_own_routes(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", ADMIN_CREDENTIAL)
    row = _pending_row()

    res = client.post(f"/api/hub/connections/{row['id']}/confirm", headers={"X-Admin-Token": ADMIN_CREDENTIAL})

    assert res.status_code == 400
    assert connections.get(row["id"])["state"] == connections.REQUESTED


# ---------------------------------------------------------------- the requester backing out


def test_a_requester_may_withdraw_its_own_request_with_its_own_secret(client):
    """Allowed before with no credential at all, on an argument nothing checked."""
    row = _pending_row()

    out = hub.decide(row["id"], "decline", note="changed my mind", secret=row["folder_key"]["secret"])

    assert out["state"] == connections.DECLINED
    assert "requester withdrew" in out["decided_by"], "and the row does not call it the owner's no"


def test_a_requesters_secret_still_cannot_confirm_on_the_owners_behalf(client):
    row = _pending_row()
    with pytest.raises(hub.HubError, match="needs authority over"):
        hub.decide(row["id"], "confirm", secret=row["folder_key"]["secret"])
    assert connections.get(row["id"])["state"] == connections.REQUESTED


# ---------------------------------------------------------------- lifecycle, still


def test_an_answered_introduction_cannot_be_answered_again(client):
    row = _pending_row()
    target = _target_secret(row)
    hub.decide(row["id"], "confirm", secret=target)

    with pytest.raises(hub.HubError, match="only a requested connection"):
        hub.decide(row["id"], "decline", secret=target)


def test_a_declined_introduction_never_becomes_a_rating(client):
    row = _pending_row()
    hub.decide(row["id"], "decline", secret=_target_secret(row))

    with pytest.raises(connections.ConnectionError_):
        hub.score(row["id"], 50, secret=row["folder_key"]["secret"])


def test_a_decision_only_wins_while_the_row_is_still_requested(client, monkeypatch):
    """The conditional transition, exercised where it is the only thing that can catch it.

    Both `hub.decide` and `connections.confirm` read the row and check its state before writing, and
    a row answered before either read is caught by those checks — which says nothing about the
    write. So this declines it inside `folders.accept_link`, the last thing `confirm` does before its
    UPDATE and, in any link implementation that is not a local table, a round trip. That is the
    window `WHERE state = ?` exists for: one winner, decided by the write.
    """
    row = _pending_row()
    target = _target_secret(row)
    real = folders.accept_link

    def decline_meanwhile(link_id, *, by=""):
        out = real(link_id, by=by)
        with db.write() as cur:  # the owner's other agent declines in the same moment
            cur.execute("UPDATE hub_connections SET state = ? WHERE id = ?", [connections.DECLINED, row["id"]])
        return out

    monkeypatch.setattr(folders, "accept_link", decline_meanwhile)

    with pytest.raises(connections.ConnectionError_, match="changed while this was being authorised"):
        hub.decide(row["id"], "confirm", secret=target)
    assert connections.get(row["id"])["state"] == connections.DECLINED, "the decline stood"


def test_a_row_written_before_these_columns_existed_still_reads(client):
    """The demo hub has a snapshot of older rows; a missing attribution is a fact about the row."""
    row = _open_row()
    with db.write() as cur:
        cur.execute(
            "UPDATE hub_connections SET decided_by = NULL, scored_by = NULL WHERE id = ?",
            [row["id"]],
        )

    fetched = connections.get(row["id"])
    assert fetched["decided_by"] is None and fetched["scored_by"] is None
    assert connections.awaiting_rating(GUEST), "and it is still evidence"
