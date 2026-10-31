"""Whose rules? Signed rulesets a person chooses per request, named in every answer they shape.

Cards hold facts their owners signed. Whatever filters or ranks on top of them is judgement, and judgement differs
by who asks: a dog owners' club trusts only a vouched-for "dog-friendly", someone who slept badly wants quiet, someone
stressed wants two calm options instead of ten. So a ruleset is a document of its own, signed by whoever wrote it,
and published with its key in /.well-known/hive.json like a business's key.

Rules that keep this honest (keep them):
- A ruleset can only add: require tags, require third-party attestations, show fewer results. It cannot boost a
  business, hide its own effect or loosen the Hive's floor (constraints first, no paid placement, no profiling).
- The person picks it for one request; nothing about them is stored.
- The answer names the ruleset, its author and what it changed, and every business it left out says why.
"""

from typing import Any

from . import hive

FLOOR = "hive-floor"
ALLOWED = {"require_features", "require_attested", "max_results"}

# The authors are fictional. Real ones would publish and sign their own; the Hive would only pin their keys.
RULESETS: dict[str, dict[str, Any]] = {
    FLOOR: {
        "name": "The Hive's floor",
        "author": "Adobee Hive",
        "summary": hive.RANKING_POLICY + " The traveller's words and identity are never stored.",
        "rules": {},
    },
    "dogs-verified": {
        "name": "Dogs, verified",
        "author": "Basel Dog Owners Club (fictional)",
        "summary": "Dog-friendly counts only when a third party vouches for it.",
        "rules": {"require_features": ["dog-friendly"], "require_attested": ["dog-friendly"]},
    },
    "access-verified": {
        "name": "Access, verified",
        "author": "Basel Accessibility Forum (fictional)",
        "summary": "Accessible counts only after an independent audit.",
        "rules": {"require_features": ["accessible"], "require_attested": ["accessible"]},
    },
    "quiet-nights": {
        "name": "Quiet nights",
        "author": "Swiss Sleep Society (fictional)",
        "summary": "Only places that say they are quiet.",
        "rules": {"require_features": ["quiet"]},
    },
    "calm": {
        "name": "Two calm options",
        "author": "Adobee Hive",
        "summary": "For a stressful moment: the two best fits, and the rest set aside with reasons.",
        "rules": {"max_results": 2},
    },
}


def validate(rules: dict[str, Any]) -> None:
    """Refuse any rule that is not purely additive. Raises ValueError."""
    unknown = set(rules) - ALLOWED
    if unknown:
        raise ValueError(f"Not an additive rule: {', '.join(sorted(unknown))}. A ruleset can only narrow the floor.")
    if "max_results" in rules and not (isinstance(rules["max_results"], int) and rules["max_results"] >= 1):
        raise ValueError("max_results must be a positive whole number.")


def _key_id(ruleset_id: str) -> str:
    return f"ruleset:{ruleset_id}"


def document(ruleset_id: str) -> dict[str, Any]:
    """Return one ruleset as published: its terms plus a statement signed by its author's key."""
    if ruleset_id not in RULESETS:
        raise hive.HiveError(f"Unknown ruleset {ruleset_id!r}. See hive_rulesets.")
    body = {"id": ruleset_id, **RULESETS[ruleset_id], "floor": FLOOR}
    validate(body["rules"])
    return {**body, "statement": hive.sign_statement(_key_id(ruleset_id), body)}


def catalogue() -> dict[str, Any]:
    """Every ruleset a person can choose, each signed by its author."""
    return {"rulesets": [document(r) for r in RULESETS], "note": "Each one only adds to the Hive's floor."}


def keys() -> dict[str, str]:
    """Pinned public keys of the ruleset authors, for /.well-known/hive.json."""
    for ruleset_id in RULESETS:  # make sure every author has a key before it is published
        document(ruleset_id)
    prefix = _key_id("")
    return {k.removeprefix(prefix): v for k, v in hive.signing_keys().items() if k.startswith(prefix)}


def apply(result: dict[str, Any], ruleset_id: str) -> dict[str, Any]:
    """Narrow a discover() result by a ruleset and say what changed. Never adds or reorders a business."""
    doc = document(ruleset_id)
    rules, label = doc["rules"], f"{doc['name']} ({doc['author']})"
    kept, left_out = [], []
    for match in result["matches"]:
        # A match from a peer Hive carries the signed card it was verified against; a local one is read here.
        card = match.get("card") or hive.get_card(match["id"])
        feats = {f.lower() for f in card.get("features", [])}
        vouched = {a["claim"].lower() for a in card["trust"]["attestations"]}
        why_not = [f"no {f}" for f in rules.get("require_features", []) if f not in feats]
        why_not += [
            f"{c} is not attested by a third party"
            for c in rules.get("require_attested", [])
            if c in feats and c not in vouched
        ]
        if why_not:
            left_out.append({**match, "why_not": [f"{label}: {w}" for w in why_not]})
        else:
            kept.append({**match, "why": [*match["why"], f"meets {doc['name']}"]} if rules else match)
    changed = [f"left out {len(left_out)}: {', '.join(m['name'] for m in left_out)}"] if left_out else []
    limit = rules.get("max_results")
    if limit and len(kept) > limit:
        aside = kept[limit:]
        kept = kept[:limit]
        left_out += [{**m, "why_not": [f"set aside: {doc['name']} shows the best {limit}"]} for m in aside]
        changed.append(f"set aside {len(aside)} lower-ranked")
    return {
        **result,
        "matches": kept,
        "excluded": result["excluded"] + left_out,
        "ruleset": {
            "id": doc["id"],
            "name": doc["name"],
            "author": doc["author"],
            "summary": doc["summary"],
            "statement": doc["statement"],
            "changed": changed or ["nothing: every match already met it"],
        },
    }
