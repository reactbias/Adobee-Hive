"""Semantic similarity: the mismatches a substring search cannot see, and the floor that keeps it honest.

The index is `offers` and `needs` across every kind, so literal matching failed in every domain at once:
"haircut" missed "Cut, wash and finish", "web developer" missed "builds user interfaces in React". These tests
pin the offline provider — the one that has to work with no API key, no network and no new dependency — against
exactly those pairs, and against the pairs it must *not* match, because a floor-less similarity matches
everything to everything and ranking becomes noise.
"""

from __future__ import annotations

import pytest

from app import config, semantic

#: Pairs a substring search misses and a semantic one must not. Left: what someone types. Right: a line out of
#: a real vault in `testdata/vaults/` (or the brief's own example), as the owner wrote it.
MISMATCHES = [
    ("haircut", "Cut, wash and finish — CHF 65, about an hour."),
    ("haircut", "Beard trim — CHF 25."),
    ("web developer", "builds user interfaces in React"),
    ("someone to fix my bicycle", "Service and safety check — CHF 85, same day."),
    ("data visualisation", "Two-week dataviz sprint — CHF 9600, remote. Next free: 17 November."),
    ("photographer for my hotel", "Half-day shoot for a hotel or restaurant — CHF 950, edited within a week."),
    ("kubernetes help", "Deployment pipeline rescue — CHF 1250/day, remote or on-site in Zürich."),
    ("somewhere quiet to sleep", "Courtyard single — 1 guest, CHF 128, 3 of them. Quiet side."),
    ("breakfast without animal products", "Vegan breakfast — CHF 18, served all day."),
    ("technical writer", "On-call handover and runbook writing — CHF 900/day."),
    ("Haarschnitt", "Cut, wash and finish — CHF 65, about an hour."),
]

#: True matches this floor gives up, written down rather than quietly lost. Each is one concept in common
#: against a long line, so length normalisation pushes it under the floor. If a change makes one of these pass,
#: the test below fails and the pair moves up into MISMATCHES — that is the ratchet, and the right direction.
KNOWN_MISSES = [
    ("web developer", "A front-end contractor for Svelte work, six weeks, CHF 130/hour."),
    ("web developer", "An interface designer for the alarm list, two weeks remote."),
]

#: Pairs that must stay apart. Without these the floor is free to sink until the hub answers every query with
#: every card, which is the failure mode a similarity score introduces and the reason there is a floor at all.
UNRELATED = [
    ("haircut", "Payments integration review — CHF 2400, three days, remote."),
    ("haircut", "Terraform module cleanup — CHF 1000/day."),
    ("web developer", "Colour — from CHF 140."),
    ("web developer", "A pastry supplier within walking distance, three mornings a week."),
    ("kubernetes help", "Beard trim — CHF 25."),
    ("vegan breakfast", "Wheel build — CHF 180, three days."),
    ("somewhere quiet to sleep", "Payments integration review — CHF 2400, three days, remote."),
    ("asdkjh qwrtz plmok", "Cut, wash and finish — CHF 65, about an hour."),
    # The harder ones: a shared word root or a neighbouring trade, which is where a concept table that grew
    # too broad would show up first. "build" sat in the software concept once and made a wheel build look
    # like a pipeline build; that is why it does not any more.
    ("software developer", "Wheel build — CHF 180, three days."),
    ("hotel room", "The long table for a quiet morning meeting — free with an order, eight seats."),
    ("kubernetes", "Short design engagements on substation tooling — CHF 1200 a day."),
    ("a room for two nights", "Vegan breakfast — CHF 18, served all day."),
    ("photographer", "Payments integration review — CHF 2400, three days, remote."),
    ("bike repair", "Design system audit — CHF 180/hour."),
    ("haircut", "Portraits for a team — CHF 140 per person."),
]


@pytest.fixture
def offline() -> semantic.Provider:
    """The provider the demo runs on: no key, no network."""
    return semantic.OfflineProvider()


@pytest.mark.parametrize(("query", "text"), MISMATCHES)
def test_a_pair_a_substring_search_misses_is_found(offline, query, text):
    """The whole point: every one of these scores above the floor, and none of them matches literally."""
    assert query.lower() not in text.lower(), "this pair is not a mismatch; a substring search already finds it"
    score = offline.similarity(offline.encode(query), offline.encode(text))
    assert score >= semantic.SIMILARITY_FLOOR, f"{query!r} vs {text!r} scored {score:.3f}"


@pytest.mark.parametrize(("query", "text"), UNRELATED)
def test_the_floor_keeps_unrelated_things_apart(offline, query, text):
    """Everything matching everything is not search. These stay under the floor."""
    score = offline.similarity(offline.encode(query), offline.encode(text))
    assert score < semantic.SIMILARITY_FLOOR, f"{query!r} vs {text!r} scored {score:.3f}"


def test_the_floor_is_a_named_constant_with_room_on_both_sides(offline):
    """A floor of zero is no floor, and a floor of one lets nothing through."""
    assert 0 < semantic.SIMILARITY_FLOOR < 1
    best = max(offline.similarity(offline.encode(q), offline.encode(t)) for q, t in MISMATCHES)
    worst = max(offline.similarity(offline.encode(q), offline.encode(t)) for q, t in UNRELATED)
    assert worst < semantic.SIMILARITY_FLOOR <= best, (worst, best)


@pytest.mark.parametrize(("query", "text"), KNOWN_MISSES)
def test_what_the_offline_provider_still_misses_is_written_down(offline, query, text):
    """A table of synonyms is not an embedding, and this is the honest edge of it.

    One concept in common against a long line of prose falls under the floor. Keeping the list as a test rather
    than a comment means an improvement to the provider shows up here as a failure, and whoever makes it moves
    the pair into MISMATCHES instead of discovering the gap on stage.
    """
    score = offline.similarity(offline.encode(query), offline.encode(text))
    assert score < semantic.SIMILARITY_FLOOR, f"this pair passes now ({score:.3f}): move it into MISMATCHES"


def test_a_literal_match_scores_higher_than_a_merely_similar_one(offline):
    """Ranking rests on this: close is worth something, the same thing is worth more."""
    literal = offline.similarity(offline.encode("haircut"), offline.encode("Haircut — CHF 65."))
    similar = offline.similarity(offline.encode("haircut"), offline.encode("Cut, wash and finish — CHF 65."))
    assert literal > similar > semantic.SIMILARITY_FLOOR


def test_the_offline_provider_is_deterministic(offline):
    """No clock, no random, no network: the same two inputs always give the same number."""
    fresh = semantic.OfflineProvider()
    for query, text in MISMATCHES:
        first = offline.similarity(offline.encode(query), offline.encode(text))
        again = fresh.similarity(fresh.encode(query), fresh.encode(text))
        assert first == again, (query, text)


def test_similarity_is_bounded_and_symmetric(offline):
    """Cosine, not a score someone invented: in [0, 1] and the same both ways round."""
    for query, text in MISMATCHES + UNRELATED:
        forward = offline.similarity(offline.encode(query), offline.encode(text))
        backward = offline.similarity(offline.encode(text), offline.encode(query))
        assert 0.0 <= forward <= 1.0
        assert forward == pytest.approx(backward)
    assert offline.similarity(offline.encode("haircut"), offline.encode("haircut")) == pytest.approx(1.0)


def test_nothing_matches_nothing(offline):
    """An empty query, an empty card line, punctuation only: zero, never a crash and never a match."""
    for query, text in [("", "Cut, wash and finish"), ("haircut", ""), ("???", "???"), ("   ", "a")]:
        assert offline.similarity(offline.encode(query), offline.encode(text)) == 0.0


def test_best_picks_the_closest_line_and_says_which_terms_carried_it(offline):
    """A number nobody can read is not an open ranking. A hit carries the words that earned it."""
    lines = [
        "Colour — from CHF 140.",
        "Cut, wash and finish — CHF 65, about an hour.",
        "Someone to build us a booking page that an agent can read.",
    ]
    hit = semantic.best("haircut", lines, using=offline)
    assert hit is not None
    assert hit.text == lines[1]
    assert hit.score >= semantic.SIMILARITY_FLOOR
    assert "haircut" in hit.terms
    assert "cut" in hit.snippet.lower() and len(hit.snippet) <= semantic.SNIPPET_CHARS + 1


def test_best_returns_nothing_rather_than_the_least_bad_line(offline):
    """An honest "nobody offers this" is the promise `explore.ask` already keeps. No nearest-card forcing."""
    lines = ["Payments integration review — CHF 2400.", "Terraform module cleanup — CHF 1000/day."]
    assert semantic.best("haircut", lines, using=offline) is None
    assert semantic.best("haircut", [], using=offline) is None
    assert semantic.best("", lines, using=offline) is None


def test_the_offline_provider_is_the_one_in_use_without_a_key(monkeypatch):
    """The demo must work with no API key at all, and not as a degraded state we apologise for."""
    monkeypatch.setattr(config, "SEMANTIC_PROVIDER", "")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    semantic.reset()
    assert semantic.provider().name == semantic.OFFLINE
    assert semantic.provider().available() is True
    assert semantic.status()["provider"] == semantic.OFFLINE


def test_a_pinned_provider_wins_over_the_keys(monkeypatch):
    """Selection follows the LLM_PROVIDER pattern: by which key is set, overridable by config."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-not-a-real-key")
    monkeypatch.setattr(config, "SEMANTIC_PROVIDER", "offline")
    semantic.reset()
    assert semantic.provider().name == semantic.OFFLINE

    # An unknown name is not guessed at: the hub says what it is using, and it is the one that works.
    monkeypatch.setattr(config, "SEMANTIC_PROVIDER", "telepathy")
    semantic.reset()
    assert semantic.provider().name == semantic.OFFLINE


def test_the_status_never_carries_the_credential(monkeypatch):
    """/api/health is public. It may say whether a provider is live, never anything about the key."""
    monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-secret-value-0123456789")
    monkeypatch.setattr(config, "SEMANTIC_PROVIDER", "")
    semantic.reset()
    assert "secret" not in repr(semantic.status()).lower()
    assert "0123456789" not in repr(semantic.status())


def test_encoding_a_card_line_twice_costs_nothing(offline):
    """A search must not be noticeably slower than the substring one it replaces: vectors are cached per text."""
    text = "Cut, wash and finish — CHF 65, about an hour."
    offline.encode(text)
    before = semantic.cache_info()
    offline.encode(text)
    assert semantic.cache_info()["hits"] > before["hits"]
