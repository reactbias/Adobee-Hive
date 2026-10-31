"""How honest a hub's ratings turned out to be.

A hub is not scored on how good its members are. It is scored on whether it **told the truth about
them**, measured against what our own people experienced afterwards. That distinction is the whole
design: a hub full of ordinary businesses, listed as ordinary, scores well. A hub that dresses them
up scores badly, by exactly as much as it exaggerated.

For every scored connection we hold two numbers: what the other hub published at the moment of
introduction, and what our human reported after the real meeting. The gap is the error.

    delta = published - realised          (tenths of a star, so 25 is two and a half stars)

**Lower is better, and the sign carries meaning.**

- Published 5.0, our user says 2.5  →  delta **+25**. Over-promised by two and a half stars. Worse.
- Published 2.5, our user says 5.0  →  delta **-25**. Under-promised. Better: the hub was modest and
  the introduction over-delivered, which is a hub worth asking.
- Published 4.0, our user says 4.0  →  delta **0**. Perfectly calibrated, which is the target.

A hub's score is the recency-weighted mean of its deltas. Old evidence fades (`HALF_LIFE_DAYS`), so
a hub that was careless in spring and careful since is not condemned for ever, and a hub that was
honest once cannot coast on it.

Two things this deliberately does not do. It does not punish a hub for members who are merely
mediocre — only for *misdescribing* them. And it cannot be bought: there is no number a hub can
publish about itself that moves this, because every input comes from our own users.

**A known way to game it.** Because credit is signed, a hub could systematically under-rate its own
members — list everyone at one star, let them turn out to be four — and bank negative deltas. The
credit side is therefore weighted by `UNDER_PROMISE_WEIGHT`, one constant, so damping or disabling
that is a one-line change once the behaviour is seen in the wild.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any

from . import connections

#: Scored connections needed before a number is reported at all. Below this the hub is "unproven":
#: one disappointing meeting is a story, not a measurement.
MIN_EVIDENCE = 3

#: Evidence older than this counts half as much. Long enough to survive a quiet month.
HALF_LIFE_DAYS = 90.0

#: How much credit under-promising earns, against the full cost of over-promising. 1.0 is symmetric,
#: as specified. Lower it to blunt the under-rating game described above.
UNDER_PROMISE_WEIGHT = 1.0

#: The over-promise, in tenths of a star, at which a hub's ranking weight reaches zero.
#: Two and a half stars of exaggeration is a hub whose word is worth nothing.
TRUST_FLOOR_DELTA = 25.0

#: What an unproven hub is worth while we find out. Matches reputation.NEW_PEER_TRUST.
UNPROVEN_TRUST = 0.35


def _age_weight(rated_at: str | None, now: datetime) -> float:
    """Recency weight, halving every HALF_LIFE_DAYS. Undated evidence is treated as old."""
    if not rated_at:
        return 0.5
    try:
        when = datetime.fromisoformat(rated_at)
    except ValueError:
        return 0.5
    days = max(0.0, (now - when).total_seconds() / 86_400)
    return float(2 ** (-days / HALF_LIFE_DAYS))


def delta(published: int, realised: int) -> int:
    """The error of one introduction, in tenths of a star. Positive means the hub over-promised."""
    return int(published) - int(realised)


def score(hub_id: str, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """This hub's standing with us: its mean signed error, and why.

    Returns `verdict` "unproven" until MIN_EVIDENCE connections have been scored, because a mean
    over two meetings is noise wearing a number's clothes.
    """
    rows = connections.rated_via(hub_id) if rows is None else rows
    now = datetime.now(UTC).replace(tzinfo=None)

    weighted_sum = weight_sum = 0.0
    over = under = exact = 0
    for row in rows:
        published, realised = row.get("published_rating"), row.get("rating")
        if published is None or realised is None:
            continue
        d = delta(published, realised)
        if d > 0:
            over += 1
        elif d < 0:
            under += 1
            d = int(round(d * UNDER_PROMISE_WEIGHT))
        else:
            exact += 1
        w = _age_weight(row.get("rated_at"), now)
        weighted_sum += d * w
        weight_sum += w

    n = over + under + exact
    mean = (weighted_sum / weight_sum) if weight_sum else 0.0
    proven = n >= MIN_EVIDENCE
    return {
        "hub": hub_id,
        "verdict": "calibrated"
        if proven and abs(mean) < 5
        else ("unproven" if not proven else "over-promises" if mean > 0 else "under-promises"),
        # Lower is better. Negative means the hub undersold what it offered.
        "error": round(mean, 1) if proven else None,
        "error_stars": round(mean / 10, 2) if proven else None,
        "evidence": n,
        "over_promised": over,
        "under_promised": under,
        "exact": exact,
        "weight": round(weight_sum, 2),
        "why": _why(proven, mean, n, over, under),
    }


def _why(proven: bool, mean: float, n: int, over: int, under: int) -> str:
    """One sentence an operator can read in the admin GUI."""
    if not proven:
        return f"{n} scored introduction{'s' if n != 1 else ''}; {MIN_EVIDENCE} needed before this means anything"
    stars = abs(mean) / 10
    if abs(mean) < 5:
        return f"ratings land within half a star of what our people report, over {n} introductions"
    if mean > 0:
        return f"over-promised by {stars:.1f} stars on average over {n} introductions ({over} too high)"
    return f"under-promised by {stars:.1f} stars on average over {n} introductions ({under} modest)"


def trust(hub_id: str, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Calibration expressed as the 0..1 ranking weight the search already multiplies by.

    Error is the honest unit and stays in `score()`. This is only the translation into what
    ranking needs: perfectly calibrated or better is 1.0, and TRUST_FLOOR_DELTA of exaggeration
    is 0.0. An unproven hub gets UNPROVEN_TRUST, not the benefit of the doubt.
    """
    s = score(hub_id, rows)
    if s["error"] is None:
        factor = UNPROVEN_TRUST
    else:
        # Only over-promising costs ranking weight; being modest is already its own reward.
        factor = 1.0 - max(0.0, float(s["error"])) / TRUST_FLOOR_DELTA
        factor = max(0.0, min(1.0, factor))
    return {**s, "factor": round(factor, 4)}


def ranked(hub_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Every hub we hold evidence about, best calibrated first. What the admin GUI lists."""
    hubs = hub_ids if hub_ids is not None else connections.hubs_with_ratings()
    out = [trust(h) for h in hubs]
    # Unproven hubs sort last: an absent measurement is not a good one.
    return sorted(out, key=lambda s: (s["error"] is None, s["error"] if s["error"] is not None else math.inf))
