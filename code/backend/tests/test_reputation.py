"""Two levels of trust: what this hub thinks of a peer *hub*, and what a business has earned.

A hub's reputation is this hub's own opinion, never a global score: new peers start low and earn trust slowly,
a hub that declares paid placement is downweighted, and one that relays cards which fail verification loses it.
"""

from app import hive, reputation

SIGNED = {"hub_id": "zurich", "verification": "signed", "paid_placement": False}


def setup_function():
    reputation.forget()


def test_a_new_peer_starts_at_low_trust():
    out = reputation.hub_trust("stranger")
    assert out["hub"] == "stranger"
    assert 0 < out["trust"] <= reputation.NEW_PEER_TRUST
    assert out["factors"]["trust_on_first_use"] == reputation.NEW_PEER_TRUST
    assert any("first" in why for why in out["why"])


def test_trust_accrues_slowly_and_never_in_one_jump():
    reputation.record_answer("zurich", latency_ms=120, relayed=2)
    before = reputation.hub_trust("zurich", SIGNED)["trust"]
    assert before < 0.7, "one clean answer must not make a stranger a trusted hub"
    for _ in range(3):
        reputation.record_answer("zurich", latency_ms=120, relayed=2)
    after_three = reputation.hub_trust("zurich", SIGNED)["trust"]
    assert 0 < after_three - before <= 3 * reputation.TRUST_PER_EXCHANGE + 1e-9
    for _ in range(200):
        reputation.record_answer("zurich", latency_ms=120, relayed=2)
    assert reputation.hub_trust("zurich", SIGNED)["trust"] - before <= reputation.MAX_EARNED + 1e-9


def test_a_hub_that_declares_paid_placement_is_downweighted():
    honest = reputation.hub_trust("honest", {"hub_id": "honest", "paid_placement": False})
    seller = reputation.hub_trust("seller", {"hub_id": "seller", "paid_placement": True})
    assert seller["trust"] < honest["trust"]
    assert seller["factors"]["open_ranking"] <= -reputation.PAID_PLACEMENT_PENALTY
    assert any("paid placement" in why for why in seller["why"])
    # A declared policy in words counts too, so a peer that only publishes ranking_policy is still judged.
    in_words = reputation.hub_trust("wordy", {"hub_id": "wordy", "ranking_policy": "Sponsored results rank first."})
    assert in_words["trust"] < honest["trust"]


def test_relaying_a_card_that_fails_verification_costs_trust():
    for _ in range(5):
        reputation.record_answer("zurich", latency_ms=100, relayed=4)
    clean = reputation.hub_trust("zurich", SIGNED)["trust"]
    reputation.record_invalid("zurich", 4)
    dirty = reputation.hub_trust("zurich", SIGNED)
    assert dirty["trust"] < clean
    assert dirty["factors"]["disputes"] < 0
    # Claiming to vet members and then relaying forgeries is worse than claiming nothing.
    assert dirty["factors"]["declared_vetting"] < 0


def test_a_peer_that_misses_its_deadline_loses_availability_trust():
    reputation.record_answer("bern", latency_ms=80)
    before = reputation.hub_trust("bern", SIGNED)["trust"]
    reputation.record_timeout("bern")
    out = reputation.hub_trust("bern", SIGNED)
    assert out["trust"] < before and out["factors"]["availability"] < 0


def test_path_trust_multiplies_every_carrier_and_hop_decay_shrinks():
    reputation.record_answer("zurich", latency_ms=100, relayed=1)
    one = reputation.path_trust(["zurich"])
    two = reputation.path_trust(["zurich", "bern"])
    assert 0 < two < one <= 1
    assert reputation.path_trust([]) == 1.0  # nothing was carried: this hub's own cards
    assert reputation.hop_decay(0) == 1.0
    assert reputation.hop_decay(2) < reputation.hop_decay(1) < 1.0


def test_business_reputation_is_the_signals_discovery_already_scores(client):
    card = hive.get_card("hotel-rheinblick")
    points = reputation.business_points(card["trust"])
    match = next(m for m in hive.discover(kind="hotel")["matches"] if m["id"] == "hotel-rheinblick")
    assert {k: match["score_breakdown"][k] for k in points} == points
    assert "receipt" in reputation.BOOKING_RECEIPT_RULE
