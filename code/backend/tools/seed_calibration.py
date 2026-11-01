"""Give this hub's peers real, differing calibration, through the real endpoints only.

A hub's standing is not something a hub publishes about itself. It is measured: for every scored
introduction the hub holds two numbers — what the carrying hub claimed the entity was worth at the
moment of introduction, and what our own human reported after the real meeting — and the signed gap
between them is the error (`app/calibration.py`). Lower is better, and a **negative** error means the
hub undersold what it offered, which earns credit rather than costing it.

Below `MIN_EVIDENCE` scored introductions a hub is reported as *unproven* rather than guessed at, so
on a fresh demo every row in the directory, the hub network and the admin peer table reads "Unproven,
no scored introductions yet". That is correct and it shows nothing. This script walks the real chain
until there is something to show:

    on the peer:   book a stay  ->  review it with a signed receipt   (this is the peer's *claim*)
    on this hub:   connect to that card with its signed card          (freezes the claim on the row)
    on this hub:   score the introduction                             (this is what our human found)

Nothing here writes to a database. Every step is an HTTP call a traveller's agent could make, which
is the point: if any of it is broken the script fails here rather than on stage. In particular the
peer's claim is produced the only way the product allows one to be produced — `hive.book` then
`hive.review`, a booking-backed review with a signed receipt — because `hub._published_rating` reads
`trust.verified_reviews.average` and nothing else can set it.

    python tools/seed_calibration.py --hub http://192.168.21.123:8420
    python tools/seed_calibration.py --hub http://127.0.0.1:8000 --plan
    python tools/seed_calibration.py --hub http://h:8420 --peer zurich=http://h:8421 --only zurich

## What it cannot do, and why

It seeds the **peers** of the hub it is pointed at, never that hub's own row. An introduction to an
entity the hub carries itself always lands with `published_rating = NULL`, because `hub.connect`
takes the stored card body (`hive.get_record`) whose trust block has not been computed, so there is
no `verified_reviews.average` to freeze. The home row in `GET /api/hub/directory` is therefore
permanently "unproven" however much the hub is used. That is a bug in the hub, not here, and it is
filed; run this against each of the three hubs in turn and every screen then shows two real numbers
and one honest blank.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta

#: Scored introductions a hub needs before its error is reported at all. Must match
#: `app.calibration.MIN_EVIDENCE`; `tests/test_seed_calibration.py` fails if the two drift.
MIN_EVIDENCE = 3

#: The verdict `app.calibration.score` gives inside this many tenths of a star of zero.
CALIBRATED_WITHIN = 5

#: How far ahead the seeded stays are booked, so they never collide with a demo booking.
FIRST_STAY_IN_DAYS = 45

#: How long to wait for a freshly started hub to learn its neighbour's keys before giving up. A hub
#: asks its peers every `PEER_ASK_SECONDS` in the background, and until that has happened once it
#: holds no pinned key for the peer's entities, so every cross-hub introduction is refused —
#: correctly, because an unverifiable stranger is exactly what that rule is for. Running this script
#: seconds after `./lan.sh up` is the ordinary case, so it waits rather than failing.
PEER_SETTLE_SECONDS = 60.0


@dataclass(frozen=True)
class Profile:
    """One hub's story: what it will claim about its members, and what our people will report.

    `published_stars` is whole stars 1..5, because a claim can only be made by reviewing a stay and
    `hive.review` takes whole stars. `realised` is tenths of a star, 0..50, because that is what a
    person actually gives on the score slider — 43 is 4.3 stars.
    """

    verdict: str
    published_stars: int
    realised: tuple[int, ...]
    why: str

    @property
    def published(self) -> int:
        """The claim in tenths of a star, the unit the ledger keeps."""
        return self.published_stars * 10

    def deltas(self) -> tuple[int, ...]:
        """Published minus realised, per introduction. Positive is over-promising."""
        return tuple(self.published - found for found in self.realised)

    def mean_error(self) -> float:
        """The error this profile should produce, before recency weighting (all of it is scored now)."""
        return sum(self.deltas()) / len(self.realised)

    def expected_verdict(self) -> str:
        """What `calibration.score` will call it. Mirrors that function and is pinned by the test."""
        if len(self.realised) < MIN_EVIDENCE:
            return "unproven"
        mean = self.mean_error()
        if abs(mean) < CALIBRATED_WITHIN:
            return "calibrated"
        return "over-promises" if mean > 0 else "under-promises"


#: The three shapes worth having on screen at once. The under-promising one matters most: a negative
#: error earning a *better* standing is the thing in this design nobody expects, and a demo that only
#: ever shows hubs being punished does not show it.
OVER = Profile(
    "over-promises",
    published_stars=5,
    realised=(25, 28, 30),
    why="claims five stars, our people found two and a half to three",
)
UNDER = Profile(
    "under-promises",
    published_stars=3,
    realised=(46, 48, 50),
    why="claims three stars and over-delivered every time; undersold itself",
)
CALIBRATED = Profile(
    "calibrated",
    published_stars=4,
    realised=(38, 40, 42),
    why="claims four stars and that is what our people found",
)

#: Which story belongs to which hub, so the three demo hubs are not three of the same.
PROFILES: dict[str, Profile] = {"zurich": OVER, "bern": UNDER, "basel": CALIBRATED}

#: For a hub not in PROFILES, so this works on a renamed or a fourth hub.
ROTATION = (OVER, UNDER, CALIBRATED)


def profile_for(hub_id: str, position: int = 0) -> Profile:
    """The story for this hub: its own if it has one, otherwise the next in the rotation."""
    return PROFILES.get(hub_id) or ROTATION[position % len(ROTATION)]


# ---------------------------------------------------------------- talking to a hub


class SeedError(RuntimeError):
    """A step the hub refused. Carries the hub's own words, which are usually the whole answer."""


def _call(url: str, body: dict | None = None, timeout: float = 30, bearer: str = "") -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"content-type": "application/json"} if data else {}
    if bearer:
        # The party's own credential for one introduction, which is what scoring takes now (#107).
        # A header, never a field: it is a bearer secret and a URL ends up in logs.
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, data=data, headers=headers)  # noqa: S310 - a hub URL the operator passed
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
            return json.loads(answer.read())
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")
        with contextlib.suppress(json.JSONDecodeError):
            detail = json.loads(detail).get("detail", detail)
        raise SeedError(f"{err.code} {url}: {detail}") from err
    except (urllib.error.URLError, TimeoutError) as err:
        raise SeedError(f"cannot reach {url}: {err}") from err


def get(hub: str, path: str, timeout: float = 30) -> dict:
    """GET JSON from a hub."""
    return _call(f"{hub.rstrip('/')}{path}", timeout=timeout)


def post(hub: str, path: str, body: dict, timeout: float = 30, bearer: str = "") -> dict:
    """POST JSON to a hub, optionally as the holder of one folder link secret."""
    return _call(f"{hub.rstrip('/')}{path}", body, timeout=timeout, bearer=bearer)


# ---------------------------------------------------------------- choosing what to introduce people to


def choose_card(cards: list[dict]) -> dict | None:
    """A card a claim can actually be made about: bookable, claimed, and freely connectable.

    Three bars, each of them a step this script has to take later:

    - **units**, or `hive.book` has nothing to book and there is no receipt, so no review and no claim;
    - **claimed**, because an unclaimed card is a lead compiled from public information — it is never
      bookable (`hive.discover` says so in `bookable`) and introducing someone to it is a hand-off;
    - **`sharing: public`**, so `hub.connect` opens the introduction at once. A `confirm` card waits
      for its owner's yes, and nobody is there to give it.

    Most rooms first: more units means the three stays cannot oversell the last one.
    """
    fit = [
        card
        for card in cards
        if card.get("units")
        and (card.get("trust") or {}).get("claimed") is not False
        and (card.get("sharing") or "public") == "public"
    ]
    return max(fit, key=lambda c: (len(c["units"]), c["id"]), default=None)


def stay_dates(n: int) -> tuple[str, str]:
    """Two ISO dates for the nth seeded stay, far enough out and never overlapping the others."""
    start = date.today() + timedelta(days=FIRST_STAY_IN_DAYS + n * 3)
    return start.isoformat(), (start + timedelta(days=1)).isoformat()


# ---------------------------------------------------------------- the three steps


def make_claim(peer_url: str, card_id: str, unit_id: str, stars: int, n: int) -> dict:
    """Book a night on the peer and review it, which is the only way a card gets a published rating.

    Returns the booking and the review. The review's stars become (or hold) the card's verified-review
    average, which `hub._published_rating` reads and freezes onto the next introduction.
    """
    check_in, check_out = stay_dates(n)
    booking = post(
        peer_url,
        f"/api/hive/cards/{card_id}/book",
        {
            "unit_id": unit_id,
            "check_in": check_in,
            "check_out": check_out,
            "guest_name": f"Calibration seed {n + 1}",
            "guests": 1,
            "notes": "seeded so the hub's standing has something to stand on",
        },
    )
    if not booking.get("receipt"):
        raise SeedError(f"{card_id} booked without a receipt, so no review can be left: {booking}")
    review = post(
        peer_url,
        "/api/hive/reviews",
        {"receipt": booking["receipt"], "rating": stars, "text": f"{stars} stars, as seeded."},
    )
    return {"booking": booking, "review": review}


def published_rating_of(peer_url: str, card_id: str) -> int | None:
    """What the peer currently claims this card is worth, in tenths of a star, as the hub reads it."""
    card = get(peer_url, f"/api/hive/cards/{card_id}")
    average = ((card.get("trust") or {}).get("verified_reviews") or {}).get("average")
    return None if average is None else int(round(float(average) * 10))


def peer_is_verifiable(home_url: str, peer_hub: str, card_id: str) -> bool:
    """Whether this hub can already verify a card the peer carries, asked read-only.

    A radius-1 search is the honest probe: it returns the peer's match with the signed `card` inline
    only once this hub has fetched the peer's key registry and checked the card against the key the
    peer pinned for it (`federation._verified`). If that is true, `POST /api/hub/connect` with the
    same card will be accepted; if it is not, it would be refused for want of a key registry.
    """
    try:
        found = get(home_url, f"/api/hive/discover?query={card_id}&radius=1", timeout=30)
    except SeedError:
        return False
    return any(m.get("id") == card_id and m.get("card") for m in found.get("matches") or [])


def wait_for_peer(home_url: str, peer_hub: str, card_id: str, seconds: float = PEER_SETTLE_SECONDS) -> bool:
    """Give a freshly started hub time to learn the peer's keys. True once it has."""
    deadline = time.monotonic() + seconds
    while True:
        if peer_is_verifiable(home_url, peer_hub, card_id):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(1.0)


def introduce(home_url: str, peer_url: str, peer_hub: str, card_id: str, requester: str) -> dict:
    """Ask this hub to introduce `requester` to an entity the peer carries, and log it here.

    The signed card has to travel with the request: this hub verifies it against the key the peer
    pinned for that entity rather than trusting whoever carried it (`hub._verified_remote`), and
    refuses it otherwise. Fetched from the peer itself for exactly that reason.
    """
    card = get(peer_url, f"/api/hive/cards/{card_id}")
    row = post(
        home_url,
        "/api/hub/connect",
        {"requester": requester, "entity_id": card_id, "target_hub": peer_hub, "card": card},
    )
    if row.get("state") != "open":
        raise SeedError(
            f"the introduction to {card_id} came back {row.get('state')!r}, not open, so it cannot be scored"
        )
    if row.get("published_rating") is None:
        raise SeedError(
            f"the introduction to {card_id} carries no published_rating, so scoring it teaches calibration nothing."
            " The peer's card has no verified-review average: the booking or the review did not take"
        )
    if not ((row.get("folder_key") or {}).get("secret")):
        raise SeedError(
            f"the introduction to {card_id} came back with no requester credential, so it cannot be scored."
            " `hub.connect` returns one under `folder_key.secret` and scoring needs it (#107)"
        )
    return row


def score(home_url: str, connection_id: str, rating: int, note: str, secret: str) -> dict:
    """Score an introduction, once and finally, as the person who asked for it.

    `secret` is the requester's own link secret, which the connect answer returned under
    `folder_key.secret`. The score belongs to the one party that asked for the introduction, so the
    route takes that and nothing hub-wide (#107); passing the connection id alone used to be enough
    and is exactly what this script must not go back to pretending.
    """
    return post(
        home_url,
        f"/api/hub/connections/{connection_id}/score",
        {"rating": rating, "note": note},
        bearer=secret,
    )


# ---------------------------------------------------------------- one peer, end to end


def seed_peer(
    home_url: str,
    peer_hub: str,
    peer_url: str,
    profile: Profile,
    say=print,
    settle: float = PEER_SETTLE_SECONDS,
) -> dict:
    """Give one peer the standing its profile describes, and return what the hub made of it."""
    cards = get(peer_url, "/api/hive/cards")
    card = choose_card(cards if isinstance(cards, list) else cards.get("cards") or [])
    if card is None:
        raise SeedError(
            f"{peer_hub} carries nothing a claim can be made about: a published rating needs a bookable,"
            " claimed, publicly connectable card, because it can only come from a reviewed stay"
        )
    unit = max(card["units"], key=lambda u: u.get("quantity", 1))
    say(f"  {peer_hub:8} via {card['id']} ({unit['id']}), aiming for {profile.verdict}")
    if not wait_for_peer(home_url, peer_hub, card["id"], settle):
        raise SeedError(
            f"this hub still cannot verify a card from {peer_hub} after {settle:.0f}s, so every introduction"
            f" to {card['id']} would be refused for want of a pinned key. Either {peer_hub} is not on this"
            " hub's peer list, or it has not answered yet"
        )

    for n, found in enumerate(profile.realised):
        make_claim(peer_url, card["id"], unit["id"], profile.published_stars, n)
        claimed = published_rating_of(peer_url, card["id"])
        requester = f"seed-{peer_hub}-{n + 1}"
        row = introduce(home_url, peer_url, peer_hub, card["id"], requester)
        out = score(home_url, row["id"], found, f"seeded: {profile.why}", row["folder_key"]["secret"])
        gap = out.get("gap")
        standing = out.get("hub_standing") or {}
        say(
            f"    {n + 1}/{len(profile.realised)} claimed {claimed / 10 if claimed else '?'}"
            f" · found {found / 10} · gap {gap:+d}"
            f" → {standing.get('verdict')} ({standing.get('evidence')} of {MIN_EVIDENCE})"
        )

    final = next((p for p in get(home_url, "/api/hub/standing")["peers"] if p["hub"] == peer_hub), {})
    return {"hub": peer_hub, "card": card["id"], "profile": profile, "standing": final}


def peers_of(home_url: str) -> list[tuple[str, str]]:
    """The peers this hub knows an address for, from its own directory. `(hub_id, url)`."""
    rows = get(home_url, "/api/hub/directory").get("hubs") or []
    return [(r["hub"], r["url"]) for r in rows if not r.get("home") and r.get("url") and not r.get("blocked")]


def parse_peer(text: str) -> tuple[str, str]:
    """`zurich=http://host:8421` as a pair."""
    hub_id, _, url = text.partition("=")
    if not hub_id or not url:
        raise argparse.ArgumentTypeError(f"a peer is written hub_id=url, got {text!r}")
    return hub_id, url


def main() -> int:
    """Seed every peer of one hub, or print the plan."""
    ap = argparse.ArgumentParser(description="Give a hub's peers real, differing calibration.")
    ap.add_argument("--hub", default="http://localhost:8000", help="the hub whose standing is being seeded")
    ap.add_argument(
        "--peer",
        action="append",
        type=parse_peer,
        default=[],
        metavar="ID=URL",
        help="a peer to seed, instead of reading this hub's directory. Repeatable",
    )
    ap.add_argument("--only", nargs="*", default=[], metavar="HUB", help="seed only these peer hub ids")
    ap.add_argument("--plan", action="store_true", help="print what would be done and change nothing")
    ap.add_argument(
        "--settle-seconds",
        type=float,
        default=PEER_SETTLE_SECONDS,
        help="how long to wait for a freshly started hub to learn a peer's keys",
    )
    args = ap.parse_args()

    try:
        peers = args.peer or peers_of(args.hub)
    except SeedError as err:
        print(f"! {err}")
        return 1
    if args.only:
        peers = [(hub_id, url) for hub_id, url in peers if hub_id in args.only]
    if not peers:
        print(f"{args.hub} has no peer with an address, so it has nobody to hold an opinion about")
        return 0

    plans = [(hub_id, url, profile_for(hub_id, i)) for i, (hub_id, url) in enumerate(peers)]
    print(f"{args.hub}: {len(plans)} peer(s)")
    for hub_id, url, profile in plans:
        print(
            f"  {hub_id:8} {profile.expected_verdict():15} claims {profile.published_stars}.0,"
            f" people find {', '.join(str(r / 10) for r in profile.realised)}"
            f" → error {profile.mean_error():+.1f}  {url}"
        )
    if args.plan:
        return 0
    print()

    failures = 0
    for hub_id, url, profile in plans:
        try:
            out = seed_peer(args.hub, hub_id, url, profile, settle=args.settle_seconds)
        except SeedError as err:
            print(f"  ✗ {hub_id}: {err}")
            failures += 1
            continue
        standing = out["standing"]
        mark = "✓" if standing.get("verdict") == profile.expected_verdict() else "·"
        print(
            f"  {mark} {hub_id:8} {standing.get('verdict')} · error {standing.get('error')}"
            f" ({standing.get('error_stars')} stars) over {standing.get('evidence')} introductions"
        )
        print(f"      {standing.get('why')}")
        if mark == "·":
            failures += 1

    print(f"\n{len(plans) - failures}/{len(plans)} peer(s) of {args.hub} now have a standing")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
