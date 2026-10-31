"""The agent answers in the traveller's language: every reply it writes itself exists in EN, DE, FR and IT."""

import pytest

from app import replies, second_opinion

ASK = (
    "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, "
    "2026-12-04 to 2026-12-06, my name is Tobi Muster"
)


@pytest.mark.parametrize(
    ("header", "ready", "booked"),
    [
        ("de-CH,de;q=0.9,en;q=0.8", "Bereit zur Buchung", "Gebucht"),
        ("fr-CH", "Prêt à réserver", "Réservé"),
        ("it", "Pronto a prenotare", "Prenotato"),
        ("en-GB", "Ready to book", "Booked"),
    ],
)
def test_the_agent_replies_in_the_apps_language(client, header, ready, booked):
    out = client.post(
        "/api/agent", json={"messages": [{"role": "user", "content": ASK}]}, headers={"Accept-Language": header}
    ).json()
    assert out["reply"].startswith(ready)
    done = client.post("/api/agent/approve", json={"pending": out["pending"]}, headers={"Accept-Language": header})
    assert done.json()["reply"].startswith(booked)


def test_an_unknown_language_falls_back_to_english():
    assert replies.locale_from("ja-JP,ja;q=0.9") == "en"
    assert replies.locale_from("") == "en"
    assert replies.locale_from("es, fr;q=0.5") == "fr"


def test_every_reply_exists_in_all_four_languages_with_the_same_placeholders():
    import re

    holes = {k: sorted(re.findall(r"\{(\w+)", v)) for k, v in replies.TEXT["en"].items()}
    for locale in replies.LOCALES:
        assert set(replies.TEXT[locale]) == set(holes), locale
        for key, text in replies.TEXT[locale].items():
            assert sorted(re.findall(r"\{(\w+)", text)) == holes[key], (locale, key)
    assert not any("ß" in t for t in replies.TEXT["de"].values())


def test_the_rule_check_speaks_the_language_too():
    card = {"name": "Hotel X", "features": ["wifi"], "units": [], "trust": {"signature_valid": True}}
    note = second_opinion.rule_check({"features": ["sauna"]}, {}, card, "de")["note"]
    assert note == replies.say("de", "opinion.missing", name="Hotel X", missing="sauna")
