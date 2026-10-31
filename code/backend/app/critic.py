"""The critic: a third agent that always argues for the strongest alternative to the pick.

Tobias's rule for the traveller chat: three agents talk it through and bring the human one question only when all
three think it is good. The booking agent proposes, the verifier (second_opinion.py) checks the pick against the
request and the signed card, and the critic challenges the choice itself: why this hotel and not the next one?

It argues from the Hive's own open ranking, so it needs no model and costs nothing: it names the cheapest rival, or
the best-ranked one when none is cheaper, and concedes only when the pick ranks higher on the published scores.
"""

from typing import Any

from .replies import say


def _discovery(steps: list[dict[str, Any]]) -> dict[str, Any]:
    """The last ranking the booking agent received."""
    return next((s["output"] for s in reversed(steps) if s["tool"] == "hive_discover"), {})


def challenge(steps: list[dict[str, Any]], booking: dict[str, Any], locale: str = "en") -> dict[str, Any]:
    """Challenge a held booking. Returns the challenge, the booking agent's answer, a verdict and a closing note."""
    found = _discovery(steps)
    matches = found.get("matches", [])
    pick = next((m for m in matches if m["id"] == booking.get("card_id")), None)
    if pick is None:
        note = say(locale, "critic.unranked")
        return {"challenge": note, "answer": "", "verdict": "concern", "note": note, "rival": None}

    rivals = [m for m in matches if m["id"] != pick["id"]]
    if not rivals:
        return {
            "challenge": say(locale, "critic.alone", name=pick["name"]),
            "answer": say(locale, "critic.alone.answer", n=len(found.get("excluded", []))),
            "verdict": "agree",
            "note": say(locale, "critic.concede"),
            "rival": None,
        }

    price = pick.get("from_price_chf")
    cheaper = [m for m in rivals if price is not None and (m.get("from_price_chf") or price) < price]
    rival = min(cheaper, key=lambda m: m["from_price_chf"]) if cheaper else max(rivals, key=lambda m: m["score"])
    key = "critic.cheaper" if cheaper else "critic.rival"
    diff = round(price - rival["from_price_chf"]) if cheaper else 0
    text = say(locale, key, name=pick["name"], rival=rival["name"], diff=diff, score=f"{rival['score']:g}")

    if pick["score"] > rival["score"]:
        answer = say(
            locale,
            "critic.answer",
            name=pick["name"],
            score=f"{pick['score']:g}",
            rival=rival["name"],
            rival_score=f"{rival['score']:g}",
        )
        concede = say(locale, "critic.concede")
        return {"challenge": text, "answer": answer, "verdict": "agree", "note": concede, "rival": rival["name"]}
    note = say(locale, "critic.hold", rival=rival["name"])
    return {"challenge": text, "answer": "", "verdict": "concern", "note": note, "rival": rival["name"]}
