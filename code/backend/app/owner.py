"""The owner's experience: the café owner is not a developer.

They type what changed ("dogs are now welcome, 15 francs a night") and get back a proposed
new card plus a field-by-field diff. Nothing is published until they approve it.
"""

import json
import logging
import re
from typing import Any

from . import config, guard, hive, limits, llm, waiting

log = logging.getLogger(__name__)

#: The header an owner's credential arrives in, on a REST request and on an MCP connection alike.
#: It is never a parameter: a tool argument is written into the agent's transcript and its client's
#: logs, and a shared secret that has been written down in two places is no longer one secret.
TOKEN_HEADER = "X-Owner-Token"

EDIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["card_json", "summary"],
    "properties": {
        "card_json": {"type": "string", "description": "The complete updated card as a JSON object string"},
        "summary": {
            "type": "string",
            "description": "One sentence on what changed, for the owner, in the language of the instruction",
        },
    },
}

SYSTEM = """You maintain a local business's Hive card: the structured profile AI agents read instead of a website.
Apply the owner's instruction to the card and return the complete updated card.
- Change only what the instruction asks. Keep id, slug and kind unchanged. Keep every other field as is.
- features are short lowercase tags (e.g. "dog-friendly", "late check-in", "vegan options").
- Prices are numbers in CHF. Do not invent facts the owner did not state.
- Keep related fields consistent: a dog-friendly card must not keep a "No pets" policy."""

LOCKED = ("id", "slug", "kind", "version", "published_at", "valid_until")
#: One source for the whole-card ceiling: `limits.py` publishes it and `hive.publish` enforces
#: it too. Kept here so an owner edit is refused before a model run, not after one.
MAX_CARD_BYTES = limits.MAX_CARD_BYTES


def _strip(card: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in card.items() if k != "trust"}


def diff(old: dict[str, Any], new: dict[str, Any], prefix: str = "") -> list[dict[str, Any]]:
    """List field-level changes between two cards, with dotted paths for nested fields."""
    changes = []
    for key in sorted(set(old) | set(new)):
        path = f"{prefix}{key}"
        a, b = old.get(key), new.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            changes += diff(a, b, path + ".")
        elif a != b:
            changes.append({"field": path, "before": a, "after": b})
    return changes


def _owned(card_id: str) -> dict[str, Any]:
    card = hive.get_card(card_id)
    if not card["trust"]["claimed"]:  # compiled from a public website; only the business itself could claim it
        raise hive.HiveError("This card is unclaimed. Only the business can claim and edit it.")
    return card


def editable(token: str) -> str:
    """Why this hub will not take an edit from the holder of `token`, as a sentence, or "" when it will.

    An edit **fails closed**: a hub with no `OWNER_EDIT_TOKEN` set refuses every caller rather than
    accepting from any of them. `guard.require_secret` treats an unset secret as "the check is off",
    which is right for the owner studio's own REST routes — a person on their own machine, on a hub
    that has not been given a token yet — and wrong for a write that can arrive from anywhere the
    MCP endpoint can be reached, which is everywhere `/.well-known/hive.json` can be read. The same
    line `guard.require_admin` draws for the blocklist, for the same reason.

    Both sentences say what to do next, and neither repeats the token back: whatever arrived here is
    either this hub's secret or somebody's guess at it, and both belong only in the request.
    """
    if not config.OWNER_EDIT_TOKEN:
        return (
            "This hub has no OWNER_EDIT_TOKEN set, so it takes no card edits over MCP from anybody. "
            "Its operator sets one and gives it to the card's owner; tell your person that is what is "
            "missing. Reading the owner's view of the card needs no token and still works."
        )
    if not guard.secret_matches(token, config.OWNER_EDIT_TOKEN):
        return (
            f"Missing or wrong {TOKEN_HEADER}. Your person's hub gave them an owner token: put it in "
            f"the {TOKEN_HEADER} header of this MCP connection and call again. It is a header and not "
            "an argument on purpose — an argument would be written into this conversation."
        )
    return ""


def overview(card_id: str, token: str = "") -> dict[str, Any]:
    """What the owner of one card sees: the card, its bookings or hand-offs, missed demand, who is waiting.

    Without this hub's owner token a guest's name is reduced to initials and everything else is
    unchanged, so an entry can be read before anybody is asked for a credential. One function, so
    the REST route and the MCP tool cannot drift into two different ideas of what an owner may read.
    """
    view = hive.owner_overview(card_id)
    view["waiting"] = waiting.owner_view(card_id)
    if not guard.secret_ok(token, config.OWNER_EDIT_TOKEN):
        for booking in view["bookings"]:
            booking["guest_name"] = hive.mask_name(booking["guest_name"] or "")
    return view


def refusal(proposed: dict[str, Any]) -> str:
    """Why `hive.publish` would refuse this proposed card — the ceiling and the size that passed it — or "".

    `limits.vet` is the one function both publishing doors call, so asking it here is asking the
    same question the publish will ask, one step earlier: an agent is told that a 2400-character
    description is 400 over before it shows its person a diff it cannot publish.
    """
    try:
        limits.vet(_strip(proposed))
    except limits.LimitError as err:
        return str(err)
    return ""


def propose(card_id: str, instruction: str) -> dict[str, Any]:
    """Turn the owner's plain-language change into a proposed card, a diff and a summary. Publishes nothing."""
    current = _strip(_owned(card_id))
    proposed, summary_items = None, None
    if config.LLM_ENABLED:
        try:
            out = llm.structured(
                SYSTEM,
                f"<card>{json.dumps(current, ensure_ascii=False)}</card>\n<instruction>{instruction}</instruction>",
                EDIT_SCHEMA,
                model=config.CLAUDE_FAST_MODEL,
            )
            proposed, summary, mode = json.loads(out["card_json"]), out["summary"], config.LLM_PROVIDER
        except llm.FAILURES:  # outage or unusable answer: the rule-based edit still works
            log.exception("Model edit failed, using the rule-based edit")
    if not isinstance(proposed, dict):
        proposed, offline = mock_edit(current, instruction)
        summary, summary_items = offline["text"], offline["items"]
        mode = "mock"
    for key in LOCKED:
        proposed[key] = current.get(key)
    return {
        "card_id": current["id"],
        "proposed": proposed,
        "changes": diff(current, proposed),
        "summary": summary,
        "summary_items": summary_items,  # offline only: what changed, for the studio to word in the page's language
        "mode": mode,
    }


# Offline edits understand the owner studio's four languages. Verbs come before the tag, except German "X hinzufügen"
# and "füge X hinzu". Tags are stored in English, so common tags are mapped from their translations.
ADD, REMOVE = "add", "remove"
VERBS_BEFORE = {
    ADD: ("add", "ajouter", "ajoute", "ajoutez", "aggiungi", "aggiungere", "aggiungete", "füge", "ergänze"),
    REMOVE: (
        "remove",
        "entferne",
        "streiche",
        "retirer",
        "retire",
        "retirez",
        "supprimer",
        "supprime",
        "supprimez",
        "enlever",
        "enlève",
        "rimuovi",
        "rimuovere",
        "togli",
        "togliere",
        "elimina",
    ),
}
VERBS_AFTER = {ADD: ("hinzufügen", "ergänzen", "hinzu"), REMOVE: ("entfernen", "streichen")}
ARTICLES = {
    "a",
    "an",
    "the",
    "un",
    "une",
    "le",
    "la",
    "les",
    "l'",
    "des",
    "du",
    "der",
    "die",
    "das",
    "den",
    "ein",
    "eine",
    "einen",
    "il",
    "lo",
    "gli",
    "i",
    "uno",
    "una",
    "feature",
}
TAGS = {
    "dog-friendly": (
        "hundefreundlich",
        "hunde willkommen",
        "chiens acceptés",
        "chiens bienvenus",
        "animaux acceptés",
        "cani ammessi",
        "cani benvenuti",
    ),
    "quiet": ("ruhig", "calme", "tranquille", "tranquillo"),
    "breakfast": ("frühstück", "petit-déjeuner", "colazione"),
    "vegan breakfast": ("veganes frühstück", "petit-déjeuner végan", "petit-déjeuner vegan", "colazione vegana"),
    "parking": ("parkplatz", "parkplätze", "parcheggio"),
    "late check-in": ("später check-in", "check-in tardif", "check-in tardivo"),
    "accessible": ("barrierefrei", "rollstuhlgerecht", "accessibile"),
    "family rooms": ("familienzimmer", "chambres familiales", "camere familiari"),
    "pool": ("schwimmbad", "piscine", "piscina"),
    "bike rental": ("veloverleih", "velovermietung", "fahrradverleih", "location de vélos", "noleggio bici"),
}
CANON = {alias: tag for tag, aliases in TAGS.items() for alias in aliases}
# Words in unit names, so "Doppelzimmer", "double côté cour" and "doppia sul cortile" find "Courtyard double".
UNIT_WORDS = {
    "courtyard": ("courtyard", "hof", "cour", "cortile"),
    "double": ("double", "doppel", "doppia"),
    "single": ("single", "einzel", "simple", "singola"),
    "river": ("river", "fluss", "rhein", "fleuve", "rhin", "fiume", "reno"),
    "view": ("view", "blick", "vue", "vista"),
}


def _tag(words: str) -> str:
    parts = [w for w in words.strip().split() if w not in ARTICLES]
    tag = " ".join(parts).strip(" -")
    return CANON.get(tag, tag)


def _verb_and_tag(clause: str) -> tuple[str, str] | None:
    words = clause.split()
    if len(words) < 2:
        return None
    for verb, forms in VERBS_BEFORE.items():
        if words[0] in forms:
            rest = words[1:-1] if words[-1] in VERBS_AFTER[verb] else words[1:]  # "füge X hinzu"
            return verb, _tag(" ".join(rest))
    for verb, forms in VERBS_AFTER.items():
        if words[-1] in forms:
            return verb, _tag(" ".join(words[:-1]))
    return None


def _unit_in(clause: str, units: list[dict[str, Any]]) -> dict[str, Any] | None:
    best, best_words = None, 0
    for unit in units:
        words = unit["name"].lower().replace("-", " ").split()
        if all(any(alias in clause for alias in UNIT_WORDS.get(w, (w,))) for w in words) and len(words) > best_words:
            best, best_words = unit, len(words)
    return best


def mock_edit(card: dict[str, Any], instruction: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Understand add, remove and '<unit> <price>' in EN, DE, FR and IT, so the flow works offline.

    Returns the edited card and a summary: English text plus items the owner studio renders in the page's language.
    """
    card = json.loads(json.dumps(card))
    items: list[dict[str, Any]] = []
    for clause in re.split(r"[,.;\n]+", instruction.lower()):
        clause = " ".join(clause.replace("-", " - ").split()).replace(" - ", "-")
        found = _verb_and_tag(clause)
        if found and found[1]:
            verb, tag = found
            feats = card.setdefault("features", [])
            if verb == ADD and tag not in feats:
                feats.append(tag)
                items.append({"code": "added", "tag": tag})
            if verb == REMOVE and tag in feats:
                feats.remove(tag)
                items.append({"code": "removed", "tag": tag})
            policies = card.get("policies")
            if tag == "dog-friendly" and isinstance(policies, dict):  # keep the pets policy in line with the tag
                pets = str(policies.get("pets", ""))
                if verb == ADD and (not pets or pets.lower().startswith("no")):
                    policies["pets"] = "Dogs welcome"
                if verb == REMOVE and not pets.lower().startswith("no"):
                    policies["pets"] = "No pets"
            continue
        price = re.search(r"\d+", clause)
        unit = _unit_in(clause.replace("-", " "), card.get("units", [])) if price else None
        if unit:
            unit["price_chf"] = int(price.group())
            items.append({"code": "price", "unit": unit["name"], "price_chf": unit["price_chf"]})
    words = {"added": "added {tag}", "removed": "removed {tag}", "price": "{unit} now CHF {price_chf}"}
    text = (
        "Mock mode: " + ", ".join(words[i["code"]].format(**i) for i in items)
        if items
        else "Mock mode understood nothing; try 'add sauna' or set an API key."
    )
    return card, {"text": text, "items": items}


def apply(card_id: str, proposed: dict[str, Any]) -> dict[str, Any]:
    """Sign and publish the approved card. Identity fields (LOCKED) always keep their current values."""
    if len(hive.canonical(proposed)) > MAX_CARD_BYTES:
        raise hive.HiveError(f"A card is at most {MAX_CARD_BYTES // 1000} kB.")
    current = _owned(card_id)
    for key in LOCKED:
        proposed[key] = current.get(key)
    card = hive.publish(_strip(proposed))
    waiting.on_publish(card)  # agents waiting for exactly this change get a signed offer
    return card
