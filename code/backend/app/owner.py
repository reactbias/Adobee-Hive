"""The owner's experience: the café owner is not a developer.

They type what changed ("dogs are now welcome, 15 francs a night") and get back a proposed
new card plus a field-by-field diff. Nothing is published until they approve it.
"""

import json
import logging
import re
from typing import Any

from . import config, hive, llm, waiting

log = logging.getLogger(__name__)

EDIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["card_json", "summary"],
    "properties": {
        "card_json": {"type": "string", "description": "The complete updated card as a JSON object string"},
        "summary": {"type": "string", "description": "One sentence on what changed, for the owner"},
    },
}

SYSTEM = """You maintain a local business's Hive card: the structured profile AI agents read instead of a website.
Apply the owner's instruction to the card and return the complete updated card.
- Change only what the instruction asks. Keep id, slug and kind unchanged. Keep every other field as is.
- features are short lowercase tags (e.g. "dog-friendly", "late check-in", "vegan options").
- Prices are numbers in CHF. Do not invent facts the owner did not state.
- Keep related fields consistent: a dog-friendly card must not keep a "No pets" policy."""

LOCKED = ("id", "slug", "kind", "version", "published_at", "valid_until")
MAX_CARD_BYTES = 64_000


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


def propose(card_id: str, instruction: str) -> dict[str, Any]:
    """Turn the owner's plain-language change into a proposed card, a diff and a summary. Publishes nothing."""
    current = _strip(_owned(card_id))
    proposed = None
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
        proposed, summary = mock_edit(current, instruction)
        mode = "mock"
    for key in LOCKED:
        proposed[key] = current.get(key)
    return {
        "card_id": current["id"],
        "proposed": proposed,
        "changes": diff(current, proposed),
        "summary": summary,
        "mode": mode,
    }


def mock_edit(card: dict[str, Any], instruction: str) -> tuple[dict[str, Any], str]:
    """Understands 'add <tag>', 'remove <tag>', '<unit name> to <price>' so the flow works offline."""
    card = json.loads(json.dumps(card))
    low = instruction.lower()
    done = []
    for verb, tag in re.findall(r"\b(add|remove)\s+(?:feature\s+)?([a-z][a-z \-]+?)(?:[,.;]|$)", low):
        tag = tag.strip()
        feats = card.setdefault("features", [])
        if verb == "add" and tag not in feats:
            feats.append(tag)
            done.append(f"added {tag}")
        if verb == "remove" and tag in feats:
            feats.remove(tag)
            done.append(f"removed {tag}")
        policies = card.get("policies")
        if tag == "dog-friendly" and isinstance(policies, dict):  # keep the pets policy in line with the tag
            pets = str(policies.get("pets", ""))
            if verb == "add" and (not pets or pets.lower().startswith("no")):
                policies["pets"] = "Dogs welcome"
            if verb == "remove" and not pets.lower().startswith("no"):
                policies["pets"] = "No pets"
    for unit in card.get("units", []):
        m = re.search(rf"{re.escape(unit['name'].lower())}\D+(\d+)", low)
        if m:
            unit["price_chf"] = int(m.group(1))
            done.append(f"{unit['name']} now CHF {m.group(1)}")
    return card, (
        "Mock mode: " + ", ".join(done)
    ) if done else "Mock mode understood nothing; try 'add sauna' or set an API key."


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
