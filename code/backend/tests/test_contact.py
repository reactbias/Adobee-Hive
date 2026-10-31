"""Contact rides on the search result, so nothing has to fetch a card to find a way to get in touch."""

from __future__ import annotations

from app import hive


def test_a_search_result_carries_contact_without_fetching_the_card(client):
    """A federated result has no cheap way to fetch the full card, so contact travels with it."""
    found = hive.discover(query="quiet")

    assert found["matches"], "the seed must answer this"
    for match in found["matches"]:
        assert "contact" in match, f"{match['id']} has no contact on the result"
        assert isinstance(match["contact"], dict)
        assert "contact_sharing" in match, "the flags travel too, or an empty value cannot be read"


def test_contact_survives_the_hop_to_a_peer(client):
    """The case that matters: a remote result is the one that cannot go and fetch the card."""
    forwarded = hive.discover(query="quiet", seen=["basel"])

    for match in forwarded["matches"]:
        assert "contact" in match
        assert "contact" in match["card"], "the signed card carries it too, for anyone who checks"
