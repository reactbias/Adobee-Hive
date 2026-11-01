"""Two levels of trust, kept apart on purpose.

**Hub reputation** is what *this* hub thinks of another Hive. It is computed locally and subjectively from what
this hub declared, what this hub has seen it do, and nothing else: there is no global score, no ranking of hubs
and no consensus protocol. A new peer starts at `NEW_PEER_TRUST` and earns more only slowly, over many clean
exchanges (trust on first use). The signals are a peer's declared versus observed verification level, whether its
declared ranking policy forbids paid placement, how available and fast it has been, and how many of the cards it
relayed failed verification here.

The incentive is the point: a federated result is ranked `local_relevance × hub_path_trust × hop_decay`, so a hub
that carries disputed or forged cards loses peer trust and *every* card it relays ranks lower in every hub that
noticed, including the cards of its own honest members. Vetting members well is therefore the hub's own interest,
and no hub can buy rank for anyone: declaring paid placement only costs trust.

**Business reputation** is what one business or person earned: verified reviews from signed booking receipts and
third-party attestations. Those are the signals `hive.discover` already scores; `business_points` is where they
live now, so hub trust and business trust can never be mistaken for each other. The rule behind a review does not
change: only a signed booking receipt can produce one.
"""

from dataclasses import dataclass, field
from typing import Any

BOOKING_RECEIPT_RULE = "only guests with a signed booking receipt can review"

# --- hub reputation ------------------------------------------------------------------------------
NEW_PEER_TRUST = 0.35  # trust on first use: enough to be asked, not enough to outrank a vetted peer
MIN_TRUST = 0.05
MAX_TRUST = 1.0
TRUST_PER_EXCHANGE = 0.03  # earned per clean answer...
MAX_EARNED = 0.25  # ...up to here, so trust takes many exchanges to build
VETTING_BONUS = 0.15  # declared vetting that this hub has seen hold up
VETTING_PENALTY = 0.2  # declared vetting contradicted by a forged or tampered card
OPEN_RANKING_BONUS = 0.1
PAID_PLACEMENT_PENALTY = 0.4  # a hub that sells rank is worth little as a source
AVAILABILITY_PENALTY = 0.2  # times the share of asks it missed
LATENCY_PENALTY_MS = 20_000.0  # a hub this slow loses the full MAX_LATENCY_PENALTY
MAX_LATENCY_PENALTY = 0.1
DISPUTE_PENALTY = 0.5  # times the share of relayed cards that failed verification here
VETTED_LEVELS = ("signed", "attested")  # declared verification levels that claim the hub checks its members
HOP_DECAY = 0.85  # confidence in a longer carrier chain, not a claim about distant businesses


@dataclass
class Observed:
    """What this hub has seen one peer do. Local, subjective, and never shared as a score."""

    answers: int = 0
    timeouts: int = 0
    latency_ms: float = 0.0
    relayed: int = 0
    invalid: int = 0
    cards: set[str] = field(default_factory=set)

    @property
    def attempts(self) -> int:
        """How often this hub asked the peer and the ask either came back or ran out of time."""
        return self.answers + self.timeouts

    @property
    def avg_latency_ms(self) -> float:
        """Mean round trip of the answers that arrived, 0 when none has."""
        return self.latency_ms / self.answers if self.answers else 0.0


# Per process, like the held bookings: an opinion this hub formed since it started, not a published score.
_observed: dict[str, Observed] = {}


def forget() -> None:
    """Drop every observation. For tests and the demo reset; a hub may also simply be restarted."""
    _observed.clear()


def observed(hub_id: str) -> Observed:
    """What this hub has seen `hub_id` do so far."""
    return _observed.setdefault(hub_id, Observed())


def record_answer(hub_id: str, latency_ms: float, relayed: int = 0) -> None:
    """A peer answered in time, carrying `relayed` cards."""
    seen = observed(hub_id)
    seen.answers += 1
    seen.latency_ms += max(0.0, latency_ms)
    seen.relayed += max(0, relayed)


def record_timeout(hub_id: str) -> None:
    """A peer missed the deadline, so its answer was dropped."""
    observed(hub_id).timeouts += 1


def record_invalid(hub_id: str, cards: int = 1, card_id: str = "") -> None:
    """A peer relayed a card that failed verification here: a forgery, a tamper, or a key it cannot back up."""
    seen = observed(hub_id)
    seen.invalid += max(1, cards)
    if card_id:
        seen.cards.add(card_id)


def _paid_placement(profile: dict[str, Any]) -> bool | None:
    """Whether a peer declares paid placement. None when it declares nothing either way.

    A peer's policy text is data: it is matched against fixed markers here, never read as an instruction.
    """
    if profile.get("paid_placement") is not None:
        return bool(profile["paid_placement"])
    policy = str(profile.get("ranking_policy", "")).lower()
    if "no paid placement" in policy or "no paid boost" in policy:
        return False
    return True if any(m in policy for m in ("paid placement", "paid boost", "sponsor")) else None


def hub_trust(hub_id: str, profile: dict[str, Any] | None = None) -> dict[str, Any]:
    """This hub's own opinion of a peer Hive: a trust factor in 0..1, every factor and reason spelled out.

    `profile` is the peer's `/.well-known/hive.json` as this hub read it (declared verification level, ranking
    policy). Without one, only observations count, so an undeclared peer stays near trust on first use.
    """
    profile = profile or {}
    seen = observed(hub_id)
    paid = _paid_placement(profile)
    vetted = str(profile.get("verification", "")).lower() in VETTED_LEVELS
    factors = {
        "trust_on_first_use": NEW_PEER_TRUST,
        "earned": round(min(MAX_EARNED, TRUST_PER_EXCHANGE * seen.answers), 3),
        # Declared vetting counts only once this hub has seen it hold up, and turns against the peer when a card
        # it relayed failed verification here.
        "declared_vetting": (
            -VETTING_PENALTY
            if vetted and seen.invalid
            else VETTING_BONUS
            if vetted and seen.relayed and not seen.invalid
            else 0.0
        ),
        "open_ranking": (-PAID_PLACEMENT_PENALTY if paid is True else OPEN_RANKING_BONUS if paid is False else 0.0),
        "availability": -round(AVAILABILITY_PENALTY * (seen.timeouts / seen.attempts), 3) if seen.attempts else 0.0,
        "latency": -round(min(MAX_LATENCY_PENALTY, seen.avg_latency_ms / LATENCY_PENALTY_MS), 3),
        "disputes": -round(DISPUTE_PENALTY * (seen.invalid / seen.relayed), 3) if seen.relayed else 0.0,
    }
    why = [
        f"{name.replace('_', ' ')} {value:+.2f}"
        for name, value in factors.items()
        if value or name == "trust_on_first_use"
    ]
    if paid is True:
        why.append("declares paid placement, so its results are discounted here")
    if seen.invalid:
        why.append(f"{seen.invalid} of {seen.relayed} relayed cards failed verification here")
    if not seen.attempts:
        why.append("never asked before: trust on first use")
    return {
        "hub": hub_id,
        "trust": round(max(MIN_TRUST, min(MAX_TRUST, sum(factors.values()))), 3),
        "factors": factors,
        "why": why,
        "observed": {
            "answers": seen.answers,
            "timeouts": seen.timeouts,
            "relayed": seen.relayed,
            "invalid": seen.invalid,
            "avg_latency_ms": round(seen.avg_latency_ms, 1),
        },
    }


def path_trust(carriers: list[str], profiles: dict[str, dict[str, Any]] | None = None) -> float:
    """Trust in a carrier chain: every hub that handled a card, multiplied. 1.0 for this hub's own cards.

    Multiplying is deliberate: a chain is only as trustworthy as its weakest carrier, and one more unknown hop
    can never make a result look better.
    """
    profiles = profiles or {}
    trust = 1.0
    for hub_id in carriers:
        trust *= hub_trust(hub_id, profiles.get(hub_id))["trust"]
    return round(trust, 4)


def hop_decay(hops: int) -> float:
    """Confidence left after `hops` carriers. Longer chains are less certain, not worse businesses."""
    return round(HOP_DECAY ** max(0, hops), 4)


# --- business and person reputation --------------------------------------------------------------


def business_points(trust: dict[str, Any]) -> dict[str, Any]:
    """The reputation points discovery gives one business: verified reviews, attestations, a valid signature.

    Verified reviews need a signed booking receipt, one review per receipt. That proves a booking and not a stay,
    and bookings are free, so a rating can still be inflated (LIMITS.md). An invalid signature is not a low score
    but a disqualification.
    """
    reviews = trust["verified_reviews"]
    return {
        "verified_reviews": round((reviews["average"] or 0) * 2, 1),
        "attestations": min(5, len(trust["attestations"])),
        "signature": 0 if trust["signature_valid"] else -100,
    }
