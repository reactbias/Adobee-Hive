"""documentation/PITCH.md beat 3, run live on stage: a quiet, dog-friendly room near Basel SBB under CHF 200.

Discovery used to be gated to stay kinds, so this query could only ever be answered by hotels. It is not gated
any more — `offers` and `needs` are the index and `kind` is only a filter — so these tests pin what the pitch
query actually returns on the seeded hub, including the one case where something that is not a hotel wins.
"""

from app import hive

REQUEST = (
    "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, "
    "2026-11-13 to 2026-11-15, my name is Mara Keller"
)
#: What the offline planner extracts from REQUEST (agent.parse_request), with `kind` left off: the ask as a
#: caller who has stopped narrowing by kind would send it, which is the case the widening put at risk.
ASK = {
    "query": REQUEST,
    "near": "Basel SBB",
    "max_price_chf": 200,
    "check_in": "2026-11-13",
    "check_out": "2026-11-15",
}


def test_beat_three_ranks_hotels_for_the_room_query(client):
    """The pitch query, with nothing filtered by kind, and the whole seeded hub free to answer it.

    It holds, and not by weighting the kind: a stay ask carries dates, and `fit` already says "takes no stay
    bookings" about an entity with no rooms, so a café, a person and an unclaimed example card are near-misses
    with a reason rather than matches. Proximity and attestations then separate the hotels. If someone ever
    makes this fail, the honest fix is in `fit` — what the entity can actually do about the ask — and never a
    bonus for being a hotel.
    """
    found = hive.discover(**ASK)
    top = found["matches"][:3]
    assert len(top) == 3, "the seed must answer the pitch query with at least three stays"
    assert [m["kind"] for m in top] == ["hotel"] * 3, [(m["id"], m["kind"], m["score"]) for m in top]
    assert all(m["bookable"] and m["claimed"] for m in top), "the jury is shown rooms it can actually book"

    # And everything that cannot put her up says so, in the open, rather than being hidden by its kind.
    why_not = {e["id"]: e["why_not"] for e in found["excluded"]}
    assert any("takes no stay bookings" in w for w in why_not["cafe-bienli"])
    assert any("takes no stay bookings" in w for w in why_not["x-endress"])


def test_beat_three_over_the_agent_books_the_hotel_it_always_booked(client):
    """The beat as the jury sees it: the agent asks, three agents agree, and the hold is Rheinblick's room."""
    out = client.post("/api/agent", json={"messages": [{"role": "user", "content": REQUEST}]}).json()
    discover = next(s for s in out["steps"] if s["tool"] == "hive_discover")
    assert {m["kind"] for m in discover["output"]["matches"]} == {"hotel"}
    assert out["pending"]["tool"] == "hive_book"
    assert out["pending"]["input"]["card_id"] == "hotel-rheinblick"
    assert out["consensus"] is True


def test_an_undated_room_query_can_be_won_by_a_cafe_and_that_is_the_model(client):
    """Documented, not defended: without dates there is no room constraint, and the index is offers and needs.

    A café that actually offers a quiet dog-friendly corner outranks a hotel for "a quiet dog-friendly room near
    Basel SBB" when the caller gives no dates and no kind, because the only thing the ask can be scored against
    is what each entity offers. The product owner's call is that this is correct: `offers` and `needs` are the
    primary index and the hub does not re-introduce kind as a weight to keep hotels on top. The pitch is not
    affected — the agent sends `kind="hotel"` and dates (the two tests above) — but a caller who sends neither
    gets the café first, and should.
    """
    hive.publish(
        {
            "id": "cafe-stiller",
            "slug": "stiller",
            "kind": "cafe",
            "name": "Café Stiller Hof (fictional)",
            "description": "Twelve seats and a courtyard.",
            "features": ["dog-friendly", "quiet"],
            "offers": [{"title": "The quiet corner", "summary": "A quiet table for you and your dog, all day."}],
        }
    )
    ranked = hive.discover(query="a quiet dog-friendly room near Basel SBB")["matches"]
    assert ranked[0]["id"] == "cafe-stiller", [(m["id"], m["score"]) for m in ranked[:3]]
    assert ranked[0]["score_breakdown"]["offers_needs"] > 0
    assert ranked[0]["bookable"] is False, "whoever wins, nothing without rooms is ever bookable"
    assert any(m["kind"] == "hotel" for m in ranked[1:4]), "the hotels are still right behind it"

    # Add the dates back and the café is a near-miss again, with the reason: it has no rooms.
    with_dates = hive.discover(
        query="a quiet dog-friendly room near Basel SBB", **{k: ASK[k] for k in ASK if k != "query"}
    )
    assert "cafe-stiller" not in {m["id"] for m in with_dates["matches"]}
    assert with_dates["matches"][0]["kind"] == "hotel"
