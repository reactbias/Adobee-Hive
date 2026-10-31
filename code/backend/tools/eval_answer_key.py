"""Score `hive.discover` against the answer key in testdata/README.md, and print where it ranks.

The corpus is only half the deliverable; this is the other half. Every row of the key is a query a
person would really type next to the entity it should return, chosen so that the query shares no
searchable word with the card. So the number this prints is exactly the thing semantic search is
supposed to move, and it moves without anybody rewriting the test data:

    python tools/eval_answer_key.py                 # every pair, ranked
    python tools/eval_answer_key.py --quiet         # just the two totals
    python tools/eval_answer_key.py --hub bern      # only the pairs whose target lives there

It publishes the whole corpus into a throwaway database and calls `hive.discover` in process, so it
needs no running hub and writes nothing. Every pair is a *miss* until matching stops being literal:
that is the baseline, not a bug in the key.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ANSWER_KEY = BACKEND.parents[1] / "testdata" / "README.md"


def pairs(hub: str = "") -> list[tuple[str, str, str]]:
    """The (query, expected slug, hub) rows between the answer-key markers in testdata/README.md."""
    block = ANSWER_KEY.read_text(encoding="utf-8").split("<!-- answer-key -->")[1].split("<!-- /answer-key -->")[0]
    rows = []
    for line in block.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3 or cells[0].startswith("---") or cells[0] == "What a person types":
            continue
        if not hub or cells[2] == hub:
            rows.append((cells[0], cells[1].strip("`"), cells[2]))
    return rows


def load_corpus() -> None:
    """Open a throwaway database, create every table the app creates, and publish all 61 cards."""
    os.environ.setdefault("DUCKDB_PATH", str(Path(tempfile.mkdtemp()) / "eval.duckdb"))
    sys.path.insert(0, str(BACKEND))
    from app import activity, blocklist, connections, db, hive, registration, waiting

    db.init()
    for module in (hive, waiting, activity, blocklist, connections, registration):
        module.init()

    spec = importlib.util.spec_from_file_location("seed_vaults", BACKEND / "tools" / "seed_vaults.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    for vault in sorted(seed.VAULTS.iterdir()):
        if vault.is_dir():
            hive.publish(seed.build_card(vault))


def rank_of(slug: str, query: str) -> tuple[int | None, list[str]]:
    """Where `slug` comes in the results for `query`, ignoring everything that scored zero."""
    from app import hive

    found = [m["id"] for m in hive.discover(query=query)["matches"] if m["score"] > 0]
    return (found.index(slug) + 1 if slug in found else None), found[:3]


def main() -> int:
    """Run every pair and report first-place and top-three rates. Exit code is the number of misses."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hub", default="", help="only pairs whose target lives on this hub")
    ap.add_argument("--quiet", action="store_true", help="print only the totals")
    args = ap.parse_args()

    load_corpus()
    rows = pairs(args.hub)
    first = top3 = 0
    for query, slug, _hub in rows:
        rank, top = rank_of(slug, query)
        first += rank == 1
        top3 += bool(rank and rank <= 3)
        if not args.quiet:
            mark = "1st" if rank == 1 else (f"#{rank}" if rank else "miss")
            print(f"  {mark:5} {slug:28} {query[:50]:50} got: {', '.join(top) or '(nothing scored)'}")

    print(f"\n{first}/{len(rows)} first, {top3}/{len(rows)} in the top three")
    return len(rows) - top3


if __name__ == "__main__":
    sys.exit(main())
