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
    "tests/test_reputation.py",
    "tests/test_hive.py",
    "tests/test_hub_trust.py",
    "tests/test_hub_api.py",
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
        'factor = max(0.0, 1.0 - max(0.0, float(s["error"])) / TRUST_FLOOR_DELTA)',
        "factor = 1.0",
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
TARGETS = ["federation.py", "reputation.py", "calibration.py", "connections.py", "sharing.py"]


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
    original, changed = apply(path, find, replace, count, regex)
    if not changed:
        print(f"  SKIP  {label}: pattern not found ({find!r})")
        return None
    try:
        green = run_suite()
    finally:
        path.write_text(original, encoding="utf-8")
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
    seed = args.seed if args.seed is not None else int(time.time())
    n_random = 12 if args.all else args.random

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
