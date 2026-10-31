"""The hub directory: the picker's list, and whether it tells the truth about peers.

A peer publishes its identity in `/.well-known/hive.json`. The directory used to derive a peer's name from the
URL it was configured with, so a picker showed `127.0.0.1:8421` for a hub that calls itself `zurich`. These tests
pin the fix and the three honesty rules around it: a peer we have not asked stays unknown rather than being
guessed at or shown as zero, a peer that stops answering keeps its last good answer and is marked stale, and a
peer that does not answer at all never makes reading the directory slow.

Every peer here is in-process: nothing opens a socket.
"""

import asyncio
from datetime import UTC, datetime
from time import perf_counter
from unittest import mock

import httpx
import pytest

from app import admin, config, federation, registration


class Peer:
    """One in-process peer Hive, as far as its discovery document goes."""

    def __init__(self, hub_id: str, name: str, entities: int | None = None, admission: str = "open", **extra):
        self.hub_id = hub_id
        self.url = f"http://10.0.0.1:{8420 + abs(hash(hub_id)) % 50}/"
        self.doc = {
            "hub_id": hub_id,
            "name": name,
            "description": f"What {hub_id} carries.",
            "verification": "signed",
            "admission": admission,
            "entities": entities,
            "paid_placement": False,
            "ranking_policy": "",
            "owner_keys": {},
            **extra,
        }
        self.asks = 0
        self.answers = True
        self.hangs = False


class Net:
    """A transport over in-process peers. A peer can refuse to answer, or hang for ever."""

    def __init__(self, *peers: Peer):
        self.peers = {p.url: p for p in peers}

    async def profile(self, base_url: str) -> dict:
        peer = self.peers[base_url]
        peer.asks += 1
        if peer.hangs:
            await asyncio.sleep(3600)
        if not peer.answers:
            raise OSError("connection refused")
        return dict(peer.doc)

    async def search(self, base_url, ask, radius, budget_ms, seen) -> dict:
        return {"matches": [], "excluded": []}


@pytest.fixture
def peers(client, monkeypatch):
    """Configure a set of peers, ask them once, and leave nothing cached behind.

    `client` only to open the database the home row counts its entities from; nothing here goes over HTTP.
    """

    def wire(*peers: Peer, ask: bool = True) -> Net:
        net = Net(*peers)
        monkeypatch.setattr(config, "HIVE_PEER_URLS", [p.url for p in peers])
        monkeypatch.setattr(federation, "DEFAULT_TRANSPORT", net)
        federation.forget()
        if ask:
            asyncio.run(federation.ask_peers(net))
        return net

    yield wire
    federation.forget()


# ---------------------------------------------------------------- the names


def test_a_peer_is_listed_under_the_hub_id_it_publishes_not_its_address(peers):
    """The reported bug: the picker showed `172.20.10.7:8421` for a hub that calls itself `zurich`."""
    peers(Peer("zurich", "Adobee Hive (zurich)"), Peer("bern", "Adobee Hive (bern)"))

    listed = {row["hub"]: row for row in admin.directory()["hubs"] if not row["home"]}

    assert set(listed) == {"zurich", "bern"}
    assert listed["zurich"]["name"] == "Adobee Hive (zurich)"
    assert listed["zurich"]["description"] == "What zurich carries."
    assert listed["bern"]["name"] == "Adobee Hive (bern)"


def test_what_a_peer_carries_comes_from_the_peer(peers):
    """`entities` is the peer's own published count, not something this hub works out for it."""
    peers(Peer("zurich", "Adobee Hive (zurich)", entities=14))

    row = next(r for r in admin.directory()["hubs"] if r["hub"] == "zurich")

    assert row["entities"] == 14
    assert row["admission"] == "open" and row["accepting"] is True


def test_a_peer_that_publishes_no_count_keeps_a_null_one(peers):
    """A missing count is missing. Zero is a claim, and we do not have it."""
    peers(Peer("zurich", "Adobee Hive (zurich)", entities=None))

    assert next(r for r in admin.directory()["hubs"] if r["hub"] == "zurich")["entities"] is None


def test_a_closed_peer_is_reported_closed_and_an_open_one_open(peers):
    peers(Peer("shut", "Shut", admission="closed"), Peer("open", "Open", admission="open"))

    rows = {r["hub"]: r for r in admin.directory()["hubs"]}

    assert rows["shut"]["accepting"] is False and rows["shut"]["admission"] == "closed"
    assert rows["open"]["accepting"] is True


def test_a_peer_declaring_a_policy_this_hub_does_not_know_is_not_passed_on(peers):
    """A peer's text is data. An admission policy outside the published list reads as unknown, never as a word
    the picker would have to find a sentence for."""
    peers(Peer("odd", "Odd", admission="pay-us"))

    row = next(r for r in admin.directory()["hubs"] if r["hub"] == "odd")

    assert row["admission"] == "unknown" and row["accepting"] is None


# ---------------------------------------------------------------- never asked, and never invented


def test_a_peer_that_has_never_been_asked_says_so_rather_than_guessing(peers):
    peers(Peer("zurich", "Adobee Hive (zurich)"), ask=False)

    row = next(r for r in admin.directory()["hubs"] if not r["home"])

    assert row["last_asked"] is None and row["last_asked_ok"] is None
    assert row["name"] == "" and row["description"] == ""
    assert row["entities"] is None, "never zero"
    assert row["accepting"] is None, "not asked is not the same as not accepting"
    assert row["admission"] == "unknown"
    assert row["known"] is False
    assert row["hub"] == federation.url_label(config.HIVE_PEER_URLS[0]), "the URL stays as the label"


def test_an_unreachable_peer_keeps_the_url_as_its_label_and_stays_unknown(peers):
    """It was asked, it did not answer: the ask is recorded, and nothing is invented from it."""
    dead = Peer("ghost", "Never seen")
    dead.answers = False
    peers(dead)

    row = next(r for r in admin.directory()["hubs"] if not r["home"])

    assert row["last_asked"] is not None and row["last_asked_ok"] is False
    assert row["hub"] == federation.url_label(dead.url)
    assert row["entities"] is None and row["accepting"] is None
    assert row["stale"] is False, "nothing good was ever shown, so there is nothing stale to warn about"


# ---------------------------------------------------------------- when it was last asked


def test_a_peer_that_answered_carries_the_moment_it_was_asked(peers):
    peers(Peer("zurich", "Adobee Hive (zurich)", entities=14))

    row = next(r for r in admin.directory()["hubs"] if r["hub"] == "zurich")

    assert row["last_asked_ok"] is True
    asked = datetime.fromisoformat(row["last_asked"])
    assert asked.tzinfo is not None, "ISO 8601 with a zone, so a browser can render it in local time"
    assert abs((datetime.now(UTC) - asked).total_seconds()) < 60


def test_a_failed_ask_keeps_the_last_good_answer_and_marks_it_stale(peers):
    """ "Asked a minute ago, no answer, last known 14 entities" beats reverting the row to unknown."""
    peer = Peer("zurich", "Adobee Hive (zurich)", entities=14)
    net = peers(peer)

    peer.answers = False
    asyncio.run(federation.ask_peers(net))
    row = next(r for r in admin.directory()["hubs"] if r["hub"] == "zurich")

    assert row["name"] == "Adobee Hive (zurich)" and row["entities"] == 14, "the last good answer is kept"
    assert row["last_asked_ok"] is False and row["stale"] is True
    assert row["last_answered"] is not None, "the row can say how old the answer it is showing is"
    assert row["last_answered"] <= row["last_asked"], "the answer predates the ask that failed"


def test_the_home_row_has_nothing_to_ask_and_says_so(peers):
    peers(Peer("zurich", "Adobee Hive (zurich)"))

    home = next(r for r in admin.directory()["hubs"] if r["home"])

    assert home["last_asked"] is None and home["stale"] is False
    assert home["name"] == config.HIVE_NAME
    assert home["admission"] in registration.POLICIES


def test_the_directory_says_how_often_it_asks_so_an_old_number_is_explainable(peers):
    peers(Peer("zurich", "Adobee Hive (zurich)"))

    assert admin.directory()["asked_every_seconds"] == config.PEER_ASK_SECONDS


def test_the_operator_can_read_why_a_number_is_two_minutes_old(peers):
    """The intervals are on the settings form, where an operator looks when a count looks out of date."""
    keys = {f["key"]: f for f in admin.settings()["fields"]}

    for key in ("peer_ask_seconds", "peer_stale_after_seconds", "peer_ask_timeout_seconds"):
        assert keys[key]["help"], key
        assert keys[key]["value"] is not None


# ---------------------------------------------------------------- a dead peer never makes it slow


def test_a_peer_that_hangs_for_ever_does_not_slow_the_directory_down(peers):
    """The read path never asks anybody. This is the bug that would make the picker feel unstable again."""
    hanging = Peer("tarpit", "Tarpit")
    hanging.hangs = True
    peers(hanging, ask=False)

    started = perf_counter()
    rows = admin.directory()["hubs"]

    assert perf_counter() - started < 0.5, "reading the directory must not wait on a peer"
    assert len(rows) == 2 and hanging.asks == 0


def test_asking_a_hanging_peer_gives_up_quickly_and_asks_them_all_at_once(peers, monkeypatch):
    """Short timeout, concurrent: a round costs the slowest peer, not the sum of them."""
    monkeypatch.setattr(config, "PEER_ASK_TIMEOUT_S", 0.2)
    first, second = Peer("tar1", "One"), Peer("tar2", "Two")
    first.hangs = second.hangs = True
    net = peers(first, second, ask=False)

    started = perf_counter()
    asyncio.run(federation.ask_peers(net))
    spent = perf_counter() - started

    assert spent < 0.6, f"both peers asked at once, not one after the other ({spent:.2f}s)"
    assert all(r["last_asked_ok"] is False for r in federation.peer_rows())


def test_a_second_read_does_not_ask_again(peers):
    """The directory is served from the book, so the finder may poll it as often as it likes."""
    peer = Peer("zurich", "Adobee Hive (zurich)")
    peers(peer)

    for _ in range(5):
        admin.directory()

    assert peer.asks == 1


def test_the_hub_asks_its_peers_without_being_asked_to(peers, monkeypatch):
    """The state the product owner was looking at: peers configured, and never asked anything.

    Nothing in the request path asks a peer, so something has to. `keep_peers_fresh` is that something, and it
    runs for the hub's lifetime from the app's lifespan.
    """
    monkeypatch.setattr(config, "PEER_ASK_SECONDS", 0.01)
    peer = Peer("zurich", "Adobee Hive (zurich)", entities=3)
    peers(peer, ask=False)

    async def run_briefly():
        asking = asyncio.create_task(federation.keep_peers_fresh())
        for _ in range(200):
            await asyncio.sleep(0.01)
            if peer.asks:
                break
        asking.cancel()

    asyncio.run(run_briefly())

    assert peer.asks >= 1, "a hub with peers configured asks them on its own"
    assert next(r for r in admin.directory()["hubs"] if r["hub"] == "zurich")["entities"] == 3


def test_one_bad_round_does_not_stop_the_asking(peers, monkeypatch):
    """A refusal inside the loop must never end it, or the hub stops learning for the rest of its life."""
    monkeypatch.setattr(config, "PEER_ASK_SECONDS", 0.01)
    peer = Peer("zurich", "Adobee Hive (zurich)")
    peers(peer, ask=False)
    rounds = {"n": 0}
    real = federation.ask_peers

    async def sometimes_explodes(transport=None):
        rounds["n"] += 1
        if rounds["n"] == 1:
            raise RuntimeError("the network went away mid-round")
        return await real(transport)

    monkeypatch.setattr(federation, "ask_peers", sometimes_explodes)

    async def run_briefly():
        asking = asyncio.create_task(federation.keep_peers_fresh())
        for _ in range(200):
            await asyncio.sleep(0.01)
            if rounds["n"] > 1:
                break
        asking.cancel()

    asyncio.run(run_briefly())

    assert rounds["n"] > 1, "the loop survived the bad round"


# ---------------------------------------------------------------- what this hub publishes about itself


def test_this_hub_publishes_what_a_peer_needs_to_describe_it(client):
    """The other half of the fix: a peer can only name us if we say our name, and one document says it all."""
    declared = client.get("/.well-known/hive.json").json()["federation"]

    assert declared["hub_id"] == config.HIVE_HUB_ID
    assert declared["name"] == config.HIVE_NAME
    assert declared["description"] == config.HIVE_DESCRIPTION
    assert declared["admission"] == config.ADMISSION_POLICY
    assert isinstance(declared["entities"], int) and declared["entities"] >= 0


def test_the_parser_the_search_already_had_reads_the_two_new_fields(client):
    """One document, one parser. `HttpTransport.profile` is what the directory reuses, so it is what is tested."""
    doc = client.get("/.well-known/hive.json").json()

    async def handler(request):
        assert request.url.path == "/.well-known/hive.json"
        return httpx.Response(200, json=doc)

    async def read() -> dict:
        client_cls = httpx.AsyncClient  # bind before patching, or the replacement calls itself
        patched = lambda **kw: client_cls(transport=httpx.MockTransport(handler), **kw)  # noqa: E731
        with mock.patch.object(httpx, "AsyncClient", patched):
            return await federation.HttpTransport().profile("https://basel.example/")

    profile = asyncio.run(read())

    assert profile["hub_id"] == config.HIVE_HUB_ID
    assert profile["name"] == config.HIVE_NAME
    assert profile["admission"] == config.ADMISSION_POLICY
    assert profile["entities"] == doc["federation"]["entities"]


def test_a_peer_too_old_to_publish_a_count_is_read_as_unknown():
    """An older peer's document has neither field. Absent must not arrive as 0 or as ""."""

    async def handler(request):
        return httpx.Response(200, json={"federation": {"hub_id": "antique"}})

    async def read() -> dict:
        client_cls = httpx.AsyncClient
        patched = lambda **kw: client_cls(transport=httpx.MockTransport(handler), **kw)  # noqa: E731
        with mock.patch.object(httpx, "AsyncClient", patched):
            return await federation.HttpTransport().profile("https://antique.example/")

    profile = asyncio.run(read())

    assert profile["entities"] is None and profile["admission"] == ""


def test_a_peer_publishing_nonsense_for_its_count_is_not_believed():
    """Card text and peer declarations are data. A count that is not a whole number is no count at all."""
    for nonsense in ("14", True, -3, None, {"n": 1}, 2.5):
        assert federation._count(nonsense) is None, nonsense
    assert federation._count(0) == 0 and federation._count(14) == 14
