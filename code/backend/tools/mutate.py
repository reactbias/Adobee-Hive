"""Mutation testing for the federated search.

Coverage proves the tests *ran* a line. It does not prove they would notice if that line
were wrong. This makes small, deliberate changes to the source — flips a comparison, drops
the loop guard, keeps the longest path instead of the shortest — and checks the suite turns
red. A mutant the tests still pass is a hole, named and located.

    python tools/mutate.py                  # the curated mutants, the invariants that matter
    python tools/mutate.py --random 12      # 12 random operator and constant flips
    python tools/mutate.py --random 12 --seed 7
    python tools/mutate.py --all            # both
    python tools/mutate.py --workers 8      # how many mutants to check at once
    python tools/mutate.py --modules app/semantic.py,app/hive.py   # only these modules

Every mutant runs the whole SUITE, so the cost is (number of mutants) x (one suite run). Mutants
are independent of each other, so they run N at a time. Each worker gets its own copy of the tree
because a mutant is applied by editing the source in place: two workers in one tree would read each
other's mutants. The real checkout is never written to at all.

`--modules` is for the pull-request loop: a change to one module does not need every other
mutant re-proved. CI passes the modules the PR touched and runs the full set on main, so main is
never permanently unchecked. It filters *mutants*, never tests: every mutant that runs still runs
the whole SUITE, so nothing that used to kill a mutant stops being asked.

Exit code is the number of survivors, so CI can gate on it.
"""

from __future__ import annotations

import argparse
import atexit
import os
import queue
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"

# The test files that should notice. Keeping the subset small keeps a run under a minute.
# Every file that should notice a change to a TARGET module. A mutant can only be "killed" by a
# test that actually runs, so forgetting a file here produces a false all-clear — the one failure
# mode this tool must not have. test_suite_covers_every_target in tests/test_mutation.py pins it.
SUITE = [
    "tests/test_federation.py",
    "tests/test_offers_needs.py",
    "tests/test_pitch.py",
    "tests/test_reputation.py",
    "tests/test_hive.py",
    "tests/test_signed_cards.py",
    "tests/test_hub_trust.py",
    "tests/test_hub_api.py",
    "tests/test_folders.py",
    "tests/test_folder_api.py",
    "tests/test_registration.py",
    "tests/test_semantic.py",
    "tests/test_admin_manage.py",
    "tests/test_admin_peers.py",
    "tests/test_admin_services.py",
    "tests/test_semantic_search.py",
    "tests/test_discover_identity.py",
    "tests/test_discover_relevance.py",
    # After the relevance tests: its tie test publishes a card that matches their nonsense query.
    "tests/test_search_words.py",
    "tests/test_limits.py",
    "tests/test_owner_mcp.py",
    "tests/test_budgets.py",
    "tests/test_local_calibration.py",
    "tests/test_home_hub_row.py",
    "tests/test_forward_introduction.py",
    "tests/test_requester_identity.py",
    "tests/test_withdrawal_authority.py",
    "tests/test_introduction_authority.py",
    "tests/test_federated_blocks.py",
    "tests/test_federated_facts.py",
    "tests/test_sharing_enforced.py",
]


@dataclass
class Mutant:
    """One deliberate change: what it breaks, and where."""

    file: str
    why: str
    find: str
    replace: str
    count: int = 1
    #: What the report calls this one. Curated mutants are named by what they break; a random flip
    #: is named by its site, because "federation.py:112" is the only useful handle it has.
    label: str = ""
    #: Random flips match a whole line by regular expression; curated ones are literal text.
    regex: bool = False

    @property
    def path(self) -> Path:
        """The module this mutant edits, in the real checkout."""
        return APP / self.file

    def path_in(self, tree: Path) -> Path:
        """The module this mutant edits, inside a worker's copy of the tree."""
        return tree / "app" / self.file

    @property
    def title(self) -> str:
        """The label, falling back to a trimmed reason for the curated mutants."""
        return self.label or self.why[:46]


# --- The curated mutants -------------------------------------------------------------
# Each one is a bug a tired person could plausibly write at 3am, aimed at an invariant the
# design depends on. If the suite does not catch these, the suite is decorative.
CURATED: list[Mutant] = [
    Mutant(
        "guard.py",
        "the MCP door stops spending, so a budget exhausted over REST lets MCP run the same work",
        "    return over_budget(limiter, client)",
        '    return ""',
    ),
    Mutant(
        "guard.py",
        "every MCP caller shares one bucket, so one address spends everybody's budget",
        'return f"mcp:{host}" if host else IN_PROCESS',
        "return IN_PROCESS",
    ),
    Mutant(
        "guard.py",
        "an in-process call is waved through whatever the policy says, so peer fan-out goes uncounted",
        "if client == IN_PROCESS and not charge_in_process:",
        "if client == IN_PROCESS:",
    ),
    Mutant(
        "limits.py",
        "a discovery answer is never cut, so one call can carry every card on the hub",
        "    if len(matches) <= cap:\n        return found",
        "    if True:\n        return found",
    ),
    Mutant(
        "limits.py",
        "the answer ceiling is lifted, so a caller can ask for an unbounded answer again",
        "MAX_ANSWER_MATCHES = 50",
        "MAX_ANSWER_MATCHES = 10_000",
    ),
    Mutant(
        "limits.py",
        "the limit clamp loses its floor, so limit=0 answers with nothing instead of something",
        "cap = DEFAULT_ANSWER_MATCHES if limit is None else max(1, min(int(limit), MAX_ANSWER_MATCHES))",
        "cap = DEFAULT_ANSWER_MATCHES if limit is None else min(int(limit), MAX_ANSWER_MATCHES)",
    ),
    Mutant(
        "limits.py",
        "a cut answer stops saying it was cut, so a client cannot tell it from the whole Hive",
        '"truncated": True,',
        '"truncated": False,',
    ),
    Mutant(
        "federation.py",
        "a hop forwards its own radius, so the search never stops shrinking",
        "hops - 1, left, trail, transport",
        "hops, left, trail, transport",
    ),
    Mutant(
        "federation.py",
        "the loop guard goes: a cycle in the peer graph re-asks forever",
        'elif profile["hub_id"] not in seen:',
        "elif True:",
    ),
    Mutant(
        "federation.py",
        "the radius cap is lifted, so one call can fan out across the whole graph",
        "MAX_RADIUS = 3",
        "MAX_RADIUS = 99",
    ),
    Mutant(
        "federation.py",
        "a negative radius is no longer clamped to zero",
        "hops = max(0, min(int(radius), MAX_RADIUS))",
        "hops = min(int(radius), MAX_RADIUS)",
    ),
    Mutant(
        "federation.py",
        "the deadline stops being enforced: one slow peer stalls every search",
        "if hops >= 1 and left < MIN_FORWARD_MS:",
        "if hops >= 1 and False:",
    ),
    Mutant(
        "federation.py",
        "breadth is unbounded, so reach 2 becomes a broadcast storm",
        "            if len(taken) >= PEERS_PER_HOP:\n                records.append",
        "            if False:\n                records.append",
    ),
    Mutant(
        "federation.py",
        "a peer's own claim about itself becomes its rating, so trust can be self-declared",
        '"rating": trust,  # our own opinion of this peer, not its word for itself',
        '"rating": 1.0,',
    ),
    Mutant(
        "federation.py",
        "the carrier's own copy of the facts wins again, so a peer can rename what it relays",
        "**{key: card[key] for key in SIGNED_FACTS if key in card},",
        "**{key: match[key] for key in SIGNED_FACTS if key in match},",
    ),
    Mutant(
        "federation.py",
        "the signature verdict is taken from the carrier instead of from our own check",
        '        "signature_valid": True,\n        "card": card,',
        '        "signature_valid": match.get("signature_valid", True),\n        "card": card,',
    ),
    Mutant(
        "federation.py",
        "the allowlist becomes a merge, so a field a carrier invented rides along as fact",
        "    return {\n        **{key: card[key] for key in SIGNED_FACTS if key in card},",
        "    return {\n        **match,\n        **{key: card[key] for key in SIGNED_FACTS if key in card},",
    ),
    Mutant(
        "federation.py",
        "whether a card is claimed comes from the carrier, so a compiled lead relays as a real business",
        '"claimed": (card.get("provenance") or {}).get("verified_by_owner") is not False,',
        '"claimed": match.get("claimed", True),',
    ),
    Mutant(
        "federation.py",
        "a peer's exclusion stops saying whose words it is, so the hub appears to vouch for it",
        '"asserted_by": carrier["hub_id"],',
        '"asserted_by": "",',
    ),
    Mutant(
        "hive.py",
        "an unreviewed business reports a rating of zero instead of none earned yet",
        '"rating": trust["verified_reviews"]["average"],',
        '"rating": 0,',
    ),
    Mutant(
        "hive.py",
        "the constraint weight is granted again, so an ask with nothing to check pays everyone 50",
        '"constraints": CONSTRAINT_POINTS if found["checked"] and not misses else 0,',
        '"constraints": 0 if misses else CONSTRAINT_POINTS,',
    ),
    Mutant(
        "hive.py",
        "what an entity offers or needs stops counting, so the index is prose again",
        '"offers_needs": min(30, 10 * len(side_hits)),',
        '"offers_needs": 0,',
    ),
    Mutant(
        "hive.py",
        "being close to the ask stops counting, so a haircut search misses 'cut, wash and finish' again",
        '"semantic": close[2] if close else 0,',
        '"semantic": 0,',
    ),
    Mutant(
        "hive.py",
        "a merely similar entity is paid like one that really offers the thing, so literal stops winning",
        "SEMANTIC_POINTS = 8",
        "SEMANTIC_POINTS = 10",
    ),
    Mutant(
        "hive.py",
        "prose is paid like a structured claim, so saying it is worth as much as offering it",
        "SEMANTIC_TEXT_POINTS = 4",
        "SEMANTIC_TEXT_POINTS = 10",
    ),
    Mutant(
        "hive.py",
        "the semantic side ignores looking_for, so who offers a thing is answered with who wants it",
        'sides = {"offers": offer_hits, "needs": need_hits} if looking_for == "any" else {looking_for: side_hits}',
        'sides = {"offers": offer_hits, "needs": need_hits}',
    ),
    Mutant(
        "hive.py",
        "looking_for is ignored, so a search for who offers a thing answers with who wants it",
        'need_hits = _side_hits(card, "needs", terms) if looking_for in ("needs", "any") else []',
        'need_hits = _side_hits(card, "needs", terms)',
    ),
    Mutant(
        "hive.py",
        "people are hidden from discovery again, so every developer on the hub is invisible",
        "NOT_DISCOVERABLE: set[str] = set()",
        'NOT_DISCOVERABLE: set[str] = {"person"}',
    ),
    Mutant(
        "hive.py",
        "missed demand is logged against a person: a record of the times they were passed over",
        'NO_MISSED_DEMAND = {"person"}',
        "NO_MISSED_DEMAND: set[str] = set()",
    ),
    Mutant(
        "hive.py",
        "an unclaimed card reports itself as bookable, so a lead passes for a business that agreed",
        '"bookable": bool(card.get("units")) and trust["claimed"],',
        '"bookable": True,',
    ),
    Mutant(
        "hive.py",
        "the relevance threshold goes, so every door answers every query with the whole hub again",
        "    if ask_had_content and not include_irrelevant:",
        "    if False:",
    ),
    Mutant(
        "hive.py",
        "reputation counts as relevance, so four well-reviewed hotels answer a nonsense query",
        'RELEVANCE_COMPONENTS = ("constraints", "text_relevance", "offers_needs", "semantic", "proximity")',
        'RELEVANCE_COMPONENTS = ("constraints", "text_relevance", "offers_needs", "semantic", "proximity",'
        ' "verified_reviews", "attestations")',
    ),
    Mutant(
        "hive.py",
        "a browse is thresholded too, so 'show me what is on this hub' answers with nobody",
        "return bool((text and not names_only_a_place) or features or near or max_price_chf is not None)",
        "return True",
    ),
    Mutant(
        "hive.py",
        "the counts stop being reported, so a caller cannot tell an empty answer from a filtered one",
        '"matched": len(matches),',
        '"matched": considered,',
    ),
    Mutant(
        "semantic.py",
        "the similarity floor goes, so every card is a little bit like every query and ranking is noise",
        "SIMILARITY_FLOOR = 0.20",
        "SIMILARITY_FLOOR = 0.0",
    ),
    Mutant(
        "semantic.py",
        "the concept table stops being consulted, so semantic search is substring search again",
        'bag += [(f"c:{concept}", CONCEPT_WEIGHT) for concept in concepts]',
        "bag += []",
    ),
    Mutant(
        "semantic.py",
        "the tokeniser is a list of remembered letters again, so French and Italian queries find nothing",
        'LETTERS = re.compile(r"[^\\W\\d_]+")',
        'LETTERS = re.compile(r"[a-zäöü]+")',
    ),
    Mutant(
        "semantic.py",
        "nothing is folded before tokenising, so an accent or a capital hides a word from both paths",
        'folded = FRENCH_JAI.sub(" ", fold(text))',
        'folded = FRENCH_JAI.sub(" ", text)',
    ),
    Mutant(
        "semantic.py",
        "the stopword list stops being folded, so every umlaut function word is unreachable again",
        "    fold(word)\n    for word in",
        "    word\n    for word in",
    ),
    Mutant(
        "hive.py",
        "the literal path gets its own short stopword list back, so filler words are evidence again",
        "STOPWORDS = semantic.STOPWORDS",
        'STOPWORDS = frozenset({"book", "basel", "hotel", "near", "under", "with", "that"})',
    ),
    Mutant(
        "hive.py",
        "the literal search stops folding the card, so a folded query term cannot match an accented card",
        'text = semantic.fold(" ".join(_side_texts(card, side)))',
        'text = " ".join(_side_texts(card, side)).lower()',
    ),
    Mutant(
        "hive.py",
        "any word is a literal term again, so a two-letter accident is worth ten points",
        "MIN_TERM_LENGTH = 4",
        "MIN_TERM_LENGTH = 1",
    ),
    Mutant(
        "hive.py",
        "a tie on points is settled by whatever order the cards came back in, not by the closer match",
        'matches.sort(key=lambda m: (m["score"], closeness.get(m["id"], 0.0)), reverse=True)',
        'matches.sort(key=lambda m: m["score"], reverse=True)',
    ),
    Mutant(
        "hive.py",
        "a withdrawn entity is discoverable again, so kicking one off the hub does nothing",
        "    if not include_withdrawn:",
        "    if False:",
    ),
    Mutant(
        "hive.py",
        "a withdrawn entity can still be booked, so the hub sells what it no longer carries",
        '    carried(card["id"])\n    free = {u["id"]: u for u in _units_free(card, check_in, check_out, guests)}',
        '    free = {u["id"]: u for u in _units_free(card, check_in, check_out, guests)}',
    ),
    Mutant(
        "peers.py",
        "a peer an operator removed is asked again, so dropping a neighbour does nothing",
        "    return [url for url, state in rows if state == ACTIVE]",
        "    return [url for url, state in rows]",
    ),
    Mutant(
        "peers.py",
        "the environment wins over the stored list, so nothing an operator adds is ever asked",
        "    if not rows:",
        "    if True:",
    ),
    Mutant(
        "peers.py",
        "a peer change is accepted with no reason, so nobody can tell later why a hub was dropped",
        '        raise PeerError("a peer change needs a reason: someone has to be able to read this list later")',
        '        reason = "none given"',
    ),
    Mutant(
        "services.py",
        "a stored key comes back in the status call, so the panel shows the key it promised never to",
        '        "fingerprint": str(row["fingerprint"]) if stored else "",',
        '        "fingerprint": str(row["secret"]) if stored else "",',
    ),
    Mutant(
        "services.py",
        "a vendor's error keeps the key it echoed back, so a bad key is written into the database",
        '    text = message.replace(secret, "[key]") if secret else message',
        "    text = message",
    ),
    Mutant(
        "services.py",
        "an empty key is stored, so a service reads as configured and every call fails",
        '    if not secret:\n        raise ServiceError("a key cannot be empty; clear the service instead")',
        '    if False:\n        raise ServiceError("a key cannot be empty; clear the service instead")',
    ),
    Mutant(
        "removals.py",
        "a removal is accepted with no reason, so nobody can tell later why an entity is missing",
        '        raise RemovalError("a removal needs a reason: someone has to be able to read this list later")',
        '        reason = "none given"',
    ),
    Mutant(
        "audit.py",
        "the reason is dropped on the way into the ledger, so it records only that something happened",
        '        "reason": (reason or "")[:MAX_REASON],',
        '        "reason": "",',
    ),
    Mutant(
        "calibration.py",
        "the error loses its sign, so a modest hub is punished like a boastful one",
        "return int(published) - int(realised)",
        "return abs(int(published) - int(realised))",
    ),
    Mutant(
        "calibration.py",
        "a hub is scored on one introduction, so a single bad day condemns it",
        "MIN_EVIDENCE = 3",
        "MIN_EVIDENCE = 1",
    ),
    Mutant(
        "calibration.py",
        "over-promising stops costing ranking weight at all",
        "max(0.0, 1.0 - max(0.0, float(error)) / TRUST_FLOOR_DELTA)",
        "1.0",
    ),
    Mutant(
        "connections.py",
        "a stale introduction can be scored after all, inviting score-settling",
        'if row["state"] == STALE:',
        "if False:",
    ),
    Mutant(
        "connections.py",
        "a connection can be scored twice, so a rating becomes negotiable",
        'if row["state"] == RATED:',
        "if False:",
    ),
    Mutant(
        "connections.py",
        "a booking can be made with no folder link at all, so the whole handshake is decorative",
        "link = link_for(requester, target, folder_link, opening=not needs_confirmation)",
        'link = {"id": ""}',
    ),
    Mutant(
        "connections.py",
        "a booking opens on a folder link the other side never accepted",
        'if opening and link["state"] != folders.ESTABLISHED:',
        "if False:",
    ),
    Mutant(
        "folders.py",
        "a hidden or private file becomes readable, which is the one thing the folder link must never do",
        'if entry["visibility"] not in ADMITTED:',
        "if False:",
    ),
    Mutant(
        "folders.py",
        "a grant needs only a link that was asked for, which makes the other side's yes decorative",
        'if link is None or link["state"] != ESTABLISHED:',
        "if link is None:",
    ),
    Mutant(
        "folders.py",
        "an unmarked file is published, so a folder opens itself by saying nothing",
        "DEFAULT_VISIBILITY = PUBLIC_SUMMARY",
        "DEFAULT_VISIBILITY = PUBLIC",
    ),
    Mutant(
        "folders.py",
        "the read surface hands over everything the owner listed, hidden and private included",
        "SERVED: frozenset[str] = frozenset({PUBLIC, PUBLIC_SUMMARY})",
        "SERVED: frozenset[str] = frozenset(VISIBILITIES)",
    ),
    Mutant(
        "folders.py",
        "a symlink out of the folder is listed and served as one of the owner's own files",
        "if file.is_symlink() or any((folder / part).is_symlink() for part in _prefixes(rel)):",
        "if False:",
    ),
    Mutant(
        "folders.py",
        "withdrawing a link leaves it established, so every read it allowed keeps working",
        'cur.execute("UPDATE folder_links SET state = ? WHERE id = ?", [REVOKED, link_id])',
        'cur.execute("UPDATE folder_links SET state = ? WHERE id = ?", [ESTABLISHED, link_id])',
    ),
    Mutant(
        "folder_keys.py",
        "a revoked link still reads: the state is trusted from mint time instead of re-read per request",
        '    if link["state"] != folders.ESTABLISHED:\n        return None\n    return key',
        "    return key",
    ),
    Mutant(
        "folder_keys.py",
        "a revoked secret keeps working at both doors, so losing a laptop cannot be undone",
        'WHERE secret_sha256 = ? AND revoked_at IS NULL"',
        'WHERE secret_sha256 = ?"',
    ),
    Mutant(
        "folder_keys.py",
        "the link secret is stored in the clear, so a stolen dump is a stolen folder",
        '[key_id, _now(), link["id"], me, peer, fingerprint(secret)],',
        '[key_id, _now(), link["id"], me, peer, secret],',
    ),
    Mutant(
        "hub.py",
        "a connection id authorises its own answer again, so a stranger fakes a consent",
        "        raise HubError(_no_authority(row, action))",
        "        proof = BY_LINK",
    ),
    Mutant(
        "hub.py",
        "any live link secret answers any introduction, not only one on this row's own link",
        '    if key is None or key["link"] != row["folder_link"]:',
        "    if key is None:",
    ),
    Mutant(
        "hub.py",
        "either party's secret answers for the other, so a requester consents on the owner's behalf",
        '        return key["handle"] == folders.handle_for(who)',
        '        return key["peer"] == folders.handle_for(who)',
    ),
    Mutant(
        "hub.py",
        "a requester's secret confirms as well as declines, so the owner's yes is not theirs to give",
        '    elif _party_by_link(row, secret, row["requester"]) and action == "decline":',
        '    elif _party_by_link(row, secret, row["requester"]):',
    ),
    Mutant(
        "hub.py",
        "an unset owner token authorises everybody, the way an owner edit over REST would",
        "    elif owner_token and guard.secret_matches(owner_token, config.OWNER_EDIT_TOKEN):",
        "    elif guard.secret_ok(owner_token, config.OWNER_EDIT_TOKEN):",
    ),
    Mutant(
        "hub.py",
        "a decision signature is accepted without being checked against the target's registered key",
        '    if not hive.verify(decision_statement(row["id"], action, nonce, expires), signature, pinned):',
        "    if False:",
    ),
    Mutant(
        "hub.py",
        "an expired decision signature still answers, so a captured one answers for ever",
        '    if _expired(expires):\n        raise HubError(f"this decision document has expired',
        '    if False:\n        raise HubError(f"this decision document has expired',
    ),
    Mutant(
        "hub.py",
        "a score can be given by anybody again, so one person's one final score is anyone's to spend",
        "            f\"scoring {row['id']} needs the requester's own credential: the\"",
        "            f\"unreachable {row['id']}\"",
    ),
    Mutant(
        "hub.py",
        "a hub-wide owner token scores, so the requester's one report is not theirs",
        '    if _party_by_link(row, secret, row["requester"]):\n        proof = BY_LINK\n    elif by_operator:',
        "    if True:\n        proof = BY_LINK\n    elif by_operator:",
    ),
    Mutant(
        "connections.py",
        "a transition stops being conditional, so two racing callers both win",
        'cur.execute(f"UPDATE hub_connections SET {sets} WHERE id = ? AND state = ?", [*args, connection_id, was])',
        'cur.execute(f"UPDATE hub_connections SET {sets} WHERE id = ?", [*args, connection_id])',
    ),
    Mutant(
        "folder_keys.py",
        "a party lookup stops noticing a revoked link, so withdrawing a link leaves its authority",
        '    return None if link["state"] == folders.REVOKED else key',
        "    return key",
    ),
    Mutant(
        "folder_keys.py",
        "the default stops refusing a link nobody accepted, so `pending_ok` means nothing and reads open early",
        'if link["state"] != folders.ESTABLISHED and not pending_ok:\n        raise KeyError_(',
        "if False:\n        raise KeyError_(",
    ),
    Mutant(
        "main.py",
        "folder reads are counted per address again, so one agent spends another's budget",
        'guard.folder_reads.check(request, key=caller["link"])',
        "guard.folder_reads.check(request)",
    ),
    Mutant(
        "main.py",
        "the manifest promises bytes the file route would refuse, so readable stops meaning anything",
        '{**f, "readable": bool(f["readable"]) and f["visibility"] in folders.SERVED}',
        '{**f, "readable": bool(f["readable"])}',
    ),
    Mutant(
        "main.py",
        "a grant may name a pattern again, so one write opens a folder the owner listed one file of",
        'if not path or "*" in path or "?" in path:',
        "if not path:",
    ),
    Mutant(
        "hive.py",
        "discovery stops reading the owner's sharing flag, so a held entity is searchable again",
        "if not sharing.searchable(entity_sharing, None):",
        "if False:",
    ),
    Mutant(
        "hive.py",
        "a closed channel's value is signed into the public card after all",
        'k: v for k, v in (card.get("contact") or {}).items() if flags.get(k) not in (sharing.PUSH, sharing.NEVER)',
        'k: v for k, v in (card.get("contact") or {}).items()',
    ),
    Mutant(
        "hive.py",
        "the served contact block stops redacting, so an older card hands out what it closed",
        "if sharing.searchable(default, flags.get(str(channel)))",
        "if True",
    ),
    Mutant(
        "hive.py",
        "a person card defaults to public, so an introduction stops being theirs to grant",
        'fallback = sharing.CONFIRM if card.get("kind") in CONSENT_FIRST_KINDS else sharing.PUBLIC',
        "fallback = sharing.PUBLIC",
    ),
    Mutant(
        "federation.py",
        "a held entity relayed by a peer is served here, so the owner's flag stops at the hub boundary",
        "elif not sharing.searchable(hive.sharing_default(card), None):",
        "elif False:",
    ),
    Mutant(
        "federation.py",
        "a blocked peer is asked who it is, so the query follows and it learns what we searched for",
        "if known and known in blocked:",
        "if known and False:",
    ),
    Mutant(
        "federation.py",
        "a blocked hub is named as a place to go, so the hint leaks what blocking it closed",
        'if entity_id in ((record or {}).get("owner_keys") or {}) and not refused(entity_id, [hub_id]):',
        'if entity_id in ((record or {}).get("owner_keys") or {}):',
    ),
    Mutant(
        "federation.py",
        "the block is not rechecked on the name a peer gave, so a blocked hub is forwarded the query",
        'elif profile["hub_id"] in blocked:',
        "elif False:",
    ),
    Mutant(
        "federation.py",
        "nothing that arrives is screened, so a blocked entity comes back through an allowed peer",
        "        return not reason",
        "        return True",
    ),
    Mutant(
        "federation.py",
        "the timer polls a blocked peer anyway, so an outbound call to it every PEER_ASK_SECONDS",
        "urls = [url for url in peer_store.urls() if known_hub_id(url) not in blocked]",
        "urls = peer_store.urls()",
    ),
    Mutant(
        "blocklist.py",
        "a blocked entity passes the screen, so an administrative block stops biting on arrivals",
        'if (entity_id or "").strip() in entities:',
        "if False:",
    ),
    Mutant(
        "blocklist.py",
        "a blocked carrier chain passes, so blocking a hub that relays for a blocked one does nothing",
        'return f"carried through {carrier}, which is blocked on this hub" if carrier else None',
        "return None",
    ),
    Mutant(
        "main.py",
        "a query a blocked hub relayed here is answered, so the block holds in one direction only",
        "if carrier := blocklist.filter_path([str(h) for h in (seen or [])]):",
        "if False:",
    ),
    Mutant(
        "admin.py",
        "the hub's own row loses its address again, so an agent cannot pass on a working one",
        'url = (config.HIVE_PUBLIC_URL or base_url or "").rstrip("/")',
        'url = ""',
    ),
    Mutant(
        "admin.py",
        "the apply link goes back to being relative, which is useless to an agent quoting it",
        'f"{url}/api/hub/register" if url else "/api/hub/register"',
        '"/api/hub/register"',
    ),
    Mutant(
        "admin.py",
        "a configured public URL is ignored, so a hub behind a proxy publishes the wrong address",
        'url = (config.HIVE_PUBLIC_URL or base_url or "").rstrip("/")',
        'url = (base_url or "").rstrip("/")',
    ),
    Mutant(
        "mcp_server.py",
        "the scheme is asserted rather than read, so an https hub publishes an http address",
        'scheme = headers.get("x-forwarded-proto", "").split(",")[0].strip() or "http"',
        'scheme = "http"',
    ),
    Mutant(
        "sharing.py",
        "the looser of the two flags wins, so opening a default unseals closed items",
        "return max(flags, key=strictness)",
        "return min(flags, key=strictness)",
    ),
    Mutant(
        "sharing.py",
        "a push item becomes searchable, so what the owner meant to send is handed out",
        "SEARCHABLE = frozenset({PUBLIC, CONFIRM})",
        "SEARCHABLE = frozenset({PUBLIC, CONFIRM, PUSH})",
    ),
    Mutant(
        "sharing.py",
        "an unflagged item defaults to public instead of needing a yes",
        "DEFAULT = CONFIRM",
        "DEFAULT = PUBLIC",
    ),
    Mutant(
        "registration.py",
        "a bad signature is admitted, so anyone can register as anyone",
        'return False, "the signature does not match the key offered"',
        'return True, "signature was not checked"',
    ),
    Mutant(
        "registration.py",
        "an application that brings a key need not sign, so the key is just a claim",
        'return False, "an application that brings a public key must be signed with the private half"',
        'return True, "unsigned"',
    ),
    Mutant(
        "registration.py",
        "an application can be withdrawn with no proof at all, by anybody who knows its id",
        "        raise RegistrationError(_no_proof(row))",
        "        proof = BY_CAPABILITY",
    ),
    Mutant(
        "registration.py",
        "a wrong withdrawal capability is accepted, so the hash check is decorative",
        "        if not guard.secret_matches(fingerprint(key), stored):",
        "        if False:",
    ),
    Mutant(
        "registration.py",
        "a withdrawal signature is accepted without being checked against the registered key",
        '        if not hive.verify(withdrawal_statement(row["id"], nonce, expires), signature, registered):',
        "        if False:",
    ),
    Mutant(
        "registration.py",
        "an expired withdrawal signature still works, so a captured one works for ever",
        "        if _expired(expires):",
        "        if False:",
    ),
    Mutant(
        "registration.py",
        "an unreadable expiry is read as a live window instead of a closed one",
        "        return True\n    if when.tzinfo is not None:",
        "        return False\n    if when.tzinfo is not None:",
    ),
    Mutant(
        "registration.py",
        "the withdrawal transition stops being conditional, so admission and withdrawal both win",
        '" WHERE id = ? AND state = ?",\n            [WITHDRAWN, _now(), proof, reason, app_id, PENDING],',
        '" WHERE id = ?",\n            [WITHDRAWN, _now(), proof, reason, app_id],',
    ),
    Mutant(
        "registration.py",
        "an operator withdrawal is credited to the applicant, so the row claims a consent nobody gave",
        '        if proof == BY_OPERATOR\n        else f"withdrawn by the applicant',
        '        if False\n        else f"withdrawn by the applicant',
    ),
    Mutant(
        "registration.py",
        "the capability is minted for an application that brought its own key, weakening both",
        '    secret = secrets.token_urlsafe(WITHDRAW_SECRET_BYTES) if state == PENDING and not public_key else ""',
        "    secret = secrets.token_urlsafe(WITHDRAW_SECRET_BYTES)",
    ),
    Mutant(
        "registration.py",
        "a blocked entity can register its way back in",
        'return False, f"{entity_id} is blocked on this hub"',
        'return True, "not blocked"',
    ),
    Mutant(
        "registration.py",
        "an id already in the index can be taken over by a new applicant",
        "if hive.get_record(entity_id) is not None:",
        "if False:",
    ),
    Mutant(
        "registration.py",
        "a vetted hub admits without a person ever looking",
        "elif config.ADMISSION_POLICY == VETTED:",
        "elif False:",
    ),
    Mutant(
        "registration.py",
        "an invite-only hub lets anyone in",
        "if offered and offered in config.INVITE_TOKENS:",
        "if True:",
    ),
    Mutant(
        "registration.py",
        "a failed check still publishes the entity",
        "if state == ADMITTED:",
        "if state != WITHDRAWN:",
    ),
    Mutant(
        "limits.py",
        "the description ceiling is removed, so one entry can carry a megabyte of prose",
        '"description": MAX_DESCRIPTION,',
        '"description": 10_000_000,',
    ),
    Mutant(
        "limits.py",
        "the whole-card ceiling goes, so every field legal still adds up to an unbounded document",
        "if size > cap:",
        "if False:",
    ),
    Mutant(
        "limits.py",
        "zero-width characters survive normalising, so an invisible pad changes every digest",
        "kept = [ch for ch in text if ch.isspace() or unicodedata.category(ch) not in _INVISIBLE]",
        "kept = list(text)",
    ),
    Mutant(
        "limits.py",
        "the request body stops being counted, so a chunked 20 MB application is parsed after all",
        "if seen > self.max_bytes:",
        "if False:",
    ),
    Mutant(
        "limits.py",
        "Content-Length stops being read, so a body that declares itself too big is received anyway",
        'if name.lower() == b"content-length":',
        "if False:",
    ),
    Mutant(
        "hive.py",
        "the second door goes: an entity joins politely and grows unbounded on its next version",
        "card = limits.vet(card)",
        "card = limits.normalise(card)",
    ),
    Mutant(
        "registration.py",
        "the size check stops refusing, so an application of any size is signed for and stored",
        'return (False, reason) if reason else (True, "within the sizes this hub publishes")',
        'return True, "not checked"',
    ),
    Mutant(
        "reputation.py",
        "distance stops discounting, so a far result outranks an identical near one",
        "HOP_DECAY = 0.85",
        "HOP_DECAY = 1.0",
    ),
    Mutant(
        "reputation.py",
        "an unknown peer is trusted like a vetted one",
        "NEW_PEER_TRUST = 0.35",
        "NEW_PEER_TRUST = 1.0",
    ),
    Mutant(
        "reputation.py",
        "selling placement stops costing a peer anything",
        "PAID_PLACEMENT_PENALTY",
        "0.0 * PAID_PLACEMENT_PENALTY",
    ),
    Mutant(
        "reputation.py",
        "a relayed card that failed its signature check is no longer held against the carrier",
        'def record_invalid(hub_id: str, cards: int = 1, card_id: str = "") -> None:',
        'def record_invalid(hub_id: str, cards: int = 1, card_id: str = "") -> None:\n    return',
    ),
    Mutant(
        "mcp_server.py",
        "publish works without a token: any agent that can reach /mcp/ can rewrite any claimed card",
        'return {"error": refused} if refused else None',
        "return None",
    ),
    Mutant(
        "hive.py",
        "a published card keeps the old version's signature, so every change breaks verify_pinned",
        "signature = base64.b64encode(key.sign(canonical(card))).decode()",
        'signature = (existing or {}).get("signature", "")',
    ),
    Mutant(
        "owner.py",
        "a hub with no owner token set accepts an edit from anybody instead of refusing everybody",
        "    if not config.OWNER_EDIT_TOKEN:\n        return (",
        "    if False:\n        return (",
    ),
    Mutant(
        "owner.py",
        "a guest's name is handed to anyone who asks for the owner's view without the token",
        "    if not guard.secret_ok(token, config.OWNER_EDIT_TOKEN):",
        "    if False:",
    ),
    Mutant(
        "owner.py",
        "an owner edit is answered as published without ever being signed or stored",
        "    card = hive.publish(_strip(proposed))",
        "    card = _strip(proposed)",
    ),
    Mutant(
        "hub.py",
        "a local introduction reads the signed body again, so its published claim is NULL for ever",
        "held = _verified_remote(entity_id, card, target_hub) if remote else hive.get_card(entity_id)",
        'held = _verified_remote(entity_id, card, target_hub) if remote else record["data"]',
    ),
    Mutant(
        "hub.py",
        "a local introduction is attributed to nobody, so calibration never counts it",
        "    if not remote and not target_hub:",
        "    if False:",
    ),
    Mutant(
        "hub.py",
        "a forward tells the peer the requester is one of *its* members, which is the bug it exists to fix",
        '        "requester_hub": config.HIVE_HUB_ID,',
        '        "requester_hub": "",',
    ),
    Mutant(
        "hub.py",
        "a peer URL is taken from the request instead of this hub's own peer list",
        '    return next((row["url"] for row in federation.peer_rows() if row["hub"] == hub_id and row["url"]), "")',
        "    return hub_id",
    ),
    Mutant(
        "hub.py",
        "a forward that failed is reported as sent, so a hub believes a peer was told",
        '        return {"sent": False, "to": target_hub, "url": url, "why": f"{type(err).__name__}: {err}"}',
        '        return {"sent": True, "to": target_hub, "url": url, "why": f"{type(err).__name__}: {err}"}',
    ),
    Mutant(
        "hub.py",
        "a forward is forwarded again, so two hubs can bounce one introduction between them",
        "    if remote and forward and FORWARD_INTRODUCTIONS:",
        "    if remote and FORWARD_INTRODUCTIONS:",
    ),
    Mutant(
        "federation.py",
        "the carrier hint claims every peer carries every entity, so a refusal points anywhere",
        '        if entity_id in ((record or {}).get("owner_keys") or {}) and not refused(entity_id, [hub_id]):',
        "        if True:",
    ),
    Mutant(
        "hub.py",
        "a visitor who said nothing is labelled a member of the hub they are visiting",
        '    return "", connections.BY_NOBODY',
        "    return config.HIVE_HUB_ID, connections.BY_MEMBER",
    ),
    Mutant(
        "hub.py",
        "a caller buys membership of this hub by claiming it, so the ledger cannot be read at all",
        "        return claimed, connections.BY_CLAIM",
        "        return claimed, connections.BY_MEMBER",
    ),
    Mutant(
        "hub.py",
        "a claim overrides what the hub can see for itself, so a member can disown their own hub",
        "    if name and hive.get_record(name) is not None:",
        "    if False:",
    ),
    Mutant(
        "connections.py",
        "an invented proof value is written to the ledger as itself",
        "                requester_proof if requester_proof in REQUESTER_PROOFS else BY_NOBODY,",
        "                requester_proof,",
    ),
]


# --- Random mutants ------------------------------------------------------------------
# Blunter: flip an operator or nudge a constant at a random site. These find the gaps
# nobody thought to aim at.
SWAPS = [
    (r"(?<![<>=!])<=(?!=)", "<"),
    (r"(?<![<>=!])>=(?!=)", ">"),
    (r"(?<![<>=!])<(?!=)", ">"),
    (r"(?<![<>=!])>(?!=)", "<"),
    (r"(?<![<>=!])==(?!=)", "!="),
    (r"!=", "=="),
    (r"\band\b", "or"),
    (r"\bor\b", "and"),
    (r"\bnot in\b", "in"),
    (r"\+ 1\b", "+ 2"),
    (r"- 1\b", "- 0"),
    (r"\bTrue\b", "False"),
]
TARGETS = [
    "federation.py",
    "blocklist.py",
    "folders.py",
    "folder_keys.py",
    "reputation.py",
    "calibration.py",
    "connections.py",
    "sharing.py",
    "registration.py",
    "semantic.py",
    "removals.py",
    "audit.py",
    "peers.py",
    "limits.py",
    "guard.py",
]


# --- Worker trees --------------------------------------------------------------------
# A mutant is applied by editing the source in place and putting it back afterwards, so two
# mutants cannot share a tree: the second would read the first's edit, and the pair would be
# reported as one. Every worker therefore gets its own copy of the tree.
#
# A copy rather than a `git worktree`: a worktree checks out a *commit*, so it would quietly
# mutate and test the last commit instead of the working tree the developer is running this on —
# a mutation report about code nobody has, which is the one kind of wrong answer this tool must
# not give. A copy also needs no .git at all (Docker layer, tarball, release archive), and if this
# process is killed there is nothing registered in someone else's repository to prune.

#: Never copied into a worker tree: huge, machine-specific, or stale the moment it is copied.
COPY_IGNORE = shutil.ignore_patterns(
    ".git",
    "__pycache__",
    "*.pyc",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "*.duckdb",
    "*.duckdb.wal",
)


def copy_source() -> tuple[Path, Path]:
    """What a worker copy has to contain, and where code/backend sits inside it.

    The suite is not self-contained inside code/backend: tests/test_folders.py reads
    testdata/vaults/ and tests/test_limits.py reads documentation/cards/README.md, both from the
    repo root. A copy of code/backend alone goes red on those two before a single mutant is
    applied, and the harness reports that as "the suite is already red" — true, but about the copy,
    not the code. So the copy is rooted at the repo when the repo is there, and at code/backend
    otherwise (a Docker layer that ships the backend alone).
    """
    repo = ROOT.parents[1]
    if (repo / "testdata").is_dir():
        return repo, ROOT.relative_to(repo)
    return ROOT, Path(".")


#: Where this run's worker copies live. Outside the checkout on purpose. A copy spends seconds at
#: a time holding a mutant, and a copy left behind by a SIGKILL must not sit anywhere a later run,
#: an import or a linter could mistake for source: live_mutants() reads only the real tree, and
#: nothing under a mkdtemp is on anybody's path.
_RUN_DIR: Path | None = None
_RUN_LOCK = threading.Lock()


def run_dir() -> Path:
    """This run's private directory for worker copies, created on first use."""
    global _RUN_DIR
    with _RUN_LOCK:
        if _RUN_DIR is None:
            _RUN_DIR = Path(tempfile.mkdtemp(prefix="mutate-trees-")).resolve()
            atexit.register(drop_run_dir)
        return _RUN_DIR


def drop_run_dir() -> None:
    """Delete this run's worker copies. Safe to call twice, and from a signal handler."""
    global _RUN_DIR
    with _RUN_LOCK:
        doomed, _RUN_DIR = _RUN_DIR, None
    if doomed is not None:
        shutil.rmtree(doomed, ignore_errors=True)


def make_trees(workers: int) -> list[Path]:
    """One independent copy of the tree per worker. Returns each copy's code/backend."""
    source, backend = copy_source()
    # Its own sub-directory per call, so a second call cannot land on the first call's w0.
    where = Path(tempfile.mkdtemp(prefix="set-", dir=run_dir()))
    trees = []
    for i in range(workers):
        dest = where / f"w{i}"
        shutil.copytree(source, dest, ignore=COPY_IGNORE, symlinks=True)
        trees.append((dest / backend).resolve())
    return trees


#: Every file holding a mutant right now, and the bytes to put back. A module global because a
#: signal handler has nowhere else to look; a dict rather than a single entry because N workers
#: each hold one. Leaving a mutant behind is the worst outcome this tool has: in the real tree it
#: breaks the source in a way that reads as a genuine failing test, and in a worker copy it makes
#: the next mutant in that copy a compound of two, which is just as silently wrong.
_IN_FLIGHT: dict[Path, str] = {}
_IN_FLIGHT_LOCK = threading.Lock()


def _hold(path: Path, original: str) -> None:
    """Record that `path` is mutated right now, and what to put back."""
    with _IN_FLIGHT_LOCK:
        _IN_FLIGHT[path] = original


def _restore(path: Path) -> None:
    """Put back one file, if it is still held. Safe to call twice."""
    with _IN_FLIGHT_LOCK:
        original = _IN_FLIGHT.pop(path, None)
    if original is not None:
        path.write_text(original, encoding="utf-8")


def _restore_in_flight() -> None:
    """Put back every file that is mutated right now. Safe to call twice."""
    with _IN_FLIGHT_LOCK:
        held = list(_IN_FLIGHT.items())
        _IN_FLIGHT.clear()
    for path, original in held:
        path.write_text(original, encoding="utf-8")


#: The pytest children running right now. A signal ends them instead of orphaning N of them for
#: another twenty seconds each, still writing into pipes nobody is reading.
_CHILDREN: set[subprocess.Popen] = set()


def _on_signal(signum, _frame):
    """Restore, end the children, delete the copies, then die with the conventional code.

    `finally` does not run on SIGTERM. The handler is reset to the default first, so a second
    signal from an impatient Ctrl-C kills us outright instead of re-entering this while we hold a
    lock. `os._exit` because sys.exit would leave the thread pool's own atexit hook waiting for a
    worker to finish its twenty-second pytest run — nothing is left mutated by then, so there is
    nothing to wait for.
    """
    signal.signal(signum, signal.SIG_DFL)
    _restore_in_flight()
    for child in list(_CHILDREN):
        child.kill()
    drop_run_dir()
    print(f"\n  interrupted ({signal.Signals(signum).name}); nothing was left mutated")
    sys.stdout.flush()
    os._exit(128 + signum)


def live_mutants() -> list[Mutant]:
    """Curated mutants that are sitting in the source right now.

    A run restores every file in a `finally`, which covers an exception and a Ctrl-C. It does not
    survive SIGKILL, and a killed run leaves the source broken in a way that looks like a real
    failing test. This has happened. So a run refuses to start until the tree is clean, and says
    exactly which line to put back.
    """
    found = []
    for mutant in CURATED:
        if not mutant.path.exists():
            continue
        src = mutant.path.read_text(encoding="utf-8")
        if mutant.find not in src and mutant.replace in src:
            found.append(mutant)
    return found


#: One suite run is ~20s, so two minutes is six times over. It is a hang detector, not a budget:
#: raising it to make a red run go green would hide exactly what the timeout is here to find.
SUITE_TIMEOUT = 120


def run_suite(tree: Path, timeout: int = SUITE_TIMEOUT, keep: list[str] | None = None) -> bool:
    """True when the suite is green in `tree`. A timeout counts as caught: the mutant hung it.

    `-x` stays: a mutant killed by the second test should not pay for the rest of the suite.

    `keep` collects pytest's own output for the one caller that needs it — the pre-flight, which
    reports "the suite is already red" and must be able to say which test. Without that, a red
    pre-flight in CI is a dead end: the harness swallows the only copy of the failure.
    """
    child = subprocess.Popen(
        [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider", *SUITE],
        cwd=tree,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _CHILDREN.add(child)
    try:
        try:
            out, err = child.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()
            if keep is not None:
                keep.append(f"pytest did not finish within {timeout}s")
            return False
    finally:
        _CHILDREN.discard(child)
    if keep is not None:
        keep.append((out or "") + (err or ""))
    return child.returncode == 0


def apply(path: Path, find: str, replace: str, count: int, regex: bool = False) -> tuple[str, bool]:
    """Swap find for replace. Returns the original text and whether anything changed."""
    original = path.read_text(encoding="utf-8")
    if regex:
        mutated, n = re.subn(find, replace, original, count=count)
    else:
        n = original.count(find)
        mutated = original.replace(find, replace, count) if n else original
        n = min(n, count)
    if n:
        path.write_text(mutated, encoding="utf-8")
    return original, bool(n)


def _only_in_a_copy(path: Path) -> None:
    """Refuse to mutate anything outside this run's worker copies.

    Nothing should ever reach here with a path in the real checkout, so this is a last line rather
    than a branch. Writing a mutant into the tree someone is working in is the one failure this
    tool must not have, and "should never happen" is not a guarantee.
    """
    where = _RUN_DIR
    if where is None or where not in path.resolve().parents:
        raise RuntimeError(f"refusing to mutate {path}: outside this run's worker copies")


@dataclass
class Result:
    """What one mutant did, and the lines to print when that mutant's turn comes round."""

    mutant: Mutant
    #: True when the suite stayed green, i.e. the mutant lived. None when it was not applied.
    survived: bool | None
    lines: list[str] = field(default_factory=list)


def check(mutant: Mutant, tree: Path, timeout: int = SUITE_TIMEOUT) -> Result:
    """Apply one mutant inside one worker copy, run the suite there, always put the file back.

    Returns its lines instead of printing them. With N workers the output would otherwise
    interleave mid-mutant and be unreadable; the caller prints each mutant's block in order.
    """
    path = mutant.path_in(tree)
    if not path.exists():
        return Result(mutant, None, [f"  SKIP  {mutant.file}: not present"])
    _only_in_a_copy(path)
    original, changed = apply(path, mutant.find, mutant.replace, mutant.count, mutant.regex)
    if not changed:
        return Result(mutant, None, [f"  SKIP  {mutant.title}: pattern not found ({mutant.find!r})"])
    _hold(path, original)
    try:
        green = run_suite(tree, timeout=timeout)
    finally:
        _restore(path)
    if green:  # green means the suite did not notice: the mutant lived
        return Result(
            mutant,
            True,
            [
                f"  \033[31mSURVIVED\033[0m  {mutant.title}",
                f"            {mutant.why}",
                f"            {path.name}: {mutant.find!r} -> {mutant.replace!r}",
            ],
        )
    return Result(mutant, False, [f"  \033[32mkilled\033[0m    {mutant.title}"])


def run_mutants(mutants: list[Mutant], trees: list[Path], timeout: int = SUITE_TIMEOUT) -> list[Result]:
    """Check every mutant, one per free worker copy, and print the report in a stable order.

    The results come back in the order the mutants were listed, not the order the workers happened
    to finish, and that is also the order they print in, so a parallel run reads exactly like a
    sequential one. A worker is a thread because all it does is wait on a pytest process.
    """
    free: queue.Queue[Path] = queue.Queue()
    for tree in trees:
        free.put(tree)

    def one(mutant: Mutant) -> Result:
        tree = free.get()
        try:
            return check(mutant, tree, timeout=timeout)
        finally:
            free.put(tree)

    results: list[Result] = []
    with ThreadPoolExecutor(max_workers=len(trees), thread_name_prefix="mutant") as pool:
        for future in [pool.submit(one, m) for m in mutants]:
            result = future.result()
            print("\n".join(result.lines), flush=True)
            results.append(result)
    return results


def random_mutants(n: int, seed: int, targets: list[str] | None = None) -> list[Mutant]:
    """Pick n random operator or constant flips at real sites in the target modules."""
    rng = random.Random(seed)
    sites = []
    for name in TARGETS if targets is None else targets:
        path = APP / name
        if not path.exists():
            continue
        in_doc = False
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            # Prose is not code. Mutating an "and" inside a docstring always survives and says
            # nothing about the tests, so track the fences and skip the whole block.
            fences = line.count('"""') + line.count("'''")
            if in_doc:
                in_doc = fences % 2 == 0
                continue
            if fences % 2:
                in_doc = True
                continue
            if not stripped or stripped.startswith("#") or fences:
                continue
            for pattern, repl in SWAPS:
                if re.search(pattern, line):
                    sites.append((name, lineno, line, pattern, repl))
    rng.shuffle(sites)
    out = []
    for name, lineno, line, pattern, repl in sites[:n]:
        mutated_line = re.sub(pattern, repl, line, count=1)
        out.append(
            Mutant(
                name,
                f"{line.strip()[:70]}  ->  {mutated_line.strip()[:70]}",
                re.escape(line),
                mutated_line.replace("\\", "\\\\"),
                label=f"{name}:{lineno}",
                regex=True,
            )
        )
    return out


# --- Choosing which mutants to run ---------------------------------------------------
# A pull request that touches one module does not need every other mutant re-proved: they
# were proved on main and nothing they touch has changed. CI passes the modules the diff names and
# runs the whole set on every push to main, so main is never permanently unchecked.
#
# This filters *mutants*, never tests. Each mutant that does run still runs the whole SUITE, so no
# test that used to be able to kill a mutant stops being asked.


def module_name(token: str) -> str:
    """The app-relative module name that a flag or a diff line is naming.

    Accepts every form the same file gets written in: `semantic.py`, `app/semantic.py`,
    `code/backend/app/semantic.py`, `./code/backend/app/domains/hr.py`. Anything up to and
    including the last `app/` component is a path to the backend, not part of the name.
    """
    parts = [p for p in token.strip().replace("\\", "/").split("/") if p not in ("", ".")]
    if "app" in parts:
        parts = parts[len(parts) - parts[::-1].index("app") :]
    return "/".join(parts)


def select_modules(mutants: list[Mutant], tokens: list[str]) -> tuple[list[Mutant], list[str]]:
    """The mutants living in the named modules, and the names that have none.

    Matching is deliberately generous — app-relative name first, then bare filename — because the
    failure this flag must not have is selecting nothing while still looking like a pass. A name
    that matches no mutant is handed back rather than dropped, so the caller says so out loud.
    """
    exact: dict[str, list[Mutant]] = {}
    by_base: dict[str, list[Mutant]] = {}
    for mutant in mutants:
        exact.setdefault(mutant.file, []).append(mutant)
        by_base.setdefault(Path(mutant.file).name, []).append(mutant)
    wanted: set[str] = set()
    without: list[str] = []
    for token in tokens:
        name = module_name(token)
        if not name:
            continue
        if name in exact:
            wanted.add(name)
        elif Path(name).name in by_base:
            wanted.update(m.file for m in by_base[Path(name).name])
        else:
            without.append(token)
    return [m for m in mutants if m.file in wanted], without


def default_workers() -> int:
    """Four, or fewer on a smaller machine. Each worker is one whole pytest process."""
    return max(1, min(4, os.cpu_count() or 1))


def parser() -> argparse.ArgumentParser:
    """The command line. Split out so the tests can pin what the defaults mean."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--random", type=int, default=0, metavar="N", help="also run N random flips")
    ap.add_argument("--seed", type=int, default=None, help="seed for --random (default: time-based)")
    ap.add_argument("--all", action="store_true", help="curated plus 12 random")
    ap.add_argument(
        "--workers",
        type=int,
        default=default_workers(),
        metavar="N",
        help="how many mutants to check at once, each in its own copy of the tree (default: %(default)s)",
    )
    # Default None, not "": the two are different answers and CI asks both. No flag at all means
    # the full set. The flag with an empty value means "the diff named no module with mutants",
    # which must check nothing — if that read as "everything" the fast path would silently become
    # the slow one, and if the inverse read as "nothing" a push to main would check nothing at all.
    ap.add_argument(
        "--modules",
        default=None,
        metavar="LIST",
        help="only mutants in these modules, comma separated (e.g. app/semantic.py,app/hive.py)",
    )
    return ap


def main() -> int:
    """Run the mutants and report the survivors."""
    args = parser().parse_args()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _on_signal)
    seed = args.seed if args.seed is not None else int(time.time())
    n_random = 12 if args.all else args.random
    workers = max(1, args.workers)
    want_curated = n_random == 0 or args.all or args.random == 0

    # Which mutants, and said out loud. A green check that silently ran nothing is worse than a
    # slow one, so the mode and the count go in the log before any work starts.
    filtered = args.modules is not None
    tokens = [t.strip() for t in (args.modules or "").split(",") if t.strip()]
    curated, no_mutants = select_modules(CURATED, tokens) if filtered else (CURATED, [])
    targets = sorted({m.file for m in curated}) if filtered else TARGETS
    randoms = random_mutants(n_random, seed, targets) if n_random else []
    if filtered:
        print(f"Mode: only the modules named — {', '.join(tokens) if tokens else '(none)'}")
        if no_mutants:
            print(f"  no mutants aimed at: {', '.join(no_mutants)}")
        print(f"Mutants: {len(curated) if want_curated else 0} curated of {len(CURATED)}, {len(randoms)} random.")
        if not (want_curated and curated) and not randoms:
            print("\nNothing to check: none of those modules has a mutant. Passing.")
            return 0
    else:
        print(f"Mode: the full set — {len(CURATED)} curated mutants over every module.")
        print(f"Mutants: {len(curated) if want_curated else 0} curated, {len(randoms)} random.")
    print(f"Workers: {workers}\n")

    stray = live_mutants()
    if stray:
        print("Refusing to run: a previous run left mutants in the source.\n")
        for mutant in stray:
            print(f"  {mutant.file}: {mutant.why}")
            print(f"    put back: {mutant.find!r}")
            print(f"    found:    {mutant.replace!r}\n")
        print("Restore those lines (git checkout the file, if it is tracked) and run again.")
        return len(stray)

    started = time.monotonic()
    trees = make_trees(workers)
    print(f"Copied the tree {workers}x in {time.monotonic() - started:.1f}s; mutants run only in those copies.")

    # In a copy, not the real tree: a faithful copy is the thing everything below depends on, so
    # the pre-flight proves both at once — the suite is green, and the copy is complete enough to
    # run it. A copy that lost a file the suite reads shows up here, once, not as a sea of survivors.
    print("Checking the suite is green before we start...")
    output: list[str] = []
    if not run_suite(trees[0], keep=output):
        print("The suite is already red. Fix that first; mutation results would be meaningless.")
        print("\n".join("    " + line for line in "\n".join(output).strip().splitlines()[-30:]))
        return 1
    print("Green.\n")

    results: list[Result] = []

    if want_curated:
        print(f"Curated mutants ({len(curated)}) — the invariants the design rests on")
        results += run_mutants(curated, trees)
        print()

    if randoms:
        print(f"Random mutants ({len(randoms)}, seed {seed})")
        results += run_mutants(randoms, trees)
        print()

    drop_run_dir()
    # The count is of mutants that were really applied, not of mutants planned. A pattern that has
    # drifted prints SKIP and checks nothing, and "checked 71" over 71 skips is the false all-clear
    # this whole tool exists to avoid.
    ran = [r for r in results if r.survived is not None]
    survivors = [f"{r.mutant.label}  {r.mutant.why}" if r.mutant.label else r.mutant.why for r in ran if r.survived]
    elapsed = time.monotonic() - started
    print(f"Checked {len(ran)} mutant(s) in {int(elapsed // 60)}m {elapsed % 60:04.1f}s with {workers} worker(s).")
    if len(ran) < len(results):
        print(f"  {len(results) - len(ran)} were skipped, so they proved nothing — look at the SKIP lines above.")

    if survivors:
        print(f"\033[31m{len(survivors)} mutant(s) survived\033[0m — the tests did not notice:")
        for s in survivors:
            print(f"  · {s}")
        print("\nEach survivor is a missing assertion, not a reason to loosen anything.")
    else:
        print("\033[32mNo survivors.\033[0m Every change the harness made was caught.")
    if args.random and args.seed is None:
        print(f"\nReproduce this random run with --seed {seed}")
    return len(survivors)


if __name__ == "__main__":
    sys.exit(main())
