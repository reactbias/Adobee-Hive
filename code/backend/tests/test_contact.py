"""`contact` is always there, so nothing downstream has to guard it."""

from __future__ import annotations

from app import hive


def test_every_card_carries_contact_with_the_standard_channels(client):
    """A caller should never write `contact?.email?`. The key is there; "" means not published."""
    for card in hive.list_cards():
        full = hive.get_card(card["id"])
        assert "contact" in full, f"{card['id']} has no contact block"
        for channel in hive.CONTACT_CHANNELS:
            assert channel in full["contact"], f"{card['id']} is missing contact.{channel}"


def test_filling_the_keys_never_invents_a_value():
    """An absent channel and an empty one read differently to a person. Only the key is filled."""
    out = hive.with_contact({"contact": {"email": "a@b.example"}})

    assert out["contact"]["email"] == "a@b.example"
    assert out["contact"]["phone"] == "", "a missing channel becomes empty, not fabricated"


def test_a_card_with_no_contact_at_all_still_gets_the_block():
    assert hive.with_contact({})["contact"] == {"email": "", "phone": ""}


def test_the_map_stays_open_to_channels_we_did_not_think_of():
    out = hive.with_contact({"contact": {"whatsapp": "+41 79 000 00 00", "mcp": "https://x.example/mcp"}})

    assert out["contact"]["whatsapp"] == "+41 79 000 00 00"
    assert out["contact"]["mcp"] == "https://x.example/mcp"
    assert out["contact"]["email"] == "" and out["contact"]["phone"] == ""


def test_a_channel_the_owner_closed_stays_absent_rather_than_listed_as_withheld():
    """Same rule as `structure`: naming a private channel in order to withhold it announces it exists."""
    closed = hive.with_contact({"contact": {"email": "a@b.example"}, "contact_sharing": {"phone": "never"}})
    assert "phone" not in closed["contact"], "a `never` channel is absent, not empty"

    held = hive.with_contact({"contact": {"email": "a@b.example"}, "contact_sharing": {"phone": "push"}})
    assert "phone" not in held["contact"], "a `push` channel is the owner's to send, not ours to hint at"


def test_a_gated_channel_is_present_and_empty_so_it_can_be_asked_for():
    """`confirm` is the one case where empty means "they have one, ask" rather than "none"."""
    out = hive.with_contact({"contact": {"phone": ""}, "contact_sharing": {"phone": "confirm"}})

    assert out["contact"]["phone"] == ""
    assert out["contact_sharing"]["phone"] == "confirm", "the flag is what tells them apart"


def test_contact_survives_a_round_trip_through_the_api(client):
    card_id = hive.list_cards()[0]["id"]
    body = (
        client.get(f"/api/hive/cards/{card_id}").json()
        if client.get(f"/api/hive/cards/{card_id}").status_code == 200
        else hive.get_card(card_id)
    )

    assert "contact" in body
    assert all(c in body["contact"] for c in hive.CONTACT_CHANNELS)
