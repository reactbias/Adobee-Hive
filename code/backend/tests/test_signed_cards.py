"""A card its owner signed elsewhere: the hub checks it and stores it, and never holds its key."""

import base64

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import config, db, hive, owner


def _owner_key() -> tuple[Ed25519PrivateKey, str]:
    """A key the way a hotel node would hold it: generated outside the hub."""
    key = Ed25519PrivateKey.generate()
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return key, base64.b64encode(raw).decode()


def _card(card_id: str, version: int = 1, **extra) -> dict:
    """A minimal card as `hive.publish` would have finished it on the owner's own node."""
    return {
        "id": card_id,
        "slug": card_id,
        "kind": "hotel",
        "name": "Fictional Node Hotel",
        "description": "A fictional hotel that keeps its own signing key.",
        "contact": {"email": "", "phone": "", "mcp": "https://node.example/mcp/"},
        "units": [{"id": "double", "name": "Double", "max_guests": 2, "price_chf": 150, "quantity": 2}],
        "version": version,
        "published_at": "2026-11-01T10:00:00+00:00",
        "valid_until": "2027-02-01T10:00:00+00:00",
        **extra,
    }


def _signed(key: Ed25519PrivateKey, card: dict) -> str:
    return base64.b64encode(key.sign(hive.canonical(card))).decode()


def test_a_card_signed_by_its_owner_is_stored_as_signed_and_pinned(client):
    key, public = _owner_key()
    card = _card("node-pinned")

    stored = hive.accept_signed(card, _signed(key, card), public)

    assert stored["trust"]["public_key"] == public
    assert hive.owner_keys()["node-pinned"] == public, "agents must find the owner's key in the registry"
    assert hive.verify_pinned(hive.get_card("node-pinned"), hive.owner_keys())
    with db.cursor() as cur:
        held = cur.execute("SELECT 1 FROM hive_keys WHERE card_id = ?", ["node-pinned"]).fetchone()
    assert held is None, "the hub must not hold a private key for a card its owner signs"


def test_a_changed_card_is_refused(client):
    key, public = _owner_key()
    card = _card("node-tampered")
    signature = _signed(key, card)

    with pytest.raises(hive.HiveError, match="signature"):
        hive.accept_signed({**card, "name": "Altered"}, signature, public)
    assert hive.get_record("node-tampered") is None


def test_a_later_version_needs_the_key_already_pinned(client):
    key, public = _owner_key()
    first = _card("node-pin-holds")
    hive.accept_signed(first, _signed(key, first), public)
    stranger, stranger_public = _owner_key()
    second = _card("node-pin-holds", version=2)

    with pytest.raises(hive.HiveError, match="pinned"):
        hive.accept_signed(second, _signed(stranger, second), stranger_public)

    assert hive.accept_signed(second, _signed(key, second), public)["version"] == 2


def test_a_card_the_hub_signs_cannot_be_taken_over_by_a_new_key(client):
    published = hive.publish(_card("hub-signed-card"))
    stranger, stranger_public = _owner_key()
    takeover = _card("hub-signed-card", version=published["version"] + 1)

    with pytest.raises(hive.HiveError, match="pinned"):
        hive.accept_signed(takeover, _signed(stranger, takeover), stranger_public)


def test_an_older_version_is_refused_and_the_same_one_is_a_quiet_repeat(client):
    key, public = _owner_key()
    second = _card("node-versions", version=2)
    hive.accept_signed(second, _signed(key, second), public)

    assert hive.accept_signed(second, _signed(key, second), public)["version"] == 2
    first = _card("node-versions", version=1)
    with pytest.raises(hive.HiveError, match="version"):
        hive.accept_signed(first, _signed(key, first), public)


def test_a_card_missing_what_the_hub_needs_is_refused(client):
    key, public = _owner_key()
    card = _card("node-no-kind")
    del card["kind"]

    with pytest.raises(hive.HiveError, match="kind"):
        hive.accept_signed(card, _signed(key, card), public)


@pytest.mark.parametrize(
    "change",
    [
        {"name": ""},
        {"name": 7},
        {"kind": 7},
        {"version": "2"},
        {"contact": "not a map"},
        {"features": "dog-friendly"},
        {"features": [7]},
        {"distances_m": ["Basel SBB"]},
        {"units": "a room"},
        {"units": ["a room"]},
        {"units": [{"id": "double"}]},
        {"units": [{"id": "d", "name": "D", "max_guests": "2", "price_chf": 1, "quantity": 1}]},
    ],
)
def test_a_signed_card_the_hub_could_not_serve_is_refused(client, change):
    key, public = _owner_key()
    card = _card("node-bad-shape") | change

    with pytest.raises(hive.HiveError):
        hive.accept_signed(card, _signed(key, card), public)
    assert hive.get_record("node-bad-shape") is None


def test_search_still_works_after_the_smallest_card_the_hub_accepts(client):
    key, public = _owner_key()
    card = {
        "id": "node-smallest",
        "slug": "node-smallest",
        "kind": "hotel",
        "name": "Fictional Smallest",
        "version": 1,
        "valid_until": "2099-01-01T00:00:00+00:00",
    }
    hive.accept_signed(card, _signed(key, card), public)

    assert "matches" in hive.discover(query="fictional smallest")


def test_a_card_over_the_hub_limits_is_refused(client):
    key, public = _owner_key()
    card = _card("node-too-long", name="x" * 5000)

    with pytest.raises(hive.HiveError):
        hive.accept_signed(card, _signed(key, card), public)
    assert hive.get_record("node-too-long") is None


def test_the_hub_cannot_book_or_edit_a_card_it_has_no_key_for(client):
    key, public = _owner_key()
    card = _card("node-no-hub-booking")
    hive.accept_signed(card, _signed(key, card), public)

    with pytest.raises(hive.HiveError, match="own node"):
        hive.book("node-no-hub-booking", "double", "2027-03-08", "2027-03-10", "Fictional Guest")
    with pytest.raises(hive.HiveError, match="own node"):
        owner.apply("node-no-hub-booking", {**card, "name": "Edited on the hub"})

    assert hive.get_card("node-no-hub-booking")["name"] == card["name"]
    assert hive.owner_keys()["node-no-hub-booking"] == public, "a refused edit must not mint a hub key"


def test_the_endpoint_stores_a_signed_card_and_needs_the_owner_token(client, monkeypatch):
    key, public = _owner_key()
    card = _card("node-over-rest")
    body = {"card": card, "signature": _signed(key, card), "public_key": public}
    monkeypatch.setattr(config, "OWNER_EDIT_TOKEN", "fictional-token")

    assert client.post("/api/hive/cards/signed", json=body).status_code == 403
    assert hive.get_record("node-over-rest") is None

    done = client.post("/api/hive/cards/signed", json=body, headers={"X-Owner-Token": "fictional-token"})
    assert done.status_code == 200
    assert done.json()["trust"]["public_key"] == public


def test_the_endpoint_answers_a_bad_signature_with_a_refusal(client):
    key, public = _owner_key()
    card = _card("node-bad-rest")
    body = {"card": {**card, "name": "Altered"}, "signature": _signed(key, card), "public_key": public}

    assert client.post("/api/hive/cards/signed", json=body).status_code == 400
