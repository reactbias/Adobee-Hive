"""Does discovery actually answer the question? Precision at 1 and at 3, measured rather than asserted.

Semantic search is easy to believe in and hard to be sure about: a synonym table that looks clever in a
docstring can quietly make every card similar to every query. So this builds a hub out of the vault folders in
`testdata/vaults/`, runs a list of query-to-expected pairs through `hive.discover()` twice — once with the
semantic component off, which is the literal substring search we had, and once with it on — and prints both
numbers side by side.

    python tools/eval_search.py                  # the before and after table, and what changed
    python tools/eval_search.py --verbose         # every query, its top three and whether it was right
    python tools/eval_search.py --floor           # the similarity of every pair, expected and not
    python tools/eval_search.py --sweep           # precision at each candidate floor: how the floor was chosen

The pairs come from the answer-key block in `testdata/README.md`, so the people writing the corpus own the
scoring set; the built-in list below is the fallback, and the first lines of the output say which was used and
over how many entities.

Exit code is 1 when the semantic run scores *worse* than the literal one, so this can gate a change that makes
search worse. It is not part of the test suite: it is a measurement, and measurements belong in a report.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
VAULTS = REPO / "testdata" / "vaults"
CORPUS_README = REPO / "testdata" / "README.md"

# A private database for the run, set before the app is imported: a measurement must never touch the demo's.
os.environ.setdefault("DUCKDB_PATH", str(Path(tempfile.mkdtemp(prefix="eval-search-")) / "eval.duckdb"))
os.environ.setdefault("DATABASE_URL", "")
sys.path.insert(0, str(ROOT))

from app import blocklist, db, hive, hive_seed, removals, semantic  # noqa: E402  (after DUCKDB_PATH, on purpose)

#: The fallback scoring set: query, which side of the market it is on, and the entities that should answer it.
#: Read off the vault folders as a person would read them — "who here cuts hair?" — and deliberately mixed:
#: some queries share a word with the card (the control), some share only a meaning (the point).
PAIRS: list[tuple[str, str, tuple[str, ...]]] = [
    # Offers: someone who provides the thing.
    ("haircut", "offers", ("schnittwerk-bern",)),
    ("someone to cut my hair", "offers", ("schnittwerk-bern",)),
    ("Haarschnitt", "offers", ("schnittwerk-bern",)),
    ("colour my hair", "offers", ("schnittwerk-bern",)),
    ("beard trim", "offers", ("schnittwerk-bern",)),
    ("someone to fix my bicycle", "offers", ("velowerk-bern",)),
    ("bike puncture", "offers", ("velowerk-bern",)),
    ("wheel build", "offers", ("velowerk-bern",)),
    ("data visualisation", "offers", ("lena-hofmann",)),
    ("dashboards for our metrics", "offers", ("lena-hofmann",)),
    ("design system audit", "offers", ("lena-hofmann",)),
    ("help with our deployment pipeline", "offers", ("aylin-dervis",)),
    ("kubernetes cost review", "offers", ("aylin-dervis",)),
    ("terraform cleanup", "offers", ("aylin-dervis",)),
    ("someone who knows rust", "offers", ("niko-ferrer",)),
    ("payments integration", "offers", ("niko-ferrer",)),
    ("photographer for our rooms", "offers", ("lichtfeld-foto",)),
    ("pictures for our website", "offers", ("lichtfeld-foto",)),
    ("portraits for the team", "offers", ("lichtfeld-foto",)),
    ("vegan breakfast", "offers", ("cafe-rhein",)),
    ("breakfast without animal products", "offers", ("cafe-rhein",)),
    ("a quiet table for a morning meeting", "offers", ("cafe-rhein",)),
    ("usability review of our control room software", "offers", ("grid-ops",)),
    ("a quiet room with a river view", "offers", ("hotel-krafft", "pension-limmat")),
    ("somewhere to sleep with my dog", "offers", ("hotel-krafft", "pension-limmat")),
    # Needs: someone who wants what you provide.
    ("web developer", "needs", ("schnittwerk-bern", "grid-ops")),
    ("I build booking pages for small businesses", "needs", ("schnittwerk-bern",)),
    ("svelte contractor", "needs", ("grid-ops", "lena-hofmann")),
    ("technical writer", "needs", ("aylin-dervis", "grid-ops")),
    ("I retouch photographs", "needs", ("lichtfeld-foto",)),
    ("frontend work, reads an OpenAPI spec", "needs", ("niko-ferrer",)),
    ("bike mechanic looking for weekend work", "needs", ("velowerk-bern",)),
    ("pastry supplier", "needs", ("cafe-rhein",)),
    ("sign writing", "needs", ("cafe-rhein",)),
    ("interface designer", "needs", ("grid-ops",)),
]

#: Where the corpus keeps its answer key: everything between these two markers in `testdata/README.md`. Only
#: that block is read, because the same file holds a table of cards that must rank *below* a query, and taking
#: a row from there would score the search against the wrong answer on purpose.
KEY_BLOCK = re.compile(r"<!--\s*answer-key\s*-->(?P<body>.*?)<!--\s*/answer-key\s*-->", re.S)

#: `- "a haircut" → schnittwerk-bern, velowerk-bern` or a markdown table row with the same two columns.
#: Liberal on purpose: the corpus is written by someone else, and a scoring set the graders cannot edit is a
#: scoring set that drifts away from the data.
_BULLET = re.compile(r'^[-*]\s*["“]?(?P<query>[^"”|]+?)["”]?\s*(?:→|->|=>)\s*(?P<ids>[a-z0-9 ,\'"-]+)$', re.M)
_ROW = re.compile(r"^\|\s*`?(?P<query>[^`|]+?)`?\s*\|\s*(?P<ids>[a-z0-9 ,`'\"-]+?)\s*\|", re.M)


def _seed_vaults():
    """Load tools/seed_vaults.py, which turns a vault folder into a Card. It is a script, not a module."""
    if "seed_vaults" in sys.modules:
        return sys.modules["seed_vaults"]
    spec = importlib.util.spec_from_file_location("seed_vaults", ROOT / "tools" / "seed_vaults.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_vaults"] = module
    spec.loader.exec_module(module)
    return module


def corpus() -> list[str]:
    """Publish every vault folder into a throwaway hub and return the ids, seeded hotels included.

    The hotels and the example cards stay in, because distractors are the whole difficulty: a search that
    only has to pick between ten entities proves nothing about one that has to pick between sixty.
    """
    db.init()
    hive.init()
    blocklist.init()
    removals.init()
    hive_seed.seed_if_empty()
    seed = _seed_vaults()
    published = []
    for vault in sorted(VAULTS.iterdir()) if VAULTS.exists() else []:
        if not vault.is_dir():
            continue
        card = seed.build_card(vault)
        hive.publish(card)
        published.append(card["id"])
    return published


def pairs(known: set[str]) -> tuple[list[tuple[str, str, tuple[str, ...]]], str]:
    """The scoring set: `testdata/README.md` when it carries one, else the built-in list.

    A pair naming an entity this hub does not hold is dropped with a warning rather than scored, because a
    typo in the corpus would otherwise read as a search failure.
    """
    found: list[tuple[str, str, tuple[str, ...]]] = []
    if CORPUS_README.exists():
        text = CORPUS_README.read_text(encoding="utf-8")
        block = KEY_BLOCK.search(text)
        text = block.group("body") if block else text
        for match in [*_BULLET.finditer(text), *_ROW.finditer(text)]:
            query = match.group("query").strip()
            ids = tuple(i.strip().strip("`'\"") for i in match.group("ids").split(",") if i.strip())
            wanted = tuple(i for i in ids if i in known)
            if not query or not wanted or len(query) < 3:
                continue
            side = "needs" if re.search(r"\bneeds?\b", query.lower()) else "offers"
            found.append((query, side, wanted))
    if found:
        return found, f"{CORPUS_README.relative_to(REPO)} ({len(found)} pairs)"
    missing = {i for _, _, ids in PAIRS for i in ids} - known
    if missing:
        print(f"  note: {len(missing)} expected entities are not on this hub: {', '.join(sorted(missing))}")
    return [(q, s, tuple(i for i in ids if i in known)) for q, s, ids in PAIRS if set(ids) & known], "built in"


def precision_at(ranked: list[str], expected: tuple[str, ...], k: int) -> float:
    """Share of the top k that should be there, normalised by how many could be: 1.0 is a perfect top k."""
    top = ranked[:k]
    return len([card for card in top if card in expected]) / min(k, len(expected)) if top else 0.0


def run(pair_list: list[tuple[str, str, tuple[str, ...]]], semantics: bool) -> dict[str, object]:
    """Run every query and score it. `semantics` off is the literal substring search we started from."""
    at1, at3, evidence, rows = [], [], [], []
    for query, side, expected in pair_list:
        found = hive.discover(query=query, looking_for=side, semantic_search=semantics)
        ranked = [m["id"] for m in found["matches"]]
        scored = {m["id"]: m["score"] for m in found["matches"]}
        at1.append(precision_at(ranked, expected, 1))
        at3.append(precision_at(ranked, expected, 3))
        # Whether the hub had any reason at all to return the right entity, as opposed to returning it by the
        # luck of the tie-break. This is the number substring search was really failing on.
        evidence.append(1.0 if any(scored.get(card, 0) > 0 for card in expected) else 0.0)
        rows.append(
            {
                "query": query,
                "side": side,
                "expected": expected,
                "top": ranked[:3],
                "why": next((m["why"] for m in found["matches"] if m["id"] in expected), []),
                "hit": at1[-1] > 0,
            }
        )
    n = len(pair_list) or 1
    return {
        "p1": sum(at1) / n,
        "p3": sum(at3) / n,
        "evidence": sum(evidence) / n,
        "rows": rows,
    }


def floors(pair_list: list[tuple[str, str, tuple[str, ...]]]) -> None:
    """Print the similarity of every query against every entity, split by whether it should match.

    This is the measurement SIMILARITY_FLOOR is chosen from: the top of the "should not" column and the
    bottom of the "should" column, and a floor in the gap between them.
    """
    engine = semantic.provider()
    should: list[tuple[float, str]] = []
    should_not: list[tuple[float, str]] = []
    for query, side, expected in pair_list:
        for card in hive.list_cards():
            lines = hive._side_texts(card, side)
            hit = max((engine.similarity(engine.encode(query), engine.encode(t)) for t in lines), default=0.0)
            (should if card["id"] in expected else should_not).append((hit, f"{query!r} ~ {card['id']}"))
    should.sort()
    should_not.sort(reverse=True)
    print("\nShould match, weakest first (the floor has to be under these):")
    for score, label in should[:12]:
        print(f"  {score:.3f}  {label}")
    print("\nShould not match, strongest first (the floor has to be over these):")
    for score, label in should_not[:12]:
        print(f"  {score:.3f}  {label}")
    print(f"\n  weakest true pair {should[0][0]:.3f} · strongest false pair {should_not[0][0]:.3f}")
    print(f"  SIMILARITY_FLOOR = {semantic.SIMILARITY_FLOOR}")


def sweep(pair_list: list[tuple[str, str, tuple[str, ...]]]) -> None:
    """Precision at each candidate floor, which is how the floor stops being a matter of taste."""
    print("\n floor   p@1    p@3   (0.00 is no floor at all)")
    in_use = semantic.SIMILARITY_FLOOR
    for floor in sorted({0.0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50, in_use}):
        semantic.SIMILARITY_FLOOR = floor
        out = run(pair_list, semantics=True)
        mark = "  <- in use" if abs(floor - semantic.SIMILARITY_FLOOR) < 1e-9 else ""
        print(f"  {floor:.2f}  {out['p1']:.3f}  {out['p3']:.3f}{mark}")
    semantic.SIMILARITY_FLOOR = in_use


def main() -> int:
    """Measure the search, print the before and after, and fail when the after is worse."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verbose", action="store_true", help="every query, its top three and the reason given")
    ap.add_argument("--floor", action="store_true", help="the similarity of every pair, expected and not")
    ap.add_argument("--sweep", action="store_true", help="precision at each candidate similarity floor")
    args = ap.parse_args()

    vaults = corpus()
    known = {card["id"] for card in hive.list_cards()}
    pair_list, source = pairs(known)
    print("Adobee Hive · search evaluation")
    print(f"  corpus:  {len(known)} entities ({len(vaults)} from testdata/vaults, the rest seeded)")
    print(f"  queries: {len(pair_list)} ({source})")
    print(f"  provider: {semantic.provider().name}, floor {semantic.SIMILARITY_FLOOR}")
    if not pair_list:
        print("\nNo scoring pairs. Nothing measured.")
        return 1

    before, after = run(pair_list, semantics=False), run(pair_list, semantics=True)
    print("\n                            literal only    with semantics")
    print(f"  precision at 1                 {before['p1']:.3f}            {after['p1']:.3f}")
    print(f"  precision at 3                 {before['p3']:.3f}            {after['p3']:.3f}")
    print(f"  queries with any evidence      {before['evidence']:.3f}            {after['evidence']:.3f}")

    fixed = [a["query"] for a, b in zip(after["rows"], before["rows"], strict=True) if a["hit"] and not b["hit"]]
    broke = [a["query"] for a, b in zip(after["rows"], before["rows"], strict=True) if b["hit"] and not a["hit"]]
    still = [a["query"] for a in after["rows"] if not a["hit"]]
    print(f"\n  fixed by the semantics ({len(fixed)}): {', '.join(repr(q) for q in fixed) or 'none'}")
    print(f"  broken by the semantics ({len(broke)}): {', '.join(repr(q) for q in broke) or 'none'}")
    print(f"  still wrong at 1 ({len(still)}): {', '.join(repr(q) for q in still) or 'none'}")

    if args.verbose:
        print("\nEvery query:")
        for row in after["rows"]:
            mark = "ok  " if row["hit"] else "MISS"
            print(f"  {mark} {row['query']!r} [{row['side']}] -> {', '.join(row['top'])}")
            print(f"       expected {', '.join(row['expected'])}; why: {'; '.join(row['why'][:2]) or '-'}")
    if args.floor:
        floors(pair_list)
    if args.sweep:
        sweep(pair_list)

    db.close()
    return 1 if after["p1"] < before["p1"] else 0


if __name__ == "__main__":
    sys.exit(main())
