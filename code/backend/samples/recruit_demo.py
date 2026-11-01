"""Run a job posting through the whole hiring path, in process, narrating what each agent does.

No server, no Docker, no key: it opens a throwaway database, publishes the person cards from a folder corpus,
and calls the same `search` and `interview.run` the MCP tools `hr_shortlist` and `hr_interview` call.

    python samples/recruit_demo.py ../cv_analyzer/job_postings/senior_software_engineer.txt
    python samples/recruit_demo.py posting.txt --slow                 # a beat between lines, to watch it happen
    python samples/recruit_demo.py posting.txt --dialogues 3         # show the interview of the top 3, not 1
    python samples/recruit_demo.py posting.txt --corpus vaults --approve jonas-brun ilaria-conti
    python samples/recruit_demo.py posting.txt --shortlist-only      # steps 1 and 2 only

`--corpus` is `candidates` (the CV-based vaults, default), `vaults` (the original test corpus, whose people have
never said yes to a recruiter, so nothing is interviewed without `--approve`) or a path to any folder of vaults.
`--approve` plays the part of the people: it stands in for their yes, which on a real hub comes only from the
`agent.md` in their own folder.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import textwrap
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
TESTDATA = BACKEND.parents[1] / "testdata"
WIDTH = 100
PAUSE = 0.0


def say(text: str = "", indent: int = 0) -> None:
    """Print one line, wrapped, with a beat after it when `--slow` is on."""
    for line in textwrap.wrap(text, WIDTH - indent) or [""]:
        print(" " * indent + line, flush=True)
    time.sleep(PAUSE)


def banner(title: str) -> None:
    """A step heading."""
    print()
    print("=" * WIDTH)
    print(title)
    print("=" * WIDTH, flush=True)
    time.sleep(PAUSE * 2)


def corpus_path(name: str) -> Path:
    """`candidates` and `vaults` by name, anything else as a path."""
    return TESTDATA / name if name in ("candidates", "vaults") else Path(name)


def load(root: Path) -> list[str]:
    """Open a throwaway hub and publish the person cards in `root`. Returns their ids."""
    os.environ["DUCKDB_PATH"] = str(Path(tempfile.mkdtemp()) / "recruit.duckdb")
    os.environ["FOLDER_ROOT"] = str(root)
    if str(BACKEND) not in sys.path:
        sys.path.insert(0, str(BACKEND))
    from app import (
        activity,
        blocklist,
        config,
        connections,
        db,
        folder_keys,
        folders,
        hive,
        registration,
        removals,
        waiting,
    )

    # Callable again and again (the web page does): a fresh database and the folder link pointed at this corpus.
    db.close()
    config.DUCKDB_PATH = Path(os.environ["DUCKDB_PATH"])
    config.FOLDER_ROOT = root
    folders.reset()
    db.init()
    for module in (hive, waiting, activity, blocklist, folders, folder_keys, connections, registration, removals):
        module.init()
    spec = importlib.util.spec_from_file_location("seed_vaults", BACKEND / "tools" / "seed_vaults.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    ids = []
    for vault in sorted(v for v in root.iterdir() if v.is_dir()):
        card = seed.build_card(vault)
        if card["kind"] == "person":
            hive.publish(card)
            ids.append(card["id"])
    return ids


def step_posting(text: str, job: dict) -> None:
    """Step 1: the posting and what was understood of it."""
    banner("STEP 1  The job posting, read into requirements")
    for line in text.strip().splitlines():
        print("  | " + line)
    print()
    say(
        "The recruiter's agent splits the posting into requirements. 'AWS, Azure or GCP' is ONE requirement with "
        "three alternatives. A must-have is worth 3 points, the role in the title 2, a nice-to-have 1."
    )
    print()
    for req in job["requirements"]:
        print(f"  [{req['kind']:4}] {req['label']}")
        if len(req["options"]) > 1:
            print(f"           any of: {', '.join(req['options'])}")
        if req["related"]:
            print(f"           also counts (implies it): {', '.join(req['related'][:8])}")
        time.sleep(PAUSE / 2)
    facts = [f"{job['min_years']:g}+ years" if job["min_years"] else "", job["location"] or "", *job["languages"]]
    print("  checked as facts, not skills:", ", ".join(f for f in facts if f) or "none")


def step_search(found: dict) -> None:
    """Step 2: the search over the person cards."""
    banner(f"STEP 2  Search the {found['considered']} person cards (signed JSON) for those requirements")
    say(
        "For every card the search reads offers, skills, headline, description and countersigned claims. NOT "
        "'needs' (someone who needs a designer is not one) and never contact details. For each requirement it looks "
        "for the best line, strongest kind of match first:"
    )
    print("    literal  1.0   the words are there (stems, accents, aliases: Postgres = PostgreSQL)")
    print("    related  0.8   the card says something that implies it (React implies frontend)")
    print("    partial  0.6   more than half of a multi-word requirement")
    print("    similar  0.45-0.8  the semantic table finds a close line (haircut ~ 'Cut, wash and finish')")
    print()
    for m in found["matches"]:
        print(f"  {m['score']:5.1f}  {m['name']}   ({m['musts_met']} of {m['musts_total']} must-haves on the card)")
        for e in m["evidence"]:
            if e["covered"]:
                print(f"           + {e['requirement'][:34]:34} {e['how']:8} \"{e.get('quote', '')[:48]}\"")
        if m["gaps"]:
            print(f"           - nothing on the card for: {', '.join(m['gaps'][:4])}")
        time.sleep(PAUSE)
    if found["excluded"]:
        print()
        print("  Left out, with the reason:")
        for e in found["excluded"][:6]:
            print(f"    {e['name']}: {e['why_not'][0]}")


def step_consent(result: dict) -> None:
    """Step 3: the recruiter's agent asks each candidate's agent."""
    banner("STEP 3  The recruiter's agent contacts each shortlisted person's agent")
    say(
        f"Recruiter agent '{result['recruiter']}' may not read anyone's folder. Each candidate's agent checks the "
        "person's own rule (agent.md in their folder: yes / ask / no):"
    )
    print()
    for r in result["ranking"]:
        c = r["consent"]
        icon = {"granted": "YES    ", "awaiting_consent": "ASK    ", "declined": "NO     ", "no_folder": "NOFOLDER"}[
            c["state"]
        ]
        print(f"  {icon} {r['name']}: {c['why']}")
        if c["state"] == "granted":
            print(f"          folder link opened; shared with the recruiter: {', '.join(c['granted'])}")
            print("          (private/hidden files and contact details are never shared)")
        time.sleep(PAUSE)


def step_dialogue(entry: dict, number: int) -> None:
    """Step 4: one interview, line by line."""
    banner(f"STEP 4.{number}  Interview: recruiter agent  <->  {entry['name']}'s agent")
    say(
        f"{entry['name']}'s agent opens only these files from its owner's folder: {', '.join(entry['read'])}. "
        "It answers by quoting lines from them; if no line speaks to the question, it says so."
    )
    for t in entry["transcript"]:
        print()
        print("  RECRUITER AGENT >", t["question"])
        a = t["answer"]
        tag = {"direct": "found", "related": "close", "weak": "loose", "none": "nothing"}[a["support"]]
        print(f"  {entry['name'].upper().split()[0]}'S AGENT   > [{tag}] {a['text']}")
        time.sleep(PAUSE * 2)
    print()
    print(
        f"  Rescored with those lines as evidence: card {entry['stage1_score']:g} -> {entry['score']:g}; "
        f"experience: {entry['years']['note']}"
    )


def step_ranking(result: dict) -> None:
    """Step 5: the ranking and what happens next."""
    banner("STEP 5  Ranking")
    say(result["summary"])
    print()
    for r in result["ranking"]:
        bar = "#" * int(r["score"] / 5)
        print(f"  #{r['rank']} {r['name']:18} {r['score']:5.1f} {bar:20} {r['verdict']:14} [{r['status']}]")
        if r["gaps"]:
            print(f"        not shown for: {', '.join(r['gaps'][:4])}")
    print()
    say(result["next_step"])


def main() -> int:
    """Command line entry."""
    global PAUSE
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("posting", help="a text file with the job posting")
    ap.add_argument("--corpus", default="candidates", help="candidates, vaults, or a folder of vaults")
    ap.add_argument("--approve", nargs="*", default=[], help="ids whose person says yes to an interview")
    ap.add_argument("--limit", type=int, default=5, help="how many to shortlist")
    ap.add_argument("--recruiter", default="acme-hr", help="the recruiter's agent name")
    ap.add_argument("--dialogues", type=int, default=1, help="how many interviews to show line by line")
    ap.add_argument("--slow", action="store_true", help="pause between lines, to watch it happen")
    ap.add_argument("--shortlist-only", action="store_true", help="only steps 1 and 2")
    ap.add_argument("--json", action="store_true", help="print the raw result instead")
    args = ap.parse_args()
    PAUSE = 0.35 if args.slow else 0.0

    text = Path(args.posting).read_text(encoding="utf-8-sig")
    ids = load(corpus_path(args.corpus))
    from app import interview, talent

    job = talent.parse_job(text)
    found = talent.search(job, limit=args.limit)
    if args.json:
        result = (
            None
            if args.shortlist_only
            else interview.run(job, recruiter=args.recruiter, limit=args.limit, approve=args.approve)
        )
        print(json.dumps(found if result is None else result, indent=2, ensure_ascii=False))
        return 0
    print(f"{len(ids)} people published on a throwaway hub from '{args.corpus}'.")
    step_posting(text, found["job"])
    step_search(found)
    if args.shortlist_only:
        return 0
    result = interview.run(job, recruiter=args.recruiter, limit=args.limit, approve=args.approve)
    step_consent(result)
    shown = [r for r in result["ranking"] if r["status"] == "interviewed"][: args.dialogues]
    if not shown:
        banner("STEP 4  Interview")
        say(
            "Nobody could be interviewed: no shortlisted person's folder says yes. "
            "Rerun with --approve <id> to play the part of a person who agrees."
        )
    for n, entry in enumerate(shown, 1):
        step_dialogue(entry, n)
    step_ranking(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
