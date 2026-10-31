"""Mutation testing for the federated search.

Coverage proves the tests *ran* a line. It does not prove they would notice if that line
were wrong. This makes small, deliberate changes to the source — flips a comparison, drops
the loop guard, keeps the longest path instead of the shortest — and checks the suite turns
red. A mutant the tests still pass is a hole, named and located.

    python tools/mutate.py                  # the curated mutants, the invariants that matter
    python tools/mutate.py --random 12      # 12 random operator and constant flips
    python tools/mutate.py --random 12 --seed 7
    python tools/mutate.py --all            # both

Exit code is the number of survivors, so CI can gate on it.
"""

from __future__ import annotations

import argparse
import random
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
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
    "tests/test_hub_trust.py",
    "tests/test_hub_api.py",
    "tests/test_folders.py",
    "tests/test_registration.py",
    "tests/test_semantic.py",
    "tests/test_semantic_search.py",
    "tests/test_limits.py",
]


@dataclass
class Mutant:
    """One deliberate change: what it breaks, and where."""

    file: str
    why: str
    find: str
    replace: str
    count: int = 1

    @property
    def path(self) -> Path:
        """The module this mutant edits."""
        return APP / self.file


# --- The curated mutants -------------------------------------------------------------
# Each one is a bug a tired person could plausibly write at 3am, aimed at an invariant the
# design depends on. If the suite does not catch these, the suite is decorative.
CURATED: list[Mutant] = [
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
        "return peers[:PEERS_PER_HOP], skipped",
        "return peers, skipped",
    ),
    Mutant(
        "federation.py",
        "a peer's own claim about itself becomes its rating, so trust can be self-declared",
        '"rating": trust,  # our own opinion of this peer, not its word for itself',
        '"rating": 1.0,',
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
        "semantic.py",
        "the similarity floor goes, so every card is a little bit like every query and ranking is noise",
        "SIMILARITY_FLOOR = 0.25",
        "SIMILARITY_FLOOR = 0.0",
    ),
    Mutant(
        "semantic.py",
        "the concept table stops being consulted, so semantic search is substring search again",
        'bag += [(f"c:{concept}", CONCEPT_WEIGHT) for concept in concepts]',
        "bag += []",
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
    "folders.py",
    "reputation.py",
    "calibration.py",
    "connections.py",
    "sharing.py",
    "registration.py",
    "semantic.py",
    "limits.py",
]


#: The file currently holding a mutant, and the bytes to put back. A module global because a
#: signal handler has nowhere else to look, and leaving a mutant behind is the worst outcome
#: this tool has: the source breaks in a way that reads as a genuine failing test.
_IN_FLIGHT: tuple[Path, str] | None = None


def _restore_in_flight() -> None:
    """Put back whatever is mutated right now. Safe to call twice."""
    global _IN_FLIGHT
    if _IN_FLIGHT is not None:
        path, original = _IN_FLIGHT
        _IN_FLIGHT = None
        path.write_text(original, encoding="utf-8")


def _on_signal(signum, _frame):
    """Restore, then die with the conventional code. `finally` does not run on SIGTERM."""
    _restore_in_flight()
    print(f"\n  interrupted ({signal.Signals(signum).name}); the source has been put back")
    sys.exit(128 + signum)


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


def run_suite(timeout: int = 120) -> bool:
    """True when the suite is green. A timeout counts as caught: the mutant hung it."""
    try:
        done = subprocess.run(
            [sys.executable, "-m", "pytest", "-x", "-q", "--no-header", "-p", "no:cacheprovider", *SUITE],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False
    return done.returncode == 0


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


def check(label: str, why: str, path: Path, find: str, replace: str, count: int, regex: bool = False):
    """Apply one mutant, run the suite, always put the file back."""
    global _IN_FLIGHT
    original, changed = apply(path, find, replace, count, regex)
    if not changed:
        print(f"  SKIP  {label}: pattern not found ({find!r})")
        return None
    _IN_FLIGHT = (path, original)
    try:
        green = run_suite()
    finally:
        _restore_in_flight()
    if green:
        print(f"  \033[31mSURVIVED\033[0m  {label}")
        print(f"            {why}")
        print(f"            {path.name}: {find!r} -> {replace!r}")
    else:
        print(f"  \033[32mkilled\033[0m    {label}")
    return green  # green means the suite did not notice: the mutant lived


def random_mutants(n: int, seed: int) -> list[tuple[str, str, Path, str, str]]:
    """Pick n random operator or constant flips at real sites in the target modules."""
    rng = random.Random(seed)
    sites = []
    for name in TARGETS:
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
            (
                f"{name}:{lineno}",
                f"{line.strip()[:70]}  ->  {mutated_line.strip()[:70]}",
                APP / name,
                re.escape(line),
                mutated_line.replace("\\", "\\\\"),
            )
        )
    return out


def main() -> int:
    """Run the mutants and report the survivors."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--random", type=int, default=0, metavar="N", help="also run N random flips")
    ap.add_argument("--seed", type=int, default=None, help="seed for --random (default: time-based)")
    ap.add_argument("--all", action="store_true", help="curated plus 12 random")
    args = ap.parse_args()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _on_signal)
    seed = args.seed if args.seed is not None else int(time.time())
    n_random = 12 if args.all else args.random

    stray = live_mutants()
    if stray:
        print("Refusing to run: a previous run left mutants in the source.\n")
        for mutant in stray:
            print(f"  {mutant.file}: {mutant.why}")
            print(f"    put back: {mutant.find!r}")
            print(f"    found:    {mutant.replace!r}\n")
        print("Restore those lines (git checkout the file, if it is tracked) and run again.")
        return len(stray)

    print("Checking the suite is green before we start...")
    if not run_suite():
        print("The suite is already red. Fix that first; mutation results would be meaningless.")
        return 1
    print("Green.\n")

    survivors = []

    if n_random == 0 or args.all or args.random == 0:
        print(f"Curated mutants ({len(CURATED)}) — the invariants the design rests on")
        for m in CURATED:
            if not m.path.exists():
                print(f"  SKIP  {m.file}: not present")
                continue
            out = check(m.why[:46], m.why, m.path, m.find, m.replace, m.count)
            if out:
                survivors.append(m.why)
        print()

    if n_random:
        print(f"Random mutants ({n_random}, seed {seed})")
        for label, why, path, find, repl in random_mutants(n_random, seed):
            out = check(label, why, path, find, repl, 1, regex=True)
            if out:
                survivors.append(f"{label}  {why}")
        print()

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
