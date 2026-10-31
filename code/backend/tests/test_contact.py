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


def test_contact_on_a_forwarded_result_comes_from_the_signed_card(client):
    """The case that matters: a remote result is the one that cannot go and fetch the card.

    This used to read "every signed card has a contact key", which held only while discovery was
    gated to hotels. It is not what the promise is: kinds without contact details are discoverable
    now (a person never has any, by design, and an unclaimed example card carries none either), and
    the rule that matters is that the hub never *invents* one. So: whatever contact a result shows
    is exactly what the signed card says, and an empty one means the card had nothing to show.
    """
    forwarded = hive.discover(query="quiet", seen=["basel"])

    assert forwarded["matches"], "the seed must answer this"
    for match in forwarded["matches"]:
        assert match["contact"] == (match["card"].get("contact") or {}), match["id"]
        assert match["contact_sharing"] == (match["card"].get("contact_sharing") or {}), match["id"]
    carried = [m for m in forwarded["matches"] if m["contact"]]
    assert carried, "and a business that does publish one still travels with it"
