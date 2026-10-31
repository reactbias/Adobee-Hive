"""documentation/PITCH.md beat 3, run live on stage: a quiet, dog-friendly room near Basel SBB under CHF 200.

Discovery used to be gated to stay kinds, so this query could only ever be answered by hotels. It is not gated
any more — `offers` and `needs` are the index and `kind` is only a filter — so these tests pin what the pitch
query actually returns on the seeded hub, including the one case where something that is not a hotel wins.
"""

import pytest

from app import db, hive

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


@pytest.mark.parametrize("guest_name", ["Mara Keller", "Quiet Station", "Ada Software"])
def test_browser_pitch_query_ranks_the_fitting_hotel(client, guest_name):
    """The browser sends only prose: its constraints, not the guest's name, determine the winner."""
    query = REQUEST.replace("Mara Keller", guest_name)
    response = client.get("/api/hive/discover", params={"query": query})
    assert response.status_code == 200
    found = response.json()
    assert found["matches"][0]["id"] == "hotel-rheinblick"
    assert all(m["kind"] == "hotel" for m in found["matches"])
    baseline = client.get("/api/hive/discover", params={"query": REQUEST}).json()
    assert [(m["id"], m["score"]) for m in found["matches"]] == [(m["id"], m["score"]) for m in baseline["matches"]]


@pytest.fixture
def browser_search_cards(client):
    """Publish fictional edge-case offers and remove their index/history/key/event state afterwards."""
    cards = [
        {
            "id": "pitch-probe-unlisted",
            "slug": "pitch-probe-unlisted",
            "kind": "hotel",
            "name": "Quiet House (fictional)",
            "features": ["quiet"],
            "offers": [{"title": "Quiet hotel room", "summary": "Contact us for room availability."}],
        },
        *[
            {
                "id": f"pitch-probe-{suffix}",
                "slug": f"pitch-probe-{suffix}",
                "kind": "hotel",
                "name": f"Parking House {suffix} (fictional)",
                "features": ["parking"],
                "distances_m": {"basel sbb": 5000, "messe basel": 0},
                "units": [{"id": "single", "name": "Single room", "max_guests": 1, "price_chf": price, "quantity": 1}],
            }
            for suffix, price in (("free", 0), ("paid", 50))
        ],
        {
            "id": "pitch-probe-service",
            "slug": "pitch-probe-service",
            "kind": "service",
            "name": "Local Support (fictional)",
            "offers": [
                {"title": "Taxi to your hotel", "summary": "Taxi transfers from Basel SBB."},
                {"title": "Website design services", "summary": "Websites for local hotels."},
            ],
            "needs": [{"title": "Quiet hotel room", "summary": "A room near Basel SBB for visiting colleagues."}],
        },
    ]
    try:
        for card in cards:
            hive.publish(card)
        yield
    finally:
        with db.write() as cur:
            for table, column in (
                ("hive_cards", "id"),
                ("hive_card_history", "card_id"),
                ("hive_keys", "card_id"),
                ("hive_events", "card_id"),
            ):
                cur.execute(f"DELETE FROM {table} WHERE {column} LIKE 'pitch-probe-%'")


@pytest.mark.parametrize("date_text", ["", "2027-04-01"])
def test_browser_incomplete_dates_do_not_exclude_a_hotel_without_online_inventory(
    client, browser_search_cards, date_text
):
    """Browsing with no complete stay keeps a hotel findable without inventing an availability check."""
    response = client.get("/api/hive/discover", params={"query": f"A quiet hotel room near Basel SBB {date_text}"})
    assert response.status_code == 200
    assert "pitch-probe-unlisted" in {m["id"] for m in response.json()["matches"]}

    dated = client.get(
        "/api/hive/discover",
        params={"query": "A quiet hotel room near Basel SBB 2027-04-01 to 2027-04-03"},
    )
    assert dated.status_code == 200
    excluded = {m["id"]: m["why_not"] for m in dated.json()["excluded"]}
    assert "takes no stay bookings" in excluded["pitch-probe-unlisted"]


def test_browser_explicit_constraints_override_prose_even_at_default_values(client, browser_search_cards):
    """The explicit free single room is eligible despite contradictory features, guests and dates in prose."""
    query = REQUEST.replace("2026-11-13 to 2026-11-15", "2027-04-10 to 2027-04-10") + " for 3 guests"
    response = client.get(
        "/api/hive/discover",
        params={
            "query": query,
            "features": ["parking"],
            "near": "messe basel",
            "max_price_chf": 0,
            "check_in": "2027-04-01",
            "check_out": "2027-04-02",
            "guests": 1,
        },
    )
    assert response.status_code == 200
    found = response.json()
    matches = {m["id"]: m for m in found["matches"]}
    assert matches["pitch-probe-free"]["from_price_chf"] == 0
    assert matches["pitch-probe-free"]["distance_m"] == 0
    excluded = {m["id"]: m["why_not"] for m in found["excluded"]}
    assert any("budget CHF 0" in reason for reason in excluded["pitch-probe-paid"])


@pytest.mark.parametrize(
    ("query", "extra"),
    [
        ("Book a taxi to a hotel near Basel SBB under CHF 50 for 2 people", {}),
        ("Website design services for a hotel", {}),
        ("A quiet hotel room near Basel SBB", {"kind": "service"}),
        ("A quiet hotel room near Basel SBB under CHF 200", {"looking_for": "needs"}),
        ("", {}),
    ],
)
def test_browser_generic_searches_keep_matching_services_eligible(client, browser_search_cards, query, extra):
    """Transport, services, needs and empty browsing must not acquire hotel-only constraints."""
    response = client.get("/api/hive/discover", params={"query": query, **extra})
    assert response.status_code == 200
    matches = {m["id"]: m for m in response.json()["matches"]}
    assert matches["pitch-probe-service"]["kind"] == "service"
    if extra.get("looking_for") == "needs":
        assert matches["pitch-probe-service"]["score_breakdown"]["offers_needs"] > 0
