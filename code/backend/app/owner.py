"""The owner's experience: the café owner is not a developer.

They type what changed ("dogs are now welcome, 15 francs a night") and get back a proposed
new card plus a field-by-field diff. Nothing is published until they approve it.
"""

import json
import re
from typing import Any

from . import config, hive, llm

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
- Prices are numbers in CHF. Do not invent facts the owner did not state."""

LOCKED = ("id", "slug", "kind", "version", "published_at")


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


def propose(card_id: str, instruction: str) -> dict[str, Any]:
    """Turn the owner's plain-language change into a proposed card, a diff and a summary. Publishes nothing."""
    current = _strip(hive.get_card(card_id))
    if config.LLM_ENABLED:
        out = llm.structured(
            SYSTEM,
            f"<card>{json.dumps(current, ensure_ascii=False)}</card>\n<instruction>{instruction}</instruction>",
            EDIT_SCHEMA,
            model=config.CLAUDE_FAST_MODEL,
        )
        proposed, summary, mode = json.loads(out["card_json"]), out["summary"], "claude"
    else:
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
    current = hive.get_card(card_id)
    for key in LOCKED:
        proposed[key] = current.get(key)
    return hive.publish(_strip(proposed))
