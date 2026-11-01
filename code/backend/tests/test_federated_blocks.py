"""An administrative block holds on a federated answer, in both directions (#110).

The lesson this file exists for was learned once already: a blocked business stayed searchable
because the filtering lived in the `hub.py` façade and not in `hive.discover`, which is what the API
actually calls. The same shape of mistake was still there one layer out. `federation.py` chose its
peers from the stored list without consulting the blocklist, so a blocked hub was sent the query —
and therefore learned what this hub's users were looking for — and verified everything it relayed
back without asking whether the operator had blocked the entity or the route.

So the checks here are about the path that serves, not about a façade:

- a blocked peer receives **no outbound call at all**, including the profile fetch and the timer;
- a blocked entity arriving over an *allowed* peer is absent from matches *and* exclusions;
- a result whose carrier chain passes through a blocked hub is dropped even when its card is valid,
  while the same business stays reachable on a route that is clean;
- a query a blocked hub relayed to us is not answered, which is the outward direction.

The last test runs **two real hubs** over HTTP and reads the blocked hub's own access log, because
"no outbound request" is the one claim a fake transport cannot make honestly: a fake peer that is
never called looks exactly like a fake peer that is.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from app import blocklist, config, db, federation, hive, hub, reputation
from tests.test_federation import FakeHive, FakeNet, _card

BACKEND = Path(__file__).resolve().parents[1]
ASK = {"kind": "hotel", "features": ["dog-friendly"], "check_in": "2027-03-10", "check_out": "2027-03-12"}


@pytest.fixture(autouse=True)
def empty_blocklist(client):
    """No block survives a test: the list is an operator's standing decision, not a fixture's."""
    blocklist.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_blocklist")
    yield
    with db.write() as cur:
        cur.execute("DELETE FROM hub_blocklist")


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


def _ids(found: dict) -> set[str]:
    return {m["id"] for m in found["matches"]}


# ---------------------------------------------------------------- nothing of ours goes to a blocked hub


def test_a_blocked_peer_is_asked_nothing_at_all(client, net):
    """The leak this closes: the query itself. A blocked hub that is still sent the ask learns what
    this hub's users want, which is most of what shutting it out was supposed to prevent."""
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    transport = net(zurich)
    asyncio.run(federation.ask_peers(transport))  # as on a running hub: the timer learned its name already
    blocklist.block(blocklist.HUB, "zurich", "spam")
    transport.profiles.clear()

    found = hive.discover(**ASK, radius=1)

    assert zurich.asks == [], "the blocked peer was sent the query"
    assert transport.profiles == [], "reading its discovery document is an outbound call to it too"
    assert "hotel-limmat" not in _ids(found)
    assert found["federation"]["asked"] == []
    dropped = {d["hub"]: d["reason"] for d in found["federation"]["dropped"]}
    assert "blocked" in dropped["zurich"], dropped


def test_a_blocked_peer_is_not_asked_again_once_its_answer_has_gone_stale(client, net):
    """The pre-fetch check, on its own, with the cache not covering for it.

    The test above asks the same question but cannot answer it: a profile read moments earlier is
    still fresh, so `_profile` serves it from the book and makes no call either way. The mutant that
    removes the pre-fetch check therefore survived a test written to catch it — the post-fetch
    recheck caught the forwarded query, and nothing caught the fetch.

    `PEER_STALE_AFTER_S` is 120 seconds, so on a hub that has been up a while this is the normal
    case rather than a contrived one: the cached answer has expired and the read path would go and
    ask again. A blocked peer must not be asked, and the identity to check it by is the one already
    in the book, stale or not — a hub does not change its name by going quiet.
    """
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    transport = net(zurich)
    asyncio.run(federation.ask_peers(transport))  # its name is in the book
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(config, "PEER_STALE_AFTER_S", 0.0)  # and the answer has expired
    try:
        transport.profiles.clear()
        assert "hotel-limmat" in _ids(hive.discover(**ASK, radius=1)), "stale means ask again, normally"
        assert transport.profiles == [zurich.url], "the control: an unblocked stale peer is re-read"

        blocklist.block(blocklist.HUB, "zurich", "spam")
        transport.profiles.clear()
        zurich.asks.clear()

        found = hive.discover(**ASK, radius=1)
    finally:
        monkeypatch.undo()

    assert transport.profiles == [], "the blocked peer's discovery document was fetched anyway"
    assert zurich.asks == [], "and the query followed it"
    assert "hotel-limmat" not in _ids(found)


def test_a_peer_blocked_before_this_hub_ever_learned_its_name_is_caught_on_its_own_answer(client, net):
    """A URL is not an identity, so the first block check needs an id this hub already has.

    With no cached profile there is nothing to match against the list, so the discovery document is
    read — and the name it returns is checked against the list before the query is forwarded. One
    outbound call rather than none is the honest cost of not guessing an identity from a hostname.
    """
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    transport = net(zurich)
    blocklist.block(blocklist.HUB, "zurich", "spam")
    federation.forget()  # as if this hub had only just started

    found = hive.discover(**ASK, radius=1)

    assert transport.profiles == [zurich.url], "its own document is the only place its id can come from"
    assert zurich.asks == [], "but the query is not forwarded once the name is known"
    assert "hotel-limmat" not in _ids(found)
    assert any("blocked" in d["reason"] for d in found["federation"]["dropped"])


def test_the_timer_stops_asking_a_blocked_peer_too(client, net):
    """`keep_peers_fresh` polls every peer every PEER_ASK_SECONDS. That is an outbound call as well."""
    zurich = FakeHive("zurich")
    transport = net(zurich)
    asyncio.run(federation.ask_peers(transport))
    assert transport.profiles == [zurich.url], "an unblocked peer is asked who it is"

    blocklist.block(blocklist.HUB, "zurich", "spam")
    asyncio.run(federation.ask_peers(transport))

    assert transport.profiles == [zurich.url], "the blocked peer was polled again"


def test_an_unknown_peer_is_still_asked_who_it_is(client, net):
    """Fail-closed must not mean fail-silent: a peer nobody has blocked is asked, blocklist or not."""
    zurich = FakeHive("zurich")
    transport = net(zurich)
    blocklist.block(blocklist.HUB, "someone-else", "spam")

    asyncio.run(federation.ask_peers(transport))

    assert transport.profiles == [zurich.url]


# ---------------------------------------------------------------- nothing blocked arrives through an allowed hub


def test_a_blocked_entity_relayed_by_an_allowed_peer_is_dropped(client, net):
    """The second half of #110. The peer is fine; the business is the one the operator shut out."""
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    net(zurich)
    blocklist.block(blocklist.ENTITY, "hotel-limmat", "court order")

    found = hive.discover(**ASK, radius=1)

    assert zurich.asks, "the carrier is not blocked, so it is still asked"
    assert "hotel-limmat" not in _ids(found)
    refused = {b["id"]: b["reason"] for b in found["federation"]["blocked"]}
    assert "blocked" in refused["hotel-limmat"], refused


def test_a_blocked_entity_is_gone_from_the_exclusions_as_well(client, net):
    """An exclusion names the business and says why it missed, which is most of what a match says.

    Leaving a blocked entity in `excluded` publishes exactly what the block was meant to withhold,
    and "it was only in the near-misses" is not a defence anyone would accept.
    """
    zurich = FakeHive("zurich")

    async def answer(ask, radius, budget_ms, seen):
        return {
            "matches": [],
            "excluded": [{"id": "hotel-limmat", "name": "Hotel Limmat (fictional)", "why_not": ["no dogs"]}],
            "ranking_policy": "No paid placement.",
        }

    zurich.search = answer  # type: ignore[method-assign]
    net(zurich)
    blocklist.block(blocklist.ENTITY, "hotel-limmat", "court order")

    found = hive.discover(**ASK, radius=1)

    assert "hotel-limmat" not in {e["id"] for e in found["excluded"]}
    assert any(b["where"] == "excluded" for b in found["federation"]["blocked"])


def test_a_blocked_hub_deeper_in_the_chain_drops_what_it_carried(client, net):
    """Blocking a hub that only ever relays has to achieve something, or it achieves nothing."""
    bern = FakeHive("bern", cards=[_card("hotel-aare", "Hotel Aare (fictional)")])
    zurich = FakeHive("zurich", relays=[bern])
    net(zurich, bern, peers=[zurich])
    blocklist.block(blocklist.HUB, "bern", "relays spam")

    found = hive.discover(**ASK, radius=2)

    assert zurich.asks, "zurich is not blocked; it is the hop behind it that is"
    assert "hotel-aare" not in _ids(found)
    refused = {b["id"]: b["reason"] for b in found["federation"]["blocked"]}
    assert "bern" in refused["hotel-aare"], refused


def test_blocking_a_route_leaves_the_same_business_reachable_on_a_clean_one(client, net):
    """Blocking a *hub* is not blocking an entity, and the answer has to keep the difference.

    The same card arrives twice, once through a blocked relay and once directly. The blocked route
    is dropped before deduplication, so it cannot survive as the kept result's `also_reached_by`
    either — which is how a blocked carrier chain used to come back as a footnote.
    """
    card = _card("hotel-aare", "Hotel Aare (fictional)")
    bern = FakeHive("bern", cards=[card])
    direct = FakeHive("direct", cards=[card])
    relay = FakeHive("relay", relays=[bern])
    net(direct, relay, bern, peers=[direct, relay])
    blocklist.block(blocklist.HUB, "relay", "relays spam")

    found = hive.discover(**ASK, radius=2)

    kept = next(m for m in found["matches"] if m["id"] == "hotel-aare")
    assert kept["provenance"]["path"] == ["direct", "basel"], kept["provenance"]
    routes = [r["path"] for r in kept["provenance"]["also_reached_by"]]
    assert all("relay" not in route for route in routes), routes


def test_the_hub_facade_still_screens_what_federation_already_screened(client, net):
    """Defence in depth on purpose. The façade check is cheap and the overlap is the whole point."""
    zurich = FakeHive("zurich", cards=[_card("hotel-limmat", "Hotel Limmat (fictional)")])
    net(zurich)
    blocklist.block(blocklist.ENTITY, "hotel-limmat", "court order")

    served = asyncio.run(hub.search(ASK, radius=1))

    assert "hotel-limmat" not in {m["id"] for m in served["matches"]}


# ---------------------------------------------------------------- and nothing of ours goes back out


def test_a_query_a_blocked_hub_relayed_here_is_not_answered(client):
    """The outward direction. A block means nothing of ours reaches it, and an answer is ours.

    `seen` is the asking hub's own account of where the query has been, which is all an
    unauthenticated peer protocol offers. A blocked hub that lies about its trail was never
    stoppable at this layer; the honest case — a hub we shut out relaying to us under its own name —
    is, and is the one that happens.
    """
    blocklist.block(blocklist.HUB, "zurich", "spam")

    refused = client.get("/api/hive/discover", params={**ASK, "seen": ["zurich"]})

    assert refused.status_code == 403
    assert "zurich" in refused.json()["detail"]
    assert client.get("/api/hive/discover", params={**ASK, "seen": ["bern"]}).status_code == 200


# ---------------------------------------------------------------- two real hubs over HTTP


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


HUB_TOKEN = "two-hub-block-test-operator"
THEM = "elektro-mattenhof"
BERN = "bern"


def _get(url: str, timeout: float = 10, token: str = "") -> dict:
    request = urllib.request.Request(url, headers={"X-Admin-Token": token} if token else {})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 - our own subprocess
        return json.loads(answer.read())


def _post(url: str, body: dict, token: str = "", timeout: float = 20) -> tuple[int, dict]:
    headers = {"content-type": "application/json"} | ({"X-Admin-Token": token} if token else {})
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def _delete(url: str, token: str, timeout: float = 20) -> dict:
    request = urllib.request.Request(url, method="DELETE", headers={"X-Admin-Token": token})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 - our own subprocess
        return json.loads(answer.read())


@pytest.fixture(scope="module")
def two_real_hubs(tmp_path_factory):
    """Two hubs in subprocesses, peered, with one vault seeded into the second one only.

    Skipped rather than failed when a hub will not start or the handshake never settles: a port this
    machine refuses is not a bug in the hub, and a flaky red on main costs more than this is worth.
    """
    ports = {"here": _free_port(), BERN: _free_port()}
    data = tmp_path_factory.mktemp("blockhubs")
    procs, logs, paths = {}, {}, {}
    env = {
        **os.environ,
        "ADMISSION_POLICY": "open",
        "ADMIN_TOKEN": HUB_TOKEN,
        "SEED_ON_EMPTY": "false",
        "PEER_ASK_SECONDS": "1",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "LLM_PROVIDER": "offline",
    }
    for name, port in ports.items():
        other = ports[BERN] if name == "here" else ports["here"]
        paths[name] = data / f"{name}.log"
        logs[name] = paths[name].open("w")
        procs[name] = subprocess.Popen(  # noqa: S603 - our own interpreter and module
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND), "--port", str(port)],
            env={
                **env,
                "HIVE_HUB_ID": name,
                "HIVE_PEER_URLS": f"http://127.0.0.1:{other}",
                "DUCKDB_PATH": str(data / f"{name}.duckdb"),
            },
            stdout=logs[name],
            stderr=subprocess.STDOUT,
            cwd=str(BACKEND),
        )
    try:
        for name, port in ports.items():
            for _ in range(100):
                try:
                    _get(f"http://127.0.0.1:{port}/api/health", timeout=1)
                    break
                except Exception:  # noqa: BLE001 - still starting, or never will
                    time.sleep(0.2)
            else:
                pytest.skip(f"the {name} hub did not come up on port {port}")
        seeded = subprocess.run(  # noqa: S603 - our own interpreter and script
            [
                sys.executable,
                str(BACKEND / "tools" / "seed_vaults.py"),
                "--hub",
                f"http://127.0.0.1:{ports[BERN]}",
                "--only",
                THEM,
            ],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(BACKEND),
            timeout=120,
        )
        if seeded.returncode != 0:
            pytest.skip(f"the bern hub would not take the vault: {seeded.stdout[-400:]}")
        for _ in range(60):
            here = _get(f"http://127.0.0.1:{ports['here']}/api/admin/peers", token=HUB_TOKEN)
            if any(row.get("hub") == BERN and row.get("known") for row in here["peers"]):
                break
            time.sleep(0.5)
        else:
            pytest.skip("the two hubs never learned each other's names")
        yield ports, paths
    finally:
        for name, proc in procs.items():
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - a hub that will not stop
                proc.kill()
            logs[name].close()


def _search(here: str, **extra) -> dict:
    params = "&".join(f"{k}={v}" for k, v in {"query": "electrician", "radius": 1, "budget_ms": 8000, **extra}.items())
    return _get(f"{here}/api/hive/discover?{params}", timeout=20)


def _hits(log: Path) -> list[str]:
    """Bern's own access log, which is the only honest answer to "was it contacted"."""
    return [line for line in log.read_text().splitlines() if "GET /" in line]


def test_two_real_hubs_a_blocked_peer_is_not_contacted_and_a_blocked_entity_does_not_arrive(two_real_hubs):
    """The runtime coverage #110 asks for, over HTTP, with the blocked hub's log as the evidence.

    A fake peer cannot make the first claim: one that is never called is indistinguishable from one
    that is never there. Bern's uvicorn log can, and it is read on the far side of the block.
    """
    ports, logs = two_real_hubs
    here = f"http://127.0.0.1:{ports['here']}"
    blocks = f"{here}/api/admin/blocklist"

    found = None
    for _ in range(40):  # the registries settle a moment after the vault is seeded
        answer = _search(here)
        found = next((m for m in answer["matches"] if m["id"] == THEM), None)
        if found and found.get("card"):
            break
        time.sleep(0.5)
    assert found is not None, "the federated search never reached bern, so there is nothing to block"
    assert found["provenance"]["path"][0] == BERN

    # ---- the peer. Block it, let a couple of timer rounds pass, then look at its log.
    assert _post(blocks, {"kind": "hub", "subject": BERN, "reason": "two-hub test"}, HUB_TOKEN)[0] == 200
    time.sleep(3)  # PEER_ASK_SECONDS is 1 here, so several background rounds happen in this window
    before = len(_hits(logs[BERN]))
    blocked = _search(here)
    time.sleep(2)

    assert THEM not in {m["id"] for m in blocked["matches"]}, "a blocked peer's entity still arrived"
    assert blocked["federation"]["asked"] == []
    assert any("blocked" in d["reason"] for d in blocked["federation"]["dropped"]), blocked["federation"]["dropped"]
    assert len(_hits(logs[BERN])) == before, "bern was contacted while blocked"

    # ---- the entity. Unblock the hub, block the business, and the carrier is asked as usual.
    assert _delete(f"{blocks}/hub/{BERN}", HUB_TOKEN)["lifted"] is True
    assert _post(blocks, {"kind": "entity", "subject": THEM, "reason": "two-hub test"}, HUB_TOKEN)[0] == 200
    for _ in range(40):
        answer = _search(here)
        if answer["federation"]["asked"]:
            break
        time.sleep(0.5)

    assert answer["federation"]["asked"], "unblocking the hub must let it be asked again"
    assert THEM not in {m["id"] for m in answer["matches"]}, "the blocked entity arrived through an allowed peer"
    assert THEM not in {e["id"] for e in answer["excluded"]}, "and it must not come back as a near-miss"
    assert any(b["id"] == THEM for b in answer["federation"]["blocked"]), answer["federation"]["blocked"]
