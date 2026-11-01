"""Hop-limited federated search: a traveller decides how far from this Hive their agent may look.

Every peer here is in-process: a FakeHive signs its own cards with its own key and answers a forwarded query the
way the REST endpoint does. No sockets, no network, so the suite still runs with no key and no connection.
"""

import asyncio
import base64
import time
from datetime import UTC, datetime, timedelta
from unittest import mock

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from mcp import Client

from app import config, federation, hive, reputation
from app.mcp_server import server
from tests.mcp_result import tool_result

ASK = {"kind": "hotel", "features": ["dog-friendly"], "check_in": "2027-03-10", "check_out": "2027-03-12"}


def _card(card_id: str, name: str, price: float = 180.0) -> dict:
    """A card the way a peer Hive publishes it: fictional, and signed below with that peer's own key."""
    return {
        "id": card_id,
        "slug": card_id,
        "kind": "hotel",
        "name": name,
        "tagline": "A fictional stay in a fictional town",
        "description": "Quiet, dog-friendly rooms. Seed data, invented for the demo.",
        "features": ["quiet", "dog-friendly"],
        "units": [{"id": "std", "name": "Standard", "max_guests": 2, "price_chf": price, "quantity": 4}],
        "version": 1,
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "valid_until": (datetime.now(UTC) + timedelta(days=30)).isoformat(timespec="seconds"),
    }


def _offer_card(card_id: str, name: str, offer: str) -> dict:
    """A fictional person card: no rooms, one offer, which is all a hub needs to find them."""
    return {
        "id": card_id,
        "slug": card_id,
        "kind": "person",
        "name": name,
        "tagline": "Fictional, invented for the demo",
        "description": "Seed data, invented for the demo.",
        "offers": [{"title": offer}],
        "version": 1,
        "published_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "valid_until": (datetime.now(UTC) + timedelta(days=30)).isoformat(timespec="seconds"),
    }


class FakeHive:
    """One in-process peer Hive: its own signing key, its own cards, and its own peers to forward to.

    `match` overrides the score, breakdown and reasons this peer reports for its cards, for the
    tests that care what the local hub does with a remote score rather than how it was reached.
    """

    def __init__(
        self,
        hub_id: str,
        cards=(),
        relays=(),
        delay_ms: float = 0.0,
        paid: bool = False,
        tamper=(),
        match: dict | None = None,
        starting_up: bool = False,
    ):
        self.hub_id = hub_id
        self.url = f"https://{hub_id}.example/"
        self.key = Ed25519PrivateKey.generate()
        self.public_key = base64.b64encode(self.key.public_key().public_bytes_raw()).decode()
        self.cards = [self._sign(c) for c in cards]
        self.relays = list(relays)
        self.delay_ms = delay_ms
        self.paid = paid
        self.tamper = set(tamper)
        self.match = match or {}
        # A hub serves /.well-known/hive.json from the moment it binds, which is before seed_vaults has
        # registered anything, so for a second or two it honestly answers with an empty key registry.
        self.starting_up = starting_up
        self.asks: list[dict] = []

    def _sign(self, data: dict) -> dict:
        signature = base64.b64encode(self.key.sign(hive.canonical(data))).decode()
        trust = {
            "signature_valid": True,
            "claimed": True,
            "provenance": None,
            "signature": signature,
            "public_key": self.public_key,
            "algorithm": "Ed25519 over canonical JSON (sorted keys, no spaces)",
            "attestations": [],
            "verified_reviews": {"count": 0, "average": None, "recent": [], "rule": reputation.BOOKING_RECEIPT_RULE},
            "freshness_days": 0,
            "fresh": True,
        }
        return {**data, "trust": trust}

    def profile(self) -> dict:
        """What this peer publishes at /.well-known/hive.json, as the other hub reads it."""
        return {
            "hub_id": self.hub_id,
            "verification": "signed",
            "paid_placement": self.paid,
            "ranking_policy": "Sponsored first." if self.paid else "No paid placement.",
            "owner_keys": {} if self.starting_up else {c["id"]: c["trust"]["public_key"] for c in self.cards},
        }

    def _match(self, card: dict) -> dict:
        served = card
        if card["id"] in self.tamper:  # the carrier changed a signed fact after the owner signed it
            served = {**card, "units": [{**card["units"][0], "price_chf": 1.0}]}
        units = served.get("units") or []
        return {
            "id": card["id"],
            "slug": card["slug"],
            "name": card["name"],
            "kind": card["kind"],
            "tagline": card["tagline"],
            "from_price_chf": units[0]["price_chf"] if units else None,
            "distance_m": None,
            "score": 60.0,
            "score_breakdown": {"constraints": 50, "text_relevance": 10},
            "why": ["has dog-friendly"],
            **self.match,
            "signature_valid": True,
            "card": served,
            "provenance": {"path": [self.hub_id], "hops": 0, "origin": self.hub_id, "origin_url": self.url},
        }

    async def search(self, ask: dict, radius: int, budget_ms: float, seen: list[str]) -> dict:
        """Answer a forwarded query: this peer's own cards, plus what its own peers send back."""
        self.asks.append({"radius": radius, "budget_ms": budget_ms, "seen": list(seen)})
        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000)
        matches = [self._match(c) for c in self.cards]
        onward = [p for p in self.relays if p.hub_id not in seen]
        if radius >= 1:
            for peer in onward:
                out = await peer.search(ask, radius - 1, budget_ms, [*seen, self.hub_id])
                matches += [
                    m | {"provenance": m["provenance"] | {"path": [*m["provenance"]["path"], self.hub_id]}}
                    for m in out["matches"]
                ]
        return {
            "matches": matches,
            "excluded": [],
            "ranking_policy": "No paid placement.",
            "federation": {"hub": self.hub_id, "radius": radius, "seen": [*seen, self.hub_id]},
        }


class FakeNet:
    """The transport federation.py uses in these tests: peer base URLs mapped to in-process Hives."""

    def __init__(self, *hubs: FakeHive):
        self.hubs = {h.url: h for h in hubs}
        self.profiles: list[str] = []

    async def profile(self, base_url: str) -> dict:
        self.profiles.append(base_url)
        return self.hubs[base_url].profile()

    async def search(self, base_url: str, ask: dict, radius: int, budget_ms: float, seen: list[str]) -> dict:
        return await self.hubs[base_url].search(ask, radius, budget_ms, seen)


@pytest.fixture
def net(monkeypatch):
    """Wire a peer network into federation.py and leave no trust or cached profile behind."""

    def wire(*hubs: FakeHive, peers: list[FakeHive] | None = None) -> FakeNet:
        transport = FakeNet(*hubs)
        monkeypatch.setattr(federation, "DEFAULT_TRANSPORT", transport)
        monkeypatch.setattr(config, "HIVE_PEER_URLS", [h.url for h in (peers if peers is not None else hubs)])
        monkeypatch.setattr(config, "HIVE_HUB_ID", "basel")
        federation.forget()
        reputation.forget()
        return transport

    yield wire
    federation.forget()
    reputation.forget()


def _mcp(tool: str, args: dict) -> dict:
    async def go():
        async with Client(server) as c:
            return tool_result(await c.call_tool(tool, args))

    return asyncio.run(go())


def _ids(found: dict) -> set[str]:
    return {m["id"] for m in found["matches"]}


def _by_id(found: dict, card_id: str) -> dict:
    return next(m for m in found["matches"] if m["id"] == card_id)


# ---------------------------------------------------------------- radius 0 is today


def test_radius_zero_is_exactly_todays_answer(client):
    plain, same = hive.discover(**ASK), hive.discover(**ASK, radius=0)
    assert same == plain
    assert set(plain) == {"matches", "excluded", "ranking_policy"}, "radius 0 adds no field to the answer"
    for match in plain["matches"] + plain["excluded"]:
        assert not {"provenance", "hops", "card", "federated_score"} & set(match)


#: What a door's answer carries at radius 0. `matched` and `considered` are the relevance threshold's
#: counts (see `hive.only_relevant`): both doors report them, at every radius, so they say nothing about
#: how far a query travelled. The point of the assertions below is that nothing *federation*-specific
#: appears when nothing was federated — that part is checked field by field in the test above.
DOOR_FIELDS = {"matches", "excluded", "ranking_policy", "matched", "considered"}


def test_radius_zero_is_the_default_over_mcp_and_rest(client):
    over_mcp = _mcp("hive_discover", ASK)
    assert over_mcp == _mcp("hive_discover", ASK | {"radius": 0})
    assert set(over_mcp) == DOOR_FIELDS
    rest = client.get("/api/hive/discover", params=ASK).json()
    assert {m["id"] for m in rest["matches"]} == {m["id"] for m in over_mcp["matches"]}
    assert set(rest) == DOOR_FIELDS


def test_a_negative_radius_cannot_reach_a_peer_at_any_layer(client, net):
    """Found by tools/mutate.py: dropping the max(0, ...) clamp in search() passed every other test.

    Three layers have to agree, because a peer controls what it forwards: the REST door refuses a
    negative radius outright, discover() treats it as local, and search() clamps it even when called
    directly. The clamp is the last of the three and the only one a hostile peer cannot route around.
    """
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    net(zurich)

    assert client.get("/api/hive/discover", params=ASK | {"radius": -1}).status_code == 422

    for bad in (-1, -3, -99):
        assert set(hive.discover(**ASK, radius=bad)) == {"matches", "excluded", "ranking_policy"}
        assert zurich.asks == [], f"discover(radius={bad}) must not reach a peer"

    for bad in (-1, -99):
        report = asyncio.run(federation.search(ASK, radius=bad))["federation"]
        assert report["radius"] == 0, f"search(radius={bad}) must clamp to a local search"
        assert report["asked"] == [] and zurich.asks == [], "a clamped search asks nobody"


def test_radius_zero_never_asks_a_peer_even_when_peers_are_configured(client, net):
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    net(zurich)
    found = hive.discover(**ASK, radius=0)
    assert zurich.asks == [] and "federation" not in found


# ---------------------------------------------------------------- reaching peers


async def _profile_over_http(handler, base_url: str) -> dict:
    """Run the real HttpTransport against an in-memory peer, so its parser is exercised for real."""
    client = httpx.AsyncClient  # bind before patching, or the replacement calls itself
    with mock.patch.object(httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(handler), **kw)):
        return await federation.HttpTransport().profile(base_url)


def test_the_real_http_transport_parses_a_peers_discovery_document():
    """Found by tools/mutate.py: the fakes replace HttpTransport, so its parser had no test at all.

    Blanking owner_keys here passed every federation test, because FakeNet never runs this code.
    In production this parser is what supplies the keys every relayed card is checked against,
    so a silent {} would turn verification into a rubber stamp.
    """
    doc = {
        "federation": {"hub_id": "zurich", "verification": "signed", "paid_placement": False},
        "ranking_policy": "No paid placement.",
        "owner_keys": {"hotel-limmat": "AAAAkey", "cafe-null": None, "cafe-ok": "BBBBkey"},
    }

    async def handler(request):
        assert request.url.path == "/.well-known/hive.json", "the peer is read from the well-known door"
        return httpx.Response(200, json=doc)

    profile = asyncio.run(_profile_over_http(handler, "https://zurich.example/"))

    assert profile["hub_id"] == "zurich"
    assert profile["verification"] == "signed" and profile["paid_placement"] is False
    assert profile["ranking_policy"] == "No paid placement."
    assert profile["owner_keys"] == {
        "hotel-limmat": "AAAAkey",
        "cafe-ok": "BBBBkey",
    }, "every string key is kept and non-string values dropped"


def test_the_http_transport_falls_back_to_the_url_when_a_peer_declares_no_hub_id():
    """A peer that publishes nothing still gets a stable identity, so trust can be recorded against it."""

    async def handler(request):
        return httpx.Response(200, json={})

    profile = asyncio.run(_profile_over_http(handler, "https://quiet.example/"))

    assert profile["hub_id"] == "https://quiet.example"
    assert profile["owner_keys"] == {} and profile["ranking_policy"] == ""
    assert profile["verification"] is None and profile["paid_placement"] is None


def test_every_entity_carries_a_name_a_description_and_a_rating(client, net):
    """The protocol says every entity has these three, so a hub and a business read the same way."""
    found = hive.discover(**ASK)

    assert found["matches"], "the seed must answer this ask"
    for match in found["matches"] + found["excluded"]:
        assert match["name"], "every business is named"
        assert "description" in match and isinstance(match["description"], str)
        assert "rating" in match and "rating_count" in match
        assert match["rating"] is None or 0 <= match["rating"] <= 5


def test_a_business_rating_stays_empty_until_a_signed_receipt_produces_one():
    """No booking, no review, and therefore no rating. The field exists; it is simply not earned yet."""
    fresh = [m for m in hive.discover(**ASK)["matches"] if m["rating_count"] == 0]

    assert fresh, "the seed should hold at least one business nobody has reviewed"
    assert all(m["rating"] is None for m in fresh), "an unreviewed business has no rating, not a zero"


def test_the_discovery_document_names_and_describes_this_hive(client):
    """A peer reads these to show who answered, so they travel with the federation block."""
    doc = client.get("/.well-known/hive.json").json()

    assert doc["name"] and doc["description"], "a Hive says who it is at its own door"
    assert doc["federation"]["name"] == doc["name"]
    assert doc["federation"]["description"] == doc["description"]


def test_a_peer_cannot_declare_its_own_rating(client, net):
    """The one field a peer may not set. A name and a description are its word; a rating is ours.

    If a hub could publish `rating: 1.0` the whole trust layer would be decorative, so the parser
    never reads a rating off the wire and the asked-peer entry carries what reputation.py computed.
    """
    liar = FakeHive("liar", cards=[_card("hotel-liar", "Hotel Liar (fictional)")])
    liar_profile = liar.profile
    liar.profile = lambda: {
        **liar_profile(),
        "name": "Totally Legitimate Hive",
        "description": "The best Hive.",
        "rating": 1.0,
        "trust": 1.0,
    }
    net(liar)

    found = hive.discover(**ASK, radius=1)
    asked = found["federation"]["asked"]

    assert asked, "the peer was asked"
    entry = asked[0]
    assert entry["name"] == "Totally Legitimate Hive", "a peer's own name is taken at its word"
    assert entry["description"] == "The best Hive.", "so is its description"
    assert entry["rating"] < 1.0, "but not its rating: an unproven peer starts at trust on first use"
    assert entry["rating"] == pytest.approx(reputation.NEW_PEER_TRUST, abs=0.2)


def test_a_forwarded_query_carries_the_whole_ask(client, net):
    """Found by tools/mutate.py: inverting the filter in hop_params() forwarded an empty ask."""
    params = federation.hop_params(ASK, radius=1, budget_ms=900, seen=["basel"])

    for key, value in ASK.items():
        assert params[key] == value, f"a hop dropped {key}: a peer would answer a different question"
    assert params["radius"] == 1 and params["budget_ms"] == 900 and params["seen"] == ["basel"]
    assert None not in params.values() and "" not in params.values(), "empty values are not forwarded"


def test_a_peers_declared_ranking_policy_is_read_not_discarded(client, net):
    """Found by tools/mutate.py: blanking ranking_policy in the profile passed every other test.

    It is load-bearing. Paid placement is detected from this string, so a hub that drops it
    silently stops downgrading peers that sell rank.
    """
    seller = FakeHive("seller", cards=[_card("hotel-paid", "Hotel Paid (fictional)")], paid=True)
    net(seller)

    profile = asyncio.run(federation.DEFAULT_TRANSPORT.profile(seller.url))
    assert profile["ranking_policy"], "the peer's declared policy must survive the hop, not arrive blank"
    assert reputation.hub_trust("seller", profile)["factors"]["open_ranking"] < 0, "selling rank must cost trust"


def test_radius_one_reaches_a_direct_peer(client, net):
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    net(zurich)
    local = _ids(hive.discover(**ASK, radius=0))

    found = hive.discover(**ASK, radius=1)
    assert local <= _ids(found), "a federated search still shows everything the local Hive found"
    assert "hotel-limmat" in _ids(found)
    assert zurich.asks[0]["radius"] == 0, "the last hop may not forward any further"
    assert zurich.asks[0]["seen"] == ["basel"], "every hop appends its own hub id for the next one"

    far, near = _by_id(found, "hotel-limmat"), _by_id(found, next(iter(local)))
    assert far["provenance"]["path"] == ["zurich", "basel"] and far["hops"] == 1
    assert near["provenance"]["path"] == ["basel"] and near["hops"] == 0
    assert found["federation"]["radius"] == 1 and found["federation"]["hub"] == "basel"
    assert [p["hub"] for p in found["federation"]["asked"]] == ["zurich"]


def test_radius_two_reaches_peers_of_peers_and_stops_there(client, net):
    bern = FakeHive("bern", cards=[_card("hotel-aare", "Hotel Aare (fictional)")])
    geneva = FakeHive("geneva", cards=[_card("hotel-leman", "Hotel Leman (fictional)")])
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")], relays=[bern])
    bern.relays = [geneva]
    net(zurich, bern, geneva, peers=[zurich])

    one = _ids(hive.discover(**ASK, radius=1))
    assert "hotel-limmat" in one and "hotel-aare" not in one

    found = hive.discover(**ASK, radius=2)
    assert {"hotel-limmat", "hotel-aare"} <= _ids(found)
    assert "hotel-leman" not in _ids(found), "radius 2 is two hops, not three"
    assert _by_id(found, "hotel-aare")["provenance"]["path"] == ["bern", "zurich", "basel"]
    assert _by_id(found, "hotel-aare")["hops"] == 2


def test_a_radius_over_the_cap_is_clamped(client, net):
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    net(zurich)
    found = hive.discover(**ASK, radius=99)
    assert found["federation"]["radius"] == federation.MAX_RADIUS == 3
    assert zurich.asks[0]["radius"] == federation.MAX_RADIUS - 1


def test_a_cycle_in_the_peer_graph_terminates(client, net):
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    bern = FakeHive("bern", cards=[_card("hotel-aare", "Hotel Aare (fictional)")])
    zurich.relays, bern.relays = [bern], [zurich]  # a cycle, like the real peer graph
    net(zurich, bern, peers=[zurich])

    found = hive.discover(**ASK, radius=3)
    assert {"hotel-limmat", "hotel-aare"} <= _ids(found)
    assert len(zurich.asks) == 1 and len(bern.asks) == 1, "a hub already in seen is never asked twice"
    assert bern.asks[0]["seen"] == ["basel", "zurich"]


def test_a_peer_already_in_seen_is_never_asked(client, net):
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    bern = FakeHive("bern", cards=[_card("hotel-aare", "Hotel Aare (fictional)")])
    net(zurich, bern)
    # This hub is a hop in someone else's search: bern has already been asked upstream.
    found = hive.discover(**ASK, radius=1, seen=["bern"])
    assert bern.asks == [] and len(zurich.asks) == 1
    assert "hotel-aare" not in _ids(found) and "hotel-limmat" in _ids(found)
    assert found["federation"]["seen"] == ["bern", "basel"]


# ---------------------------------------------------------------- budgets and breadth


def test_a_slow_peer_is_dropped_without_failing_the_query(client, net, monkeypatch):
    slow = FakeHive("slow", cards=[_card("hotel-slow", "Hotel Slow (fictional)")], delay_ms=400)
    quick = FakeHive("quick", cards=[_card("hotel-quick", "Hotel Quick (fictional)")])
    net(slow, quick)

    # This test is about the peers' deadline, but the budget also pays for the local search: of 250 ms, MIN_FORWARD_MS
    # has to be left, so a local search over 100 ms means no peer is asked at all. On a loaded machine that read as the
    # quick peer failing (#140). So the local search is slow on purpose and the clock charging for it is stopped, which
    # leaves the machine's speed out of it. Without the stopped clock this fails every run, not one run in ten. The
    # peers' own deadline is still real time: `wait_for` runs on the loop's clock, not this one.
    local_search = federation._local

    def on_a_loaded_machine(ask, hub):
        time.sleep(0.2)
        return local_search(ask, hub)

    monkeypatch.setattr(federation, "_local", on_a_loaded_machine)
    monkeypatch.setattr(federation, "perf_counter", lambda: 0.0)

    found = hive.discover(**ASK, radius=1, budget_ms=250)
    assert _ids(hive.discover(**ASK, radius=0)) <= _ids(found), "the local answer survives a dead peer"
    assert "hotel-quick" in _ids(found) and "hotel-slow" not in _ids(found)
    dropped = {d["hub"]: d["reason"] for d in found["federation"]["dropped"]}
    assert "slow" in dropped and "deadline" in dropped["slow"]
    assert reputation.observed("slow").timeouts == 1, "missing a deadline costs the peer trust"


def test_a_hop_refuses_to_forward_when_the_budget_is_already_spent(client, net):
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    net(zurich)
    found = hive.discover(**ASK, radius=2, budget_ms=1)
    assert zurich.asks == [], "no hop is worth making with no time left"
    assert any("budget" in d["reason"] for d in found["federation"]["dropped"])
    assert _ids(found) == _ids(hive.discover(**ASK, radius=0))


class SlowRegistries(FakeNet):
    """A FakeNet whose discovery documents take `delays[url]` ms to arrive: a cold cache on a slow link."""

    def __init__(self, *hubs: FakeHive, delays: dict[str, float]):
        super().__init__(*hubs)
        self.delays = delays

    async def profile(self, base_url: str) -> dict:
        await asyncio.sleep(self.delays.get(base_url, 0) / 1000)
        return await super().profile(base_url)


def _slow_registries(monkeypatch, net, *hubs: FakeHive, peers: list[FakeHive], delays: dict[str, float]):
    net(*hubs, peers=peers)
    transport = SlowRegistries(*hubs, delays=delays)
    monkeypatch.setattr(federation, "DEFAULT_TRANSPORT", transport)
    return transport


def test_a_peer_whose_registry_misses_the_deadline_is_not_asked(client, net, monkeypatch):
    """#112: a cold registry lookup is inside the whole-query budget, and no search starts after it."""
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    _slow_registries(monkeypatch, net, zurich, peers=[zurich], delays={zurich.url: 3000})

    found = hive.discover(**ASK, radius=1, budget_ms=400)
    assert found["federation"]["elapsed_ms"] < 1200, "the query outlived its budget waiting for a registry"
    assert zurich.asks == [], "a search was forwarded after the deadline"
    assert _ids(found) == _ids(hive.discover(**ASK, radius=0)), "the local answer survives"
    reasons = [d["reason"] for d in found["federation"]["dropped"]]
    assert any("deadline" in r for r in reasons), reasons
    assert not any("no key registry" in r for r in reasons), "running out of time is not a missing registry"


def test_the_hop_budget_is_what_is_left_after_peer_selection(client, net, monkeypatch):
    """#112: the budget forwarded is recomputed after the registry lookups, not carried over from before."""
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    _slow_registries(monkeypatch, net, zurich, peers=[zurich], delays={zurich.url: 600})

    found = hive.discover(**ASK, radius=1, budget_ms=1500)
    assert len(zurich.asks) == 1 and "hotel-limmat" in _ids(found)
    assert zurich.asks[0]["budget_ms"] <= 1500 - 600, "the peer was promised time this hub had already spent"


def test_a_slow_origin_registry_cannot_stretch_the_query(client, net, monkeypatch):
    """#112: verifying a relayed card against its origin's registry is inside the budget too, and blameless."""
    bern = FakeHive("bern", cards=[_card("hotel-aare", "Hotel Aare (fictional)")])
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")], relays=[bern])
    _slow_registries(monkeypatch, net, zurich, bern, peers=[zurich], delays={bern.url: 3000})

    found = hive.discover(**ASK, radius=2, budget_ms=500)
    assert found["federation"]["elapsed_ms"] < 1300, "the query outlived its budget verifying a card"
    assert "hotel-limmat" in _ids(found) and "hotel-aare" not in _ids(found)
    rejected = {r["card_id"]: r["reason"] for r in found["federation"]["rejected"]}
    assert "deadline" in rejected["hotel-aare"], rejected
    assert reputation.observed("zurich").invalid == 0, "our deadline is not the carrier's fault"


def test_a_slow_registry_does_not_spend_a_healthy_peers_turn(client, net, monkeypatch):
    """#228 review: the peer whose registry is ready is searched at once, not after the slow one gives up."""
    stuck = FakeHive("stuck", cards=[_card("hotel-stuck", "Hotel Stuck (fictional)")])
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    _slow_registries(monkeypatch, net, stuck, zurich, peers=[stuck, zurich], delays={stuck.url: 3000})

    found = hive.discover(**ASK, radius=1, budget_ms=500)
    assert "hotel-limmat" in _ids(found), found["federation"]["dropped"]
    assert len(zurich.asks) == 1 and zurich.asks[0]["budget_ms"] > 300, "the healthy peer got the whole budget"
    assert stuck.asks == []
    assert found["federation"]["elapsed_ms"] < 1300


def test_a_slow_peer_does_not_cost_a_healthy_relay_its_verification(client, net, monkeypatch):
    """#228 review: a relay that answered is verified while a slower peer is still searching."""
    bern = FakeHive("bern", cards=[_card("hotel-aare", "Hotel Aare (fictional)")])
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")], relays=[bern])
    slow = FakeHive("slow", cards=[_card("hotel-slow", "Hotel Slow (fictional)")], delay_ms=3000)
    _slow_registries(monkeypatch, net, zurich, bern, slow, peers=[zurich, slow], delays={bern.url: 200})

    found = hive.discover(**ASK, radius=2, budget_ms=700)
    assert {"hotel-limmat", "hotel-aare"} <= _ids(found), found["federation"]["rejected"]
    assert "hotel-slow" not in _ids(found)
    dropped = {d["hub"]: d["reason"] for d in found["federation"]["dropped"]}
    assert "deadline" in dropped["slow"]


def test_only_the_top_peers_by_trust_are_asked(client, net):
    honest = [FakeHive(f"honest{i}", cards=[_card(f"hotel-h{i}", f"Hotel H{i} (fictional)")]) for i in range(4)]
    sellers = [
        FakeHive(f"seller{i}", cards=[_card(f"hotel-s{i}", f"Hotel S{i} (fictional)")], paid=True) for i in (0, 1)
    ]
    net(*honest, *sellers, peers=[sellers[0], honest[0], honest[1], sellers[1], honest[2], honest[3]])

    found = hive.discover(**ASK, radius=1)
    assert len(found["federation"]["asked"]) == federation.PEERS_PER_HOP == 4
    assert {p["hub"] for p in found["federation"]["asked"]} == {h.hub_id for h in honest}
    assert all(s.asks == [] for s in sellers), "a hub that sells rank is the last this one spends its budget on"


# ---------------------------------------------------------------- trust at the destination


def test_a_tampered_card_relayed_by_a_peer_is_rejected(client, net):
    liar = FakeHive(
        "liar",
        cards=[_card("hotel-liar", "Hotel Liar (fictional)"), _card("hotel-true", "Hotel True (fictional)")],
        tamper=["hotel-liar"],
    )
    net(liar)

    found = hive.discover(**ASK, radius=1)
    assert "hotel-liar" not in _ids(found), "a relaying hub cannot forge a card, only withhold it"
    assert "hotel-true" in _ids(found), "the cards it did not touch still count"
    rejected = found["federation"]["rejected"]
    assert [r["card_id"] for r in rejected] == ["hotel-liar"] and rejected[0]["hub"] == "liar"
    assert reputation.observed("liar").invalid == 1
    assert reputation.hub_trust("liar", liar.profile())["factors"]["disputes"] < 0


def test_a_card_is_verified_against_its_own_hubs_registry_not_the_carriers(client, net):
    deep = FakeHive("deep", cards=[_card("hotel-deep", "Hotel Deep (fictional)")])
    middle = FakeHive("middle", relays=[deep])
    transport = net(deep, middle, peers=[middle])

    found = hive.discover(**ASK, radius=2)
    assert "hotel-deep" in _ids(found)
    assert deep.url in transport.profiles, "the key came from the subject's own hub, fetched directly"


def test_the_three_rank_factors_are_surfaced_separately(client, net):
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    net(zurich)
    found = hive.discover(**ASK, radius=1)

    far = _by_id(found, "hotel-limmat")
    breakdown = far["score_breakdown"]
    trust = reputation.hub_trust("zurich", zurich.profile())["trust"]
    assert breakdown["local_relevance"] == 60.0
    assert breakdown["hub_path_trust"] == pytest.approx(trust, abs=0.05)
    assert breakdown["hop_decay"] == reputation.hop_decay(1)
    expected = breakdown["local_relevance"] * breakdown["hub_path_trust"] * breakdown["hop_decay"]
    assert far["federated_score"] == pytest.approx(expected, abs=0.01)
    assert far["score"] == 60.0, "the local hub's own score is kept, not overwritten"
    assert any("hub_path_trust" in why or "zurich" in why for why in far["why"])

    near = _by_id(found, next(iter(_ids(hive.discover(**ASK, radius=0)))))
    assert near["score_breakdown"]["hub_path_trust"] == 1.0 and near["score_breakdown"]["hop_decay"] == 1.0
    assert found["federation"]["hub_trust"]["zurich"]["why"], "every hub's trust can be explained"


def test_offering_the_queried_thing_outranks_a_free_pass_even_across_a_hop(client, net):
    """The ranking bug two live hubs showed: a query for "dataviz" answered with eight hotels.

    An ask with no dates, no budget and no features has nothing to verify, so nothing may collect
    hive.CONSTRAINT_POINTS for passing it. Then relevance decides — and it has to keep deciding
    after the federated discount, because a remote score is multiplied by hub trust and hop decay.
    That is the arithmetic that buried the one person who offers a dataviz sprint: an unearned 50
    at home beat an earned score discounted for distance.
    """
    hive.publish(_offer_card("person-dataviz", "Vera S. (fictional)", "Two-week dataviz sprint"))
    local = hive.discover(query="dataviz")
    here = _by_id(local, "person-dataviz")
    assert local["matches"][0]["id"] == "person-dataviz", [(m["id"], m["score"]) for m in local["matches"][:3]]
    assert here["why"] == ["offers dataviz"]
    assert all(m["score_breakdown"]["constraints"] == 0 for m in local["matches"]), "nothing was checked"

    # The same person on the far hub, reporting the score this hub's own scorer gives her.
    zurich = FakeHive(
        "zurich",
        cards=[_offer_card("person-dataviz-zh", "Vera S. in Zürich (fictional)", "Two-week dataviz sprint")],
        match={"score": here["score"], "score_breakdown": here["score_breakdown"], "why": here["why"]},
    )
    net(zurich)

    far = hive.discover(query="dataviz", radius=1)
    ranked = [m["id"] for m in far["matches"]]
    hotels = [m["id"] for m in far["matches"] if m["kind"] == "hotel"]
    assert hotels, "the seeded hotels still answer, they just have nothing to do with dataviz"
    assert ranked.index("person-dataviz-zh") < min(ranked.index(h) for h in hotels)

    # And the discount was really applied: distance still costs her, it just no longer buries her.
    remote = _by_id(far, "person-dataviz-zh")
    assert remote["score_breakdown"]["hub_path_trust"] < 1.0 and remote["federated_score"] < remote["score"]
    assert ranked.index("person-dataviz") < ranked.index("person-dataviz-zh"), "the near one first"


def test_a_hub_that_sells_rank_cannot_outrank_an_honest_one(client, net):
    honest = FakeHive("honest", cards=[_card("hotel-honest", "Hotel Honest (fictional)")])
    seller = FakeHive("seller", cards=[_card("hotel-seller", "Hotel Seller (fictional)")], paid=True)
    net(honest, seller)

    found = hive.discover(**ASK, radius=1)
    ranked = [m["id"] for m in found["matches"]]
    assert ranked.index("hotel-honest") < ranked.index("hotel-seller")
    assert _by_id(found, "hotel-seller")["score"] == _by_id(found, "hotel-honest")["score"]  # same local score
    assert any("paid placement" in why for why in found["federation"]["hub_trust"]["seller"]["why"])


# ---------------------------------------------------------------- one card, several routes


def test_dedup_keeps_the_shortest_path(client, net):
    deep = FakeHive("deep", cards=[_card("hotel-deep", "Hotel Deep (fictional)")])
    detour = FakeHive("detour", relays=[deep])
    net(deep, detour, peers=[detour, deep])  # the long way round answers first, and still loses

    found = hive.discover(**ASK, radius=2)
    arrivals = [m for m in found["matches"] if m["id"] == "hotel-deep"]
    assert len(arrivals) == 1, "the same card by two routes is one result"
    assert arrivals[0]["provenance"]["path"] == ["deep", "basel"] and arrivals[0]["hops"] == 1
    assert any("detour" in str(route) for route in arrivals[0]["provenance"]["also_reached_by"])


def test_the_shortest_route_wins_and_a_tie_goes_to_the_more_trusted_chain():
    near = {"hops": 1, "score_breakdown": {"hub_path_trust": 0.2}}
    far = {"hops": 2, "score_breakdown": {"hub_path_trust": 0.9}}
    assert federation._shorter(near, far) and not federation._shorter(far, near)
    good = {"hops": 2, "score_breakdown": {"hub_path_trust": 0.45}}
    bought = {"hops": 2, "score_breakdown": {"hub_path_trust": 0.05}}
    assert federation._shorter(good, bought) and not federation._shorter(bought, good)


def test_dedup_breaks_a_tie_on_the_more_trusted_carrier(client, net):
    deep = FakeHive("deep", cards=[_card("hotel-deep", "Hotel Deep (fictional)")])
    good = FakeHive("good", relays=[deep])
    seller = FakeHive("seller", relays=[deep], paid=True)
    net(deep, good, seller, peers=[good, seller])

    found = hive.discover(**ASK, radius=2)
    arrivals = [m for m in found["matches"] if m["id"] == "hotel-deep"]
    assert len(arrivals) == 1 and arrivals[0]["hops"] == 2
    assert arrivals[0]["provenance"]["path"] == ["deep", "good", "basel"]


def test_this_hives_own_rest_door_is_what_a_hop_talks_to(client):
    """The wire between two hubs, over the real endpoint: what HttpTransport sends, this Hive answers."""
    ask = {"kind": "hotel", "features": ["dog-friendly"], "check_in": "2027-04-01", "check_out": "2027-04-03"}
    params = federation.hop_params(ask, radius=1, budget_ms=900, seen=["upstream"])
    answer = client.get("/api/hive/discover", params=params)
    assert answer.status_code == 200
    out = answer.json()

    report = out["federation"]
    assert report["seen"] == ["upstream", config.HIVE_HUB_ID], "a hop names itself for the next one"
    assert report["radius"] == 1 and report["budget_ms"] == 900
    # Everything the hub on the other side needs to verify a card itself, and to say where it came from.
    pins = client.get("/.well-known/hive.json").json()
    assert pins["federation"]["hub_id"] == config.HIVE_HUB_ID
    for match in out["matches"]:
        assert hive.verify_pinned(match["card"], pins["owner_keys"])
        assert match["provenance"]["path"] == [config.HIVE_HUB_ID] and match["hops"] == 0
        assert set(match["score_breakdown"]) >= {"local_relevance", "hub_path_trust", "hop_decay"}


def test_a_ruleset_still_narrows_a_federated_answer(client, net):
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    net(zurich)
    out = _mcp("hive_discover", ASK | {"radius": 1, "ruleset": "dogs-verified"})
    assert out["ruleset"]["id"] == "dogs-verified"
    # Nobody has vouched for the peer's dog-friendly claim, so the ruleset leaves it out, with the reason.
    assert "hotel-limmat" not in {m["id"] for m in out["matches"]}
    assert any(e["id"] == "hotel-limmat" for e in out["excluded"])


# ---------------------------------------------------------------- what two real hubs showed


def test_a_forwarded_query_carries_the_signed_card_but_a_direct_one_does_not(client):
    """Found by running two real hubs, not by any fake.

    The last hop of a federated search always arrives as radius 0, and a radius-0 answer omits
    `card` to stay byte-identical for direct callers. So a peer answered with matches that could
    not be verified, and the asking hub rejected every one of them with "no card to check against
    the owner's key". Every FakeHive here includes `card`, so nothing caught it.

    Backward compatibility is owed to a direct caller, not to a hop. `seen` is what tells them
    apart: a peer that forwarded a query has already put itself in it.
    """
    direct = hive.discover(**ASK)
    assert set(direct) == {"matches", "excluded", "ranking_policy"}
    assert all("card" not in m for m in direct["matches"]), "a direct caller's answer is unchanged"

    forwarded = hive.discover(**ASK, seen=["basel"])
    assert set(forwarded) == {"matches", "excluded", "ranking_policy"}, "the envelope is the same"
    assert forwarded["matches"], "the seed must answer this ask"
    for match in forwarded["matches"]:
        card = match.get("card")
        assert isinstance(card, dict), f"{match['id']} travelled to a peer with no card to verify"
        assert card["id"] == match["id"]
        assert card.get("trust", {}).get("signature"), "the card must carry the signature it is checked by"


def test_a_card_that_travelled_verifies_against_the_origin_registry(client):
    """The point of carrying the card: the far end can check it against the owner's pinned key."""
    forwarded = hive.discover(**ASK, seen=["basel"])
    pins = hive.owner_keys()

    for match in forwarded["matches"]:
        assert hive.verify_pinned(match["card"], pins), f"{match['id']} would be rejected by a peer"


def test_a_peer_still_starting_costs_nobody_their_reputation(client, net):
    """The bug this guards: a fresh three-hub stack rejected every relayed card and blamed the carrier.

    A hub answers /.well-known/hive.json as soon as it binds, which is before it has registered anything, so a
    peer asked in that window gets a real profile with an empty key registry. Nothing can be verified against it.
    That much is correct - an unverifiable card must not pass. What was wrong is who paid for it: the carrier was
    charged `record_invalid` per card, and because reputation outlives the request, a peer that happened to be
    asked half a second early wore `trust 0.05` and "41 of 82 relayed cards failed verification here" for the
    rest of the process, which dropped a real match's federated score from 4.39 to 0.36.
    """
    waking = FakeHive("waking", cards=[_card("hotel-waking", "Hotel Waking (fictional)")], starting_up=True)
    net(waking)

    found = hive.discover(**ASK, radius=1)

    assert "hotel-waking" not in _ids(found), "a card we cannot check does not pass"
    rejected = found["federation"]["rejected"]
    assert [r["card_id"] for r in rejected] == ["hotel-waking"]
    assert "empty" in rejected[0]["reason"], f"the reason should name the real cause, got {rejected[0]['reason']!r}"
    assert reputation.observed("waking").invalid == 0, "a registry we could not read is not the carrier's fault"
    assert reputation.hub_trust("waking", waking.profile())["factors"]["disputes"] == 0


def test_a_tamper_is_still_charged_even_though_a_slow_start_is_not(client, net):
    """The other half: making the empty case blameless must not make tampering free."""
    liar = FakeHive("liar", cards=[_card("hotel-liar", "Hotel Liar (fictional)")], tamper=["hotel-liar"])
    net(liar)

    hive.discover(**ASK, radius=1)

    assert reputation.observed("liar").invalid == 1, "altering a signed card is still the carrier's doing"


def test_an_empty_registry_is_read_once_per_query_and_recovers_next_time(client, net):
    """A startup miss must not fetch the same registry for every relayed card or poison the next search."""
    cards = [_card(f"hotel-waking-{i}", f"Hotel Waking {i} (fictional)") for i in range(12)]
    waking = FakeHive("waking", cards=cards, starting_up=True)
    transport = net(waking)

    found = hive.discover(**ASK, radius=1)

    assert not {card["id"] for card in cards} & _ids(found)
    assert {r["card_id"] for r in found["federation"]["rejected"]} == {card["id"] for card in cards}
    assert transport.profiles.count(waking.url) == 1
    assert reputation.observed("waking").invalid == 0

    waking.starting_up = False
    recovered = hive.discover(**ASK, radius=1)

    assert {card["id"] for card in cards} <= _ids(recovered)
    assert transport.profiles.count(waking.url) == 2
    assert reputation.observed("waking").invalid == 0
