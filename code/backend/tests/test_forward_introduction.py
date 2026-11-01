"""An agent asks its own hub, and its hub asks the peer on its behalf (#159).

An agent searches basel at radius 1, finds something zurich carries, and wants an introduction. It
has always been able to walk to zurich itself: `GET /api/hub/directory` gives it every peer with a
working URL and `provenance.path` names the origin, so it is not stranded and never was. What it
loses by walking is the record. Zurich writes the row, and basel — whose search did the work of
finding the match — never learns of it. A score weeks later is the only evidence a hub ever gets
about a peer, so an introduction recorded somewhere else is evidence basel earned and threw away.

So the design point here is the record, not the mechanism. Basel keeps the row calibration reads,
with zurich's claim frozen on it, and tells zurich as well, naming the hub its member belongs to.
Zurich records that as a **claim** — this is an unauthenticated hub-to-hub call, because there is no
hub identity key to sign it with — which is still strictly better than what it recorded before, when
the requester asserted a name and zurich filed it as one of its own members (#158).

Everything about the forward is best effort. The local row is written before it runs and is never
rolled back by it, because a hub whose neighbour is down must still be able to record what its own
member asked for.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import config, connections, db, federation, folders, hive, hub, peers

ZURICH = "zurich"
ZURICH_URL = "http://127.0.0.1:8499"
THEM = "elektro-mattenhof"
GUEST = "mara@example.com"


@pytest.fixture(autouse=True)
def clean_slate(client, monkeypatch):
    """Links, rows and peer knowledge are per test, and no peer is really called."""
    connections.init()
    with db.write() as cur:
        for table in ("folder_links", "folder_grants", "folder_handles", "folder_keys", "hub_connections"):
            cur.execute(f"DELETE FROM {table}")
        cur.execute("DELETE FROM hub_peers")
    folders.reset()
    federation.forget()
    monkeypatch.setattr(hub, "FORWARD_INTRODUCTIONS", True)
    yield
    folders.reset()
    federation.forget()


def _card(entity_id: str = THEM, *, rating: float | None = 4.5) -> tuple[dict, dict[str, str]]:
    """A card signed by a fresh key, plus the registry entry that pins that key for it."""
    body: dict[str, Any] = {
        "id": entity_id,
        "slug": entity_id,
        "kind": "service",
        "name": "Elektro Mattenhof",
        "description": "Electrical work in Zurich.",
        "offers": ["electrician"],
        "version": 3,
        "published_at": "2026-10-20T09:00:00+00:00",
    }
    key = Ed25519PrivateKey.generate()
    public = hive._public_b64(key)
    signature = base64.b64encode(key.sign(hive.canonical(body))).decode()
    trust: dict[str, Any] = {"signature": signature, "public_key": public, "signature_valid": True}
    if rating is not None:
        trust["verified_reviews"] = {"count": 4, "average": rating}
    card = {**body, "trust": trust}
    assert hive.verify_pinned(card, {entity_id: public}), "the fixture has to produce a valid card"
    return card, {entity_id: public}


def _peer_knows(pins: dict[str, str], *, url: str = ZURICH_URL, hub_id: str = ZURICH) -> None:
    """Teach this hub what the peer publishes and where it lives, as the background asking would."""
    profile = {"hub_id": hub_id, "name": f"Adobee Hive ({hub_id})", "owner_keys": pins, "entities": 21}
    federation._by_hub[hub_id] = profile
    if url:
        federation._peers[url] = {
            "profile": profile,
            "last_asked": None,
            "last_asked_ok": True,
            "last_answered": None,
        }
        peers.add(url, "a peer these tests invented")


class FakePeer:
    """Stands in for the carrying hub's own `POST /api/hub/connect`, and records what arrived."""

    def __init__(self, answer: dict | None = None, raise_with: Exception | None = None) -> None:
        self.answer = answer or {"id": "cx-theirs", "state": "open", "requester_proof": "claimed"}
        self.raise_with = raise_with
        self.calls: list[tuple[str, dict]] = []

    def install(self, monkeypatch) -> FakePeer:
        peer = self

        class Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return peer.answer

        class Client:
            def __init__(self, *_, **__) -> None:
                pass

            def __enter__(self) -> Client:
                return self

            def __exit__(self, *_) -> None:
                return None

            def post(self, url: str, json: dict) -> Response:
                peer.calls.append((url, json))
                if peer.raise_with:
                    raise peer.raise_with
                return Response()

        import httpx

        monkeypatch.setattr(httpx, "Client", Client)
        return self


def _connect(**kw) -> dict:
    card, pins = _card()
    _peer_knows(pins)
    return hub.connect(GUEST, THEM, target_hub=ZURICH, card=card, **kw)


# ---------------------------------------------------------------- the record stays here


def test_a_remote_introduction_is_forwarded_and_the_answer_says_what_the_peer_made_of_it(client, monkeypatch):
    peer = FakePeer().install(monkeypatch)

    out = _connect()

    assert out["forwarded"]["sent"] is True
    assert out["forwarded"]["to"] == ZURICH
    assert out["forwarded"]["connection"] == "cx-theirs"
    assert out["forwarded"]["requester_proof"] == "claimed", "the peer cannot check our word and says so"
    assert len(peer.calls) == 1


def test_the_forward_names_the_hub_the_requester_belongs_to(client, monkeypatch):
    """The whole point: the peer learns a member of *another* hub asked, not one of its own."""
    peer = FakePeer().install(monkeypatch)

    _connect()

    url, body = peer.calls[0]
    assert url == f"{ZURICH_URL}/api/hub/connect"
    assert body["requester_hub"] == config.HIVE_HUB_ID
    assert body["requester"] == GUEST
    assert body["entity_id"] == THEM
    assert body["target_hub"] == ZURICH
    assert body["card"], "the peer verifies the card it is handed, like anybody else"


def test_the_row_calibration_reads_stays_on_this_hub_whatever_the_peer_does(client, monkeypatch):
    """The reason forwarding exists rather than redirecting: the claim is frozen here."""
    FakePeer().install(monkeypatch)

    out = _connect()

    row = connections.get(out["id"])
    assert row["target_hub"] == ZURICH and row["via_hub"] == ZURICH
    assert row["published_rating"] == 45, "zurich's claim, frozen at the introduction"
    assert out["remote"] is True


def test_a_forward_is_never_asked_to_forward_again(client, monkeypatch):
    """A hub receiving a forward records it and stops. Otherwise two hubs could bounce one row."""
    peer = FakePeer().install(monkeypatch)

    out = _connect(forward=False)

    assert "forwarded" not in out
    assert peer.calls == []
    assert connections.get(out["id"])["target_hub"] == ZURICH, "and the local record is unaffected"


def test_the_rest_door_passes_forward_through_so_a_hub_can_say_no(client, monkeypatch):
    peer = FakePeer().install(monkeypatch)
    card, pins = _card()
    _peer_knows(pins)
    body = {"requester": GUEST, "entity_id": THEM, "target_hub": ZURICH, "card": card}

    assert client.post("/api/hub/connect", json={**body, "forward": False}).status_code == 200
    assert peer.calls == []

    out = client.post("/api/hub/connect", json=body).json()
    assert out["forwarded"]["sent"] is True
    assert len(peer.calls) == 1


# ---------------------------------------------------------------- best effort, always


def test_a_peer_that_cannot_be_reached_changes_nothing_about_the_local_record(client, monkeypatch):
    FakePeer(raise_with=RuntimeError("connection refused")).install(monkeypatch)

    out = _connect()

    assert out["forwarded"]["sent"] is False
    assert "connection refused" in out["forwarded"]["why"]
    assert out["state"] == connections.OPEN, "the introduction was still recorded"
    assert connections.get(out["id"])["published_rating"] == 45


def test_a_peer_this_hub_has_no_url_for_is_not_called_at_all(client, monkeypatch):
    """The URL comes from this hub's own peer list, never from the request."""
    peer = FakePeer().install(monkeypatch)
    card, pins = _card()
    _peer_knows(pins, url="")  # keys known, address not

    out = hub.connect(GUEST, THEM, target_hub=ZURICH, card=card)

    assert out["forwarded"]["sent"] is False
    assert "no URL for" in out["forwarded"]["why"]
    assert peer.calls == [], "nothing was fetched on a caller's say-so"
    assert out["state"] == connections.OPEN


def test_a_hub_can_turn_forwarding_off(client, monkeypatch):
    peer = FakePeer().install(monkeypatch)
    monkeypatch.setattr(hub, "FORWARD_INTRODUCTIONS", False)

    out = _connect()

    assert "forwarded" not in out
    assert peer.calls == []


def test_a_local_introduction_is_never_forwarded(client, monkeypatch):
    """There is nobody to tell: this hub is the one carrying the entity."""
    peer = FakePeer().install(monkeypatch)

    out = hub.connect(GUEST, hive.list_cards()[0]["id"])

    assert "forwarded" not in out
    assert peer.calls == []


def test_a_peer_that_refuses_the_forward_is_recorded_as_having_refused(client, monkeypatch):
    import httpx

    FakePeer(raise_with=httpx.HTTPStatusError("400", request=None, response=None)).install(monkeypatch)

    out = _connect()

    assert out["forwarded"]["sent"] is False
    assert "HTTPStatusError" in out["forwarded"]["why"]
    assert out["state"] == connections.OPEN


# ---------------------------------------------------------------- the refusal that points somewhere


def test_a_refusal_names_the_peer_this_hub_knows_carries_the_entity(client):
    """ "Not on this hub" is a dead end when the hub has the answer in its own book."""
    _, pins = _card()
    _peer_knows(pins)

    with pytest.raises(hub.HubError) as refused:
        hub.connect(GUEST, THEM)

    said = str(refused.value)
    assert f"carried by {ZURICH}" in said
    assert ZURICH_URL in said, "with the URL, so an agent can actually go there"
    assert "target_hub='zurich'" in said, "and what to pass when it comes back"


def test_the_hint_appears_on_the_missing_target_hub_refusal_too(client):
    card, pins = _card()
    _peer_knows(pins)

    with pytest.raises(hub.HubError, match=f"carried by {ZURICH}"):
        hub.connect(GUEST, THEM, card=card)


def test_an_entity_no_peer_claims_gets_no_invented_hint(client):
    """Honest about not knowing: a peer this hub has not heard from publishes nothing it can see."""
    with pytest.raises(hub.HubError) as refused:
        hub.connect(GUEST, "nobody-carries-this")

    said = str(refused.value)
    assert "is not on this hub" in said
    assert "peer book says" not in said


def test_the_carrier_lookup_reads_the_peer_book_and_never_asks_anybody(client):
    """A refusal must not be able to be made slow, so this is a local read by construction."""
    _, pins = _card()
    _peer_knows(pins)

    assert federation.carriers_of(THEM) == [{"hub": ZURICH, "url": ZURICH_URL}]
    assert federation.carriers_of("someone-else") == []
    assert federation.carriers_of("") == []


def test_a_carrier_this_hub_knows_keys_for_but_no_address_is_named_without_one(client):
    _, pins = _card()
    _peer_knows(pins, url="")

    assert federation.carriers_of(THEM) == [{"hub": ZURICH, "url": ""}]
    with pytest.raises(hub.HubError, match=f"carried by {ZURICH}"):
        hub.connect(GUEST, THEM)
