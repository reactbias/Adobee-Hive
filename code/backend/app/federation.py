"""Hop-limited ("node radius") federated search across peer Hives.

A query carries a **radius**: the number of hops it may travel. `0` (the default everywhere) is this Hive only,
exactly as before; `1` adds this Hive's direct peers, `2` their peers, and `MAX_RADIUS` is the ceiling. Each hop
decrements the radius, appends its own hub id to `seen`, and forwards only to peers that are not in `seen` yet,
so the cycles in a real peer graph cannot send a query round for ever. Each hop also subtracts the time it has
already spent from `budget_ms` and refuses to forward when too little is left; peers are asked in parallel and a
peer that misses the deadline is dropped from the answer, named in `federation.dropped`, and never fails the query.
`PEERS_PER_HOP` caps the breadth at each hop, so fan-out cannot explode.

*Which* peers exist comes from `peers.py`, which stores the list: an operator adds, edits or removes a neighbour
while the hub runs and the very next query obeys, with `HIVE_PEER_URLS` only the seed a fresh hub starts from.
*Who* a peer is, and whether it is answering, is this module's own book (`_ask`, `peer_row`, `keep_peers_fresh`).
Peer URLs still never come from a request — only from configuration or an admin-authenticated change — so a
stranger cannot use this hub to flood another.

The peer list itself comes from `peers.py`, which stores it: an operator adds, edits or removes a neighbour while
the hub runs, and `HIVE_PEER_URLS` is only the seed a fresh hub starts from. Peer URLs still never come from a
request — only from configuration or from an admin-authenticated change — so a stranger cannot use this hub to
flood another.

Trust is not transitive here. **Signatures are verified at the destination, not taken from the carrier**: a card
that arrives over a peer is checked with `hive.verify_pinned` against the key pinned in *its own* hub's registry,
which this hub fetches directly from that hub, not through the relay. A relaying hub can therefore withhold a card
or delay it, but never forge or change one; a card it tampered with is rejected here and costs it peer trust
(`reputation.record_invalid`). The one thing a hub is still trusted for is its own ranking, which is why a
federated result is ranked `local_relevance × hub_path_trust × hop_decay`, with all three factors in
`score_breakdown` so the open-ranking promise still holds for results from another hub.

What a peer says about businesses it excluded is carried along as the peer's own words, tagged with its
provenance, and stays data: it is never read as an instruction (the agent's guard in `injection.py` scans it like
any other tool result).

An **administrative block** (`blocklist.py`) is honoured here, on the path the API actually serves, and not only
in the `hub.py` façade that nothing on the read path goes through. A blocked peer is dropped before any outbound
call — the profile fetch included, because that call and the query after it are how a shut-out hub used to learn
what this hub's users were asking. A blocked entity, and any result whose carrier chain passes through a blocked
hub, is removed from the matches *and* from the exclusions on the way in. One policy, both directions.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from time import monotonic, perf_counter
from typing import Any, Protocol

import httpx

from . import blocklist, config, hive, reputation, sharing

log = logging.getLogger(__name__)

MAX_RADIUS = 3  # a traveller can reach peers of peers of peers, no further
PEERS_PER_HOP = 4  # breadth cap: the most trusted peers at each hop, so fan-out stays bounded
DEFAULT_BUDGET_MS = 2500.0
MIN_FORWARD_MS = 150.0  # below this, a hop is not worth making
MAX_PEER_EXCLUSIONS = 20  # a peer's reasons are useful, but not unbounded
FEDERATED_RANKING_POLICY = (
    "Federated results rank local_relevance x hub_path_trust x hop_decay. Hop decay is confidence in a longer "
    "carrier chain, not a judgement about distant businesses. No hub can buy rank: a hub that declares paid "
    "placement is downweighted."
)

_ProfileLookups = dict[str, asyncio.Task[dict[str, Any] | None]]


def hop_params(ask: dict[str, Any], radius: int, budget_ms: float, seen: list[str]) -> dict[str, Any]:
    """The query string one hub sends another: the ask, the radius left, the time left and where it has been."""
    params: dict[str, Any] = {k: v for k, v in ask.items() if v not in (None, "", [])}
    return params | {"radius": radius, "budget_ms": round(budget_ms), "seen": list(seen)}


class Transport(Protocol):
    """How a hub reaches a peer. Swapped for an in-process fake in the tests."""

    async def profile(self, base_url: str) -> dict[str, Any]:
        """Read a peer's /.well-known/hive.json: its hub id, what it declares, and its pinned owner keys."""
        ...

    async def search(
        self, base_url: str, ask: dict[str, Any], radius: int, budget_ms: float, seen: list[str]
    ) -> dict[str, Any]:
        """Forward a query to a peer and return its answer."""
        ...


class HttpTransport:
    """Reaches a peer over the surface every Hive already serves: /.well-known/hive.json and GET /api/hive/discover."""

    async def profile(self, base_url: str) -> dict[str, Any]:
        """Fetch and normalise a peer's discovery document."""
        async with httpx.AsyncClient(timeout=config.PEER_ASK_TIMEOUT_S) as http:
            res = await http.get(f"{base_url.rstrip('/')}/.well-known/hive.json")
            res.raise_for_status()
            doc = res.json()
        declared = doc.get("federation") or {}
        return {
            "hub_id": str(declared.get("hub_id") or base_url.rstrip("/")),
            # A hub is an entity like a business: it has a name and a description it declares, and a
            # rating this hub works out for itself. Only the first two come off the wire.
            "name": str(declared.get("name") or doc.get("name") or ""),
            "description": str(declared.get("description") or doc.get("description") or ""),
            "verification": declared.get("verification"),
            "paid_placement": declared.get("paid_placement"),
            # What it asks of a new member, and how many entities it carries: the two facts a person choosing a
            # hub actually decides by. Absent from an older peer's document, and absent is not zero.
            "admission": str(declared.get("admission") or ""),
            "entities": _count(declared.get("entities")),
            "ranking_policy": str(doc.get("ranking_policy") or ""),
            "owner_keys": {k: v for k, v in (doc.get("owner_keys") or {}).items() if isinstance(v, str)},
        }

    async def search(
        self, base_url: str, ask: dict[str, Any], radius: int, budget_ms: float, seen: list[str]
    ) -> dict[str, Any]:
        """Ask a peer the same query one hop further out."""
        params = hop_params(ask, radius, budget_ms, seen)
        async with httpx.AsyncClient(timeout=max(0.1, budget_ms / 1000)) as http:
            res = await http.get(f"{base_url.rstrip('/')}/api/hive/discover", params=params)
            res.raise_for_status()
            return res.json()


DEFAULT_TRANSPORT: Transport = HttpTransport()

# ---------------------------------------------------------------- the peer book
#
# What this hub knows about each peer, and when it last asked: by base URL for the hubs we talk to, by hub id so a
# carrier deeper in a chain can be judged too. Both are opinions this hub formed, like reputation's observations,
# and nothing here is persisted or taken on a peer's word about a third party.
#
# Asking happens on a timer (`keep_peers_fresh`), never on the read path. A hub with peers configured therefore
# knows their names without waiting for someone to run a federated search, and a read of the directory cannot be
# made slow by a peer that has stopped answering.
_peers: dict[str, dict[str, Any]] = {}
_by_hub: dict[str, dict[str, Any]] = {}


def forget() -> None:
    """Drop everything this hub has learned about its peers, so the next ask reads each declaration again."""
    _peers.clear()
    _by_hub.clear()


def _count(value: Any) -> int | None:
    """A whole count a peer published, or None. A missing or nonsense count stays missing: never read as zero."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _now() -> str:
    """This moment as ISO 8601 UTC, the one format every `last_asked` in an answer uses."""
    return datetime.now(UTC).isoformat(timespec="seconds")


def url_label(base_url: str) -> str:
    """The host and port of a peer URL: the honest label for a hub that has not yet said what it is called."""
    return base_url.rstrip("/").split("//")[-1]


def _blank(base_url: str) -> dict[str, Any]:
    """A peer we have a URL for and nothing else. Never asked is `None`, which is not the same as nothing there."""
    return {
        "url": base_url,
        "profile": None,  # the last discovery document that actually arrived
        "last_asked": None,  # when we last tried, successfully or not; None means genuinely never asked
        "last_asked_ok": None,
        "last_answered": None,  # when the document in `profile` arrived
        "asked_at": 0.0,  # monotonic, for the max age only
    }


async def _ask(base_url: str, transport: Transport) -> dict[str, Any]:
    """Ask one peer who it is and record the attempt either way.

    A failed ask keeps the last document that did arrive rather than blanking the row: a peer's name and its
    owner keys outlive one bad minute, and `last_asked_ok` already says the answer on screen is not current.
    """
    record = _peers.setdefault(base_url, _blank(base_url))
    try:
        profile = await asyncio.wait_for(transport.profile(base_url), timeout=config.PEER_ASK_TIMEOUT_S)
    except Exception:  # unreachable, slow or broken: say when we asked, and keep what we already knew
        record |= {"last_asked": _now(), "last_asked_ok": False, "asked_at": monotonic()}
        return record
    record |= {
        "profile": profile,
        "last_asked": _now(),
        "last_asked_ok": True,
        "last_answered": _now(),
        "asked_at": monotonic(),
    }
    _by_hub[profile["hub_id"]] = profile
    return record


def _fresh(record: dict[str, Any]) -> bool:
    """True while an answer we already have is young enough to reuse without asking again.

    A profile whose `owner_keys` is empty does not count as an answer. A hub that is still starting serves its
    discovery document before it has registered anything, so a peer asked in that window answers honestly with an
    empty registry - and caching that for PEER_STALE_AFTER_S would make every card it later relays unverifiable
    until the cache expired. Treat it as not yet read and ask again.
    """
    profile = record["profile"]
    if not profile or not profile.get("owner_keys"):
        return False
    return (monotonic() - record["asked_at"]) < config.PEER_STALE_AFTER_S


async def _profile(base_url: str, transport: Transport, lookups: _ProfileLookups) -> dict[str, Any] | None:
    """Read each origin once per query, including an empty or unavailable registry."""
    if base_url not in lookups:
        lookups[base_url] = asyncio.create_task(_load_profile(base_url, transport))
    return await lookups[base_url]


async def _load_profile(base_url: str, transport: Transport) -> dict[str, Any] | None:
    """Reuse a fresh peer profile, or ask again so a later query can recover after startup."""
    record = _peers.get(base_url)
    if record and _fresh(record):
        return record["profile"]
    return (await _ask(base_url, transport))["profile"]


def known_hub_id(base_url: str) -> str:
    """The canonical hub id this peer URL last gave for itself, or "" when we have never been told.

    A URL is not an identity. Two URLs can be one hub and a hub can move, so a hostname guessed from
    a peer URL is not something a policy may be built on; only the `hub_id` the peer published in its
    own discovery document is. `""` therefore means *we do not know yet*, never *it is nobody*.
    """
    return str(((_peers.get(base_url) or {}).get("profile") or {}).get("hub_id") or "")


def pinned_keys_of(hub_id: str) -> dict[str, str]:
    """The owner keys one peer published, from what the background asking already learned.

    Read-only and never a fetch, like `peer_row`: a caller on a request path must not be made slow
    by a peer. That matters most for `hub.connect`, which checks a card for an entity on another hub
    and has to do it without a round trip.

    The URL these keys came from is always one of this hub's own peer URLs — configuration or an
    admin-authenticated change (`peers.py`) — never anything from a request. A hub id this hub has
    not heard from yet gives `{}`, which callers must treat as *cannot be checked*, never as
    *nothing to check*.
    """
    return {str(k): str(v) for k, v in ((_by_hub.get((hub_id or "").strip()) or {}).get("owner_keys") or {}).items()}


def carriers_of(entity_id: str) -> list[dict[str, str]]:
    """Which peers this hub has heard pin a key for `entity_id`, with the URL to reach each.

    Read-only and never a fetch, like `pinned_keys_of`. The answer comes from the discovery documents
    the background asking already collected, so it costs nothing on a request path and cannot be made
    slow by a peer.

    This exists so a refusal can point somewhere. "No entity 'x' on this hub" is a dead end when the
    hub has the answer in its own book: it knows which of its peers publishes a key for that id, and
    it knows that peer's URL, because both came off its own peer list (#159). It is a *hint* and
    nothing more — a hub that pins a key for an id is a hub claiming that entity, and the claim is
    only worth acting on because the card still has to survive `_verified` or `hub._verified_remote`
    at the other end. So this never admits anything; it only says where to look.

    An administrative block is applied to the hint as well. A hub nothing of ours goes to is not a
    place to send somebody: naming it hands the asker the address and the query, which is the leak
    blocking it was meant to close, one indirection further out. A blocked *entity* gets no hint
    either, for the same reason an exclusion naming one would be no better than a match.
    """
    entity_id = (entity_id or "").strip()
    if not entity_id:
        return []
    refused = blocklist.screener()
    if refused(entity_id):
        return []
    by_url = {str((record.get("profile") or {}).get("hub_id") or ""): url for url, record in _peers.items()}
    out = []
    for hub_id, record in _by_hub.items():
        if entity_id in ((record or {}).get("owner_keys") or {}) and not refused(entity_id, [hub_id]):
            out.append({"hub": hub_id, "url": by_url.get(hub_id, "")})
    return sorted(out, key=lambda row: row["hub"])


def peer_row(base_url: str) -> dict[str, Any]:
    """What this hub knows about one peer, as data an interface can render.

    Read-only: it never asks, so a caller on a request path cannot be made slow by a peer. Everything we have not
    been told stays unknown — `entities` is `None` rather than `0`, and the label falls back to the URL rather
    than to a hub id nobody published.
    """
    record = _peers.get(base_url) or _blank(base_url)
    declared = record["profile"] or {}
    return {
        "url": base_url,
        "hub": str(declared.get("hub_id") or url_label(base_url)),
        "known": bool(declared),
        "name": str(declared.get("name") or ""),
        "description": str(declared.get("description") or ""),
        "verification": str(declared.get("verification") or "unknown"),
        "admission": str(declared.get("admission") or "unknown"),
        "entities": _count(declared.get("entities")),
        "last_asked": record["last_asked"],
        "last_asked_ok": record["last_asked_ok"],
        "last_answered": record["last_answered"],
        # The last ask failed, so what is shown is an older answer rather than the current one.
        "stale": bool(declared) and record["last_asked_ok"] is False,
    }


def peer_rows() -> list[dict[str, Any]]:
    """One row per peer on the stored list, from the book alone. Never asks, so it never blocks."""
    from . import peers as peer_store

    return [peer_row(url) for url in peer_store.urls()]


async def ask_peers(transport: Transport | None = None) -> list[dict[str, Any]]:
    """Ask every configured peer who it is, all at once.

    Concurrent, so a round costs the slowest peer rather than the sum of them, and each ask is capped at
    `PEER_ASK_TIMEOUT_S`. Nothing is raised: a peer that does not answer is recorded as not having answered.
    """
    from . import peers as peer_store

    # A blocked peer is not asked, here as well as on the search path. "Nothing of ours goes to it"
    # includes the timer: polling a hub this operator has shut out every PEER_ASK_SECONDS is an
    # outbound call to it, and a steady one. A peer whose canonical id we have never learned is still
    # asked, because there is nothing yet to check against the list — the identity has to come from
    # somewhere, and it only ever comes from the peer's own discovery document.
    blocked = blocklist.blocked_hubs()
    urls = [url for url in peer_store.urls() if known_hub_id(url) not in blocked]
    if urls:
        await asyncio.gather(*[_ask(url, transport or DEFAULT_TRANSPORT) for url in urls])
    return peer_rows()


async def keep_peers_fresh() -> None:
    """Ask the peers who they are, now and every `PEER_ASK_SECONDS` after, for as long as the hub runs.

    This is what makes the asking happen on its own. Without it a hub only ever learns a peer's name as a side
    effect of somebody running a federated search, so a directory read on a quiet hub would say "not asked" for
    ever while the peer was publishing its name perfectly well all along.
    """
    while True:
        try:
            await ask_peers()
        except asyncio.CancelledError:
            raise
        except Exception:  # a bad round must never end the loop; the next one tries again
            log.debug("asking the peers who they are failed", exc_info=True)
        await asyncio.sleep(max(1.0, config.PEER_ASK_SECONDS))


async def _choose_peers(
    seen: list[str], transport: Transport, lookups: _ProfileLookups
) -> tuple[list[tuple[str, dict[str, Any], float]], list[dict[str, str]]]:
    """The peers worth asking at this hop: not in `seen`, readable, the `PEERS_PER_HOP` most trusted first."""
    # The stored peer list, not the environment: a neighbour an operator added is asked by the very
    # next query, and one they removed is not (peers.py). Read per query, so there is no cache to
    # invalidate and no restart to wait for.
    from . import peers as peer_store  # local: peers.py is about which peers exist, this about who they are

    urls = peer_store.urls()
    blocked = blocklist.blocked_hubs()
    # An administrative block is checked **before** any outbound work, and again on the identity the
    # peer itself returns. Both, because the first check can only use an identity this hub already
    # had, and the second one cannot stop a request that has already gone out. Reading a peer's
    # discovery document is itself a call to it, and the query would follow, which is how a blocked
    # hub used to learn what this hub's users were searching for even though it was shut out.
    asking, skipped = [], []
    for url in urls:
        known = known_hub_id(url)
        if known and known in blocked:
            skipped.append({"hub": known, "reason": "blocked on this hub: not asked, and nothing of ours sent to it"})
        else:
            asking.append(url)
    profiles = await asyncio.gather(*[_profile(url, transport, lookups) for url in asking])
    peers = []
    for url, profile in zip(asking, profiles, strict=False):
        if profile is None:
            # Unknown identity fails closed, and that is the policy rather than an accident: a peer
            # whose discovery document cannot be read has neither a hub id to check against the
            # blocklist nor keys to verify its cards with. Unknown is never treated as trusted.
            skipped.append({"hub": url, "reason": "no key registry: its cards could not be verified here"})
        elif profile["hub_id"] in blocked:
            skipped.append(
                {
                    "hub": profile["hub_id"],
                    "reason": "blocked on this hub: it named itself on the only call made to it, and the query"
                    " was not forwarded",
                }
            )
        elif profile["hub_id"] not in seen:
            peers.append((url, profile, reputation.hub_trust(profile["hub_id"], profile)["trust"]))
    peers.sort(key=lambda peer: peer[2], reverse=True)  # stable, so configured order breaks a tie
    over = peers[PEERS_PER_HOP:]
    skipped += [
        {"hub": p["hub_id"], "reason": f"breadth cap: only the top {PEERS_PER_HOP} peers by trust"} for _, p, _ in over
    ]
    return peers[:PEERS_PER_HOP], skipped


async def _ask_peer(
    url: str, ask: dict[str, Any], radius: int, budget_ms: float, seen: list[str], transport: Transport
) -> dict[str, Any]:
    """Forward the query to one peer within the remaining budget. A miss is reported, never raised."""
    started = perf_counter()
    try:
        out = await asyncio.wait_for(
            transport.search(url, ask, radius, budget_ms, list(seen)), timeout=max(0.001, budget_ms / 1000)
        )
    except TimeoutError:
        return {"code": "deadline", "reason": f"deadline exceeded: {budget_ms:.0f} ms left for this hop"}
    except Exception as err:  # a peer that answers nonsense must not break the whole query
        return {"code": "unreachable", "reason": f"{type(err).__name__}: {err}"[:200]}
    return {"out": out if isinstance(out, dict) else {}, "ms": (perf_counter() - started) * 1000}


def _factors(match: dict[str, Any], path: list[str], hops: int) -> dict[str, Any]:
    """The three rank factors of one result, each on its own so a ranking can always be explained."""
    relevance = float(match.get("score") or 0)
    trust = reputation.path_trust(path[:-1], _by_hub)  # every hub that carried it, except this one
    decay = reputation.hop_decay(hops)
    return {
        "score_breakdown": {
            **(match.get("score_breakdown") or {}),
            "local_relevance": relevance,
            "hub_path_trust": trust,
            "hop_decay": decay,
        },
        "federated_score": round(relevance * trust * decay, 2),
    }


def _arrival(match: dict[str, Any], path: list[str], origin_url: str | None) -> dict[str, Any]:
    """One result as this hub keeps it: the route it travelled, its hop count and its three rank factors."""
    hops = len(path) - 1
    carriers = path[:-1]
    why = list(match.get("why") or [])
    factors = _factors(match, path, hops)
    if carriers:
        trust = factors["score_breakdown"]["hub_path_trust"]
        why.append(f"reached through {' then '.join(carriers)} (hub path trust {trust})")
    return {
        **{k: v for k, v in match.items() if k not in ("provenance", "score_breakdown")},
        "provenance": {
            "path": path,
            "hops": hops,
            "origin": path[0],
            "origin_url": origin_url,
            "also_reached_by": [],
        },
        "hops": hops,
        "why": why,
        **factors,
    }


def _local(ask: dict[str, Any], hub: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Today's local answer, plus its matches dressed as federated arrivals with zero hops."""
    found = hive.discover(**ask)
    arrivals = [_arrival({**m, "card": hive.get_card(m["id"])}, [hub], None) for m in found["matches"]]
    return found, arrivals


def _shorter(one: dict[str, Any], other: dict[str, Any]) -> bool:
    """Which of two routes to the same card wins: fewer hops, then the more trusted carrier chain."""

    def key(match: dict[str, Any]) -> tuple[int, float]:
        return (match["hops"], -match["score_breakdown"]["hub_path_trust"])

    return key(one) < key(other)


def _dedup(arrivals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One result per card, whichever route was shortest; the other routes are kept as `also_reached_by`."""
    best: dict[str, dict[str, Any]] = {}
    for match in arrivals:
        card = match.get("card")
        key = hive.card_digest(card) if isinstance(card, dict) else f"{match['provenance']['origin']}:{match['id']}"
        kept = best.get(key)
        if kept is None:
            best[key] = match
            continue
        winner, loser = (match, kept) if _shorter(match, kept) else (kept, match)
        winner["provenance"]["also_reached_by"] = [
            *winner["provenance"]["also_reached_by"],
            *loser["provenance"]["also_reached_by"],
            {
                "path": loser["provenance"]["path"],
                "hops": loser["hops"],
                "hub_path_trust": loser["score_breakdown"]["hub_path_trust"],
            },
        ]
        best[key] = winner
    return list(best.values())


def _screen(
    arrivals: list[dict[str, Any]], excluded: list[dict[str, Any]], report: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Drop every blocked entity and every blocked carrier chain, from the matches and the exclusions alike.

    `hive.discover` already keeps a blocked entity out of the *local* answer. This is the other
    direction — what arrived from a peer — plus the one thing that only exists out here, the chain of
    hubs a result travelled: a card is refused when *any* hub that carried it is blocked, so blocking
    a hub that merely relays for a blocked one still achieves something.

    Both lists are screened, because an exclusion is not harmless. It names a business and says why it
    missed the ask, which is most of what a match says; leaving a blocked entity in `excluded` would
    publish exactly what the block was meant to withhold.

    Called before `_dedup`, so an alternate route through a blocked hub is gone before it can be
    folded into a kept result's `also_reached_by`. A business reachable both through a blocked hub and
    through an allowed one therefore survives on the allowed route alone, which is what blocking a
    *hub* rather than an entity means.
    """
    refused = blocklist.screener()

    def kept(row: dict[str, Any], where: str) -> bool:
        path = [str(h) for h in ((row.get("provenance") or {}).get("path") or [])]
        reason = refused(str(row.get("id") or ""), path)
        if reason:
            report["blocked"].append({"id": row.get("id"), "where": where, "path": path, "reason": reason})
        return not reason

    return (
        [a for a in arrivals if kept(a, "matches")],
        [e for e in excluded if kept(e, "excluded")],
    )


async def _verified(
    out: dict[str, Any],
    carrier: dict[str, Any],
    carrier_url: str,
    hub: str,
    transport: Transport,
    report: dict,
    lookups: _ProfileLookups,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Take a peer's answer apart: verify every card against its own hub's registry, drop what fails."""
    arrivals, excluded = [], []
    for match in out.get("matches") or []:
        if not isinstance(match, dict) or not match.get("id"):
            continue
        provenance = match.get("provenance") or {}
        claimed = [str(p) for p in (provenance.get("path") or [carrier["hub_id"]])][:MAX_RADIUS]
        path = [*claimed, hub]
        blameless = False
        origin_url = str(provenance.get("origin_url") or carrier_url)
        card = match.get("card")
        origin = await _profile(origin_url, transport, lookups) if isinstance(card, dict) else None
        # The carrier's word counts for nothing here: the key comes from the card's own hub, fetched directly.
        if not isinstance(card, dict):
            reason = "no card to check against the owner's key"
        elif origin is None:
            reason = f"no key registry at {origin_url}"
        elif not origin["owner_keys"]:
            # The origin published no keys - it was probably still starting when we asked. We cannot verify the
            # card, so it does not pass; but this is our ignorance, not the carrier's doing, so nobody is charged.
            reason = f"the key registry at {origin_url} is empty, so this card cannot be checked yet"
            blameless = True
        elif not hive.verify_pinned(card, origin["owner_keys"]):
            reason = "this copy does not match what the owner signed, or no key is pinned for it"
        elif not sharing.searchable(hive.sharing_default(card), None):
            # Read only after the card has been verified, so the flag comes from a body its owner
            # signed rather than from whoever relayed it. A hub is supposed to keep a `push` or
            # `never` entity out of its own answers; when one arrives anyway it is withheld here
            # too, because the owner's decision does not stop at a hub boundary. Nobody is charged
            # for it: the hub that should have enforced it is the origin, and from here the origin
            # and the carrier are not reliably distinguishable.
            reason = "its owner shares it only on their own initiative, by the flag on the card they signed"
            blameless = True
        else:
            arrivals.append(_arrival(match, path, origin_url))
            continue
        report["rejected"].append(
            {"hub": carrier["hub_id"], "card_id": match["id"], "origin": claimed[0], "reason": reason}
        )
        # Reputation is the one judgement here that outlives the request, so it is only ever charged for something
        # the carrier controls: a card it altered, or a key its own hub will not back up. A registry we could not
        # read is neither, and blaming it there is how one slow start used to cost a peer its trust for the rest of
        # the process.
        if not blameless:
            reputation.record_invalid(carrier["hub_id"], 1, str(match["id"]))
    for left_out in (out.get("excluded") or [])[:MAX_PEER_EXCLUSIONS]:
        if isinstance(left_out, dict) and left_out.get("id"):
            route = [str(p) for p in ((left_out.get("provenance") or {}).get("path") or [carrier["hub_id"]])]
            excluded.append(
                {
                    **{k: v for k, v in left_out.items() if k not in ("card", "provenance")},
                    "provenance": {"path": [*route, hub], "hops": len(route), "origin": route[0]},
                }
            )
    return arrivals, excluded


async def search(
    ask: dict[str, Any],
    radius: int = 1,
    budget_ms: float | None = None,
    seen: list[str] | None = None,
    transport: Transport | None = None,
) -> dict[str, Any]:
    """Search this Hive and, hop by hop, its peers. Returns the local answer plus a `federation` report.

    `ask` is the same query `hive.discover` takes. Nothing here changes a local result: matches only gain
    `provenance`, `hops`, the three rank factors and the signed `card` they were verified against.
    """
    started = perf_counter()
    transport = transport or DEFAULT_TRANSPORT
    lookups: _ProfileLookups = {}
    budget = float(budget_ms or DEFAULT_BUDGET_MS)
    hub = config.HIVE_HUB_ID
    trail = [*(seen or [])]
    if hub not in trail:
        trail.append(hub)  # every hop names itself, so the next one can avoid coming back
    hops = max(0, min(int(radius), MAX_RADIUS))
    report: dict[str, Any] = {
        "hub": hub,
        "radius": hops,
        "seen": trail,
        "budget_ms": round(budget, 1),
        "asked": [],
        "dropped": [],
        "rejected": [],
        # What an administrative block refused, named so "why is this missing" has an answer.
        "blocked": [],
        "hub_trust": {},
    }

    local, arrivals = await asyncio.to_thread(_local, ask, hub)
    excluded = list(local["excluded"])
    left = budget - (perf_counter() - started) * 1000
    if hops >= 1 and left < MIN_FORWARD_MS:
        report["dropped"].append(
            {"hub": "*", "reason": f"budget spent: {left:.0f} ms left, {MIN_FORWARD_MS:.0f} ms needed to forward"}
        )
    elif hops >= 1:
        peers, skipped = await _choose_peers(trail, transport, lookups)
        report["dropped"] += skipped
        report["asked"] = [
            {
                "hub": profile["hub_id"],
                "name": profile.get("name") or profile["hub_id"],
                "description": profile.get("description") or "",
                "rating": trust,  # our own opinion of this peer, not its word for itself
                "url": url,
                "trust": trust,
            }
            for url, profile, trust in peers
        ]
        answers = await asyncio.gather(*[_ask_peer(url, ask, hops - 1, left, trail, transport) for url, _, _ in peers])
        for (url, profile, _), answer in zip(peers, answers, strict=False):
            if answer.get("code"):
                report["dropped"].append({"hub": profile["hub_id"], "reason": answer["reason"]})
                if answer["code"] == "deadline":
                    reputation.record_timeout(profile["hub_id"])
                continue
            out = answer["out"]
            reputation.record_answer(profile["hub_id"], answer["ms"], relayed=len(out.get("matches") or []))
            found, left_out = await _verified(out, profile, url, hub, transport, report, lookups)
            arrivals += found
            excluded += left_out

    arrivals, excluded = _screen(arrivals, excluded, report)
    matches = _dedup(arrivals)
    matches.sort(key=lambda m: (-m["federated_score"], m["hops"], m["id"]))
    for hub_id in {h for m in matches for h in m["provenance"]["path"] if h != hub} | {
        p["hub"] for p in report["asked"]
    }:
        report["hub_trust"][hub_id] = reputation.hub_trust(hub_id, _by_hub.get(hub_id))
    report["elapsed_ms"] = round((perf_counter() - started) * 1000, 1)
    return {
        "matches": matches,
        "excluded": excluded,
        "ranking_policy": local["ranking_policy"],
        "federated_ranking_policy": FEDERATED_RANKING_POLICY,
        "federation": report,
    }


def run(
    ask: dict[str, Any], radius: int, budget_ms: float | None = None, seen: list[str] | None = None
) -> dict[str, Any]:
    """Run a federated search from synchronous code (`hive.discover`, the MCP tool), on its own loop if needed."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(search(ask, radius, budget_ms, seen))
    with ThreadPoolExecutor(max_workers=1) as pool:  # already inside a loop: fan out from a thread of our own
        return pool.submit(asyncio.run, search(ask, radius, budget_ms, seen)).result()
