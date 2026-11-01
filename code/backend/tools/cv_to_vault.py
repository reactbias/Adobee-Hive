"""Turn CV analyzer output into vault folders, so a résumé becomes a person on the Hive.

`code/cv_analyzer` reads a PDF résumé with a model and writes structured JSON: one `CVExtraction` per person.
That JSON is the owner's private record. This tool lays one person out the way every other vault on the Hive is
laid out, and `tools/seed_vaults.py` then registers it like any applicant:

    about.md       name and the two-sentence summary: what the Card calls the person
    work.md        "What I offer": the headline role, recent roles, certifications. This is what the Card
                   publishes and what talent search reads first
    contact.md     nothing published: the person is asked first
    cv.json        the whole extraction, `shared`: the Card never mentions it, and only a recruiter whose
                   request the person accepted can read it (email and phone are blanked on the way in)
    agent.md       the person's standing answer to a screening interview: yes, ask or no
    visibility.md  `cv.json: shared`

    python tools/cv_to_vault.py                                    # code/cv_analyzer/samples → testdata/candidates
    python tools/cv_to_vault.py --src some/extractions --dst /tmp/vaults
    python tools/cv_to_vault.py --check                            # fail if testdata/candidates has drifted

The folder is deterministic, so a re-run changes nothing and `--check` can gate CI. Everything produced is
fictional: the sample CVs are made-up people.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "code" / "cv_analyzer" / "samples" / "extractions"
DST = ROOT / "testdata" / "candidates"

#: What each person's agent says to a screening interview. Mixed on purpose, so the demo exercises all three
#: answers: most say yes, one asks first, one declines.
SCREENING = {"lena-frei": "ask", "oliver-grant": "no"}
DEFAULT_SCREENING = "yes"
MAX_OFFERS = 6


def slug(name: str) -> str:
    """A folder name from a person's name: "Elena Rostova" becomes `elena-rostova`, accents folded."""
    plain = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def _extraction(data: dict) -> dict:
    """The CVExtraction inside the pipeline's output, or the object itself when it is already one."""
    return data["extraction"] if isinstance(data.get("extraction"), dict) else data


def offers(cv: dict) -> list[str]:
    """What the person offers, as the bullets a vault's `work.md` holds: the headline, recent roles, certificates."""
    lines: list[str] = []
    skills = (cv.get("technical_skills") or [])[:8]
    if cv.get("current_job_title"):
        lines.append(f"{cv['current_job_title']} — {', '.join(skills)}" if skills else cv["current_job_title"])
    for job in (cv.get("work_experience") or [])[:3]:
        what = (job.get("responsibilities") or job.get("achievements") or [""])[0].rstrip(".")
        head = f"{job.get('job_title') or 'Role'}" + (f" at {job['company']}" if job.get("company") else "")
        lines.append(f"{head} — {what[:160]}" if what else head)
    lines += [str(c["name"]) for c in cv.get("certifications") or [] if c.get("name")]
    return lines[:MAX_OFFERS]


def scrubbed(data: dict) -> dict:
    """The extraction without the person's contact details, which a screening never needs."""
    out = json.loads(json.dumps(data))
    cv = _extraction(out)
    for key in ("email", "phone", "website"):
        if isinstance(cv.get("contact"), dict):
            cv["contact"][key] = None
    cv["social_links"] = []
    return out


def render(data: dict) -> dict[str, str]:
    """One person's vault as {file name: contents}."""
    cv = _extraction(data)
    contact = cv.get("contact") or {}
    name = contact.get("full_name") or "Unnamed"
    place = ", ".join(str(contact[k]) for k in ("location", "country") if contact.get(k))
    summary = (cv.get("professional_summary") or "").strip()
    about = f"# {name}\n\n{summary}{' Based in ' + place + '.' if place else ''}\n"
    work = "# What I offer\n\n" + "\n".join(f"- {line}" for line in offers(cv)) + "\n"
    return {
        "about.md": about,
        "work.md": work,
        "contact.md": "# Contact\n\n- email: ask first\n- phone: never\n",
        "visibility.md": "# Visibility\n\n- cv.json: shared\n",
        "agent.md": f"# Agent\n\n- screening: {SCREENING.get(slug(name), DEFAULT_SCREENING)}\n",
        "cv.json": json.dumps(scrubbed(data), indent=2, ensure_ascii=False) + "\n",
    }


def build(src: Path, dst: Path, check: bool = False) -> int:
    """Write (or, with `check`, compare) a vault per extraction in `src`. Returns how many differ or were written."""
    changed = 0
    for path in sorted(src.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        name = (_extraction(data).get("contact") or {}).get("full_name") or path.stem
        vault = dst / slug(name)
        for file, text in render(data).items():
            target = vault / file
            if target.exists() and target.read_text(encoding="utf-8") == text:
                continue
            changed += 1
            if check:
                print(f"drifted: {target.relative_to(dst)}")
                continue
            vault.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {target.relative_to(dst)}")
    return changed


def main() -> int:
    """Command line: write the vaults, or check that the committed ones are what the extractions produce."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default=str(SRC), help="a folder of CV analyzer JSON files")
    ap.add_argument("--dst", default=str(DST), help="where the vault folders go")
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if a file would change")
    args = ap.parse_args()
    src, dst = Path(args.src), Path(args.dst)
    if not src.is_dir():
        print(f"no extractions at {src}")
        return 1
    changed = build(src, dst, check=args.check)
    print(f"{changed} file(s) {'would change' if args.check else 'written'}")
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
