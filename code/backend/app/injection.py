"""Prompt-injection guard: business text is data, never instructions to the agent.

Every tool result the traveller's agent receives is scanned before the agent reads it. A string that addresses the
agent (ignore your user, book this now, don't tell them) is withheld and logged. The agent still sees that the
field existed, and the trace shows the human exactly what was withheld and why.

Rules are plain regular expressions in English, German, French and Italian, so the guard costs nothing and gives
the same answer every time. It is one layer: the owner's signature is the other, because text added after signing
breaks it (see agent.verify_card).
"""

import re
import unicodedata
from typing import Any

WITHHELD = "[withheld by the agent: this text gave instructions to agents]"

# Characters that render as nothing; used to hide instructions from human readers of a page.
INVISIBLE = re.compile("[​-‏‪-‮⁠-⁤﻿]")

_AGENT = r"(?:ai|llm|assistant|agent|bot|ki|ia)s?"
_PRINCIPAL = (
    r"(?:users?|travell?ers?|guests?|humans?|principals?|customers?|clients?|"
    r"nutzer\w*|benutzer\w*|gast|gäste\w*|kund\w*|utilisateur\w*|voyageur\w*|utent\w*|viaggiator\w*|ospit\w*)"
)
_ORDERS = (
    r"(?:instructions?|rules?|budget|prompt|guidelines?|constraints?|preferences?|"
    r"anweisung\w*|regeln|vorgaben|consignes?|règles|istruzion\w*|regole)"
)

# (code, reason, pattern): the code is stable for the UI to translate, the reason is for logs and the trace.
RULES: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "override",
        "tells the agent to ignore its user or instructions",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|ignorier\w*|vergiss|missachte\w*|ignorez|oubliez|ignora\w*|"
            r"dimentica\w*)\b.{0,60}?\b(?:" + _PRINCIPAL + "|" + _ORDERS + "|previous|prior|earlier|above)",
            re.S,
        ),
    ),
    (
        "addresses_agents",
        "addresses AI agents directly",
        re.compile(
            r"\b(?:note|message|attention|instruction|hinweis|achtung|avis|nota|attenzione)\s+"
            r"(?:to|for|an|für|aux?|pour|per|agli?|ai)\s+(?:all\s+|alle\s+|les\s+|tutti\s+gli\s+)?" + _AGENT + r"\b"
            r"|\b(?:dear|liebe[rs]?|chers?|caro|cari)\s+" + _AGENT + r"\b"
            r"|\bif you are an? " + _AGENT + r"\b"
            r"|\bas an? (?:ai|llm|language model)\b"
        ),
    ),
    (
        "role_change",
        "tries to change the agent's role",
        re.compile(
            r"\byou are now\b|\bnew instructions\b|\bsystem prompt\b|\bdeveloper message\b|\bjailbreak\b"
            r"|^\s*(?:system|assistant)\s*:|\[/?(?:system|inst)\]|<\|[a-z_]+\|>",
            re.M,
        ),
    ),
    (
        "hide_from_user",
        "asks the agent to hide something from its user",
        re.compile(
            r"\b(?:do not|don't|never|without)\s+(?:tell|telling|inform|informing|mention|mentioning|show|showing|"
            r"ask|asking|confirm|confirming|consult|consulting)\b.{0,30}?\b" + _PRINCIPAL + r"\b"
            r"|\bwithout (?:asking|confirmation|approval|consent)\b"
            r"|\bohne (?:nachfrage|rückfrage|zu fragen|bestätigung|zustimmung)\b"
            r"|\bsans (?:demander|confirmation|consentement|leur demander)\b"
            r"|\bsenza (?:chiedere|conferma|consenso)\b",
            re.S,
        ),
    ),
    (
        "tool_call",
        "tells the agent which tool to call",
        re.compile(r"\b(?:call|invoke|run|use|execute)\s+(?:the\s+)?(?:tool\s+)?`?(?:hive|hr)_[a-z_]+"),
    ),
    ("hidden_text", "hides text from human readers", re.compile(r"<!--|-->|\u0000")),
]


def _normalise(text: str) -> str:
    return INVISIBLE.sub("", unicodedata.normalize("NFKC", text)).lower()


def check(text: str) -> list[str]:
    """Return the codes of the rules this one string trips; empty if it reads as plain data."""
    if not text or len(text) < 12:
        return []
    codes = [code for code, _, rule in RULES if rule.search(_normalise(text))]
    if INVISIBLE.search(text) and codes:
        codes.append("invisible_characters")
    return codes


REASONS = {code: reason for code, reason, _ in RULES} | {"invisible_characters": "uses invisible characters"}


def _card_of(path: list[str | int], root: Any) -> dict[str, Any] | None:
    """The innermost dict on the path that names a business (has an id), so a finding can say whose text it was."""
    node, found = root, root if isinstance(root, dict) and "id" in root else None
    for key in path:
        node = node[key]
        if isinstance(node, dict) and "id" in node:
            found = node
    return found


def scan(value: Any) -> list[dict[str, Any]]:
    """Walk a tool result and return one finding per string that addresses the agent.

    A finding names the field (`path`), the business it belongs to, the reasons and the full text, so the trace
    can show the human what the agent refused to read.
    """
    findings: list[dict[str, Any]] = []

    def walk(node: Any, path: list[str | int]) -> None:
        if isinstance(node, dict):
            for key, child in node.items():
                if key != "trust":  # signatures and keys are base64, not prose
                    walk(child, [*path, key])
        elif isinstance(node, list):
            for i, child in enumerate(node):
                walk(child, [*path, i])
        elif isinstance(node, str) and (codes := check(node)):
            card = _card_of(path[:-1], value) or {}
            findings.append(
                {
                    "path": ".".join(str(p) for p in path),
                    "card_id": card.get("id"),
                    "business": card.get("name"),
                    "source": card.get("source"),
                    "codes": codes,
                    "reasons": [REASONS[c] for c in codes],
                    "text": INVISIBLE.sub("", node)[:500],
                }
            )

    walk(value, [])
    return findings


def redact(value: Any, findings: list[dict[str, Any]]) -> Any:
    """Return a copy of the tool result with every flagged string replaced by WITHHELD."""
    flagged = {f["path"] for f in findings}

    def walk(node: Any, path: str) -> Any:
        if isinstance(node, dict):
            return {k: walk(v, f"{path}.{k}" if path else k) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v, f"{path}.{i}" if path else str(i)) for i, v in enumerate(node)]
        return WITHHELD if path in flagged else node

    return walk(value, "")
