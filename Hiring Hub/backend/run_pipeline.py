"""
One-command pipeline: folder of CVs -> relevance gate vs. job posting -> SQLite -> review + CSV/Excel + JSON.

  python run_pipeline.py sample_cvs --fresh --position "Senior Software Engineer" \
      --description-file job_postings/senior_software_engineer.txt
  python run_pipeline.py sample_cvs --position "Senior Software Engineer" --force
  python run_pipeline.py sample_cvs --no-screening     # skip the relevance gate

CVs that do not fit the job posting get status "rejected": nothing about the candidate is stored
(no profile, no JSON, no CSV row); only the reason is kept on the document record.
"""
import argparse
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.stdout.reconfigure(errors="replace")


def parse_args():
    ap = argparse.ArgumentParser(description="Run the full CV extraction pipeline")
    ap.add_argument("folder", type=Path, help="Folder with CVs (.pdf .png .jpg .jpeg .webp)")
    ap.add_argument("--org", default="Demo", help="Organization name (created if missing)")
    ap.add_argument("--position", default="General", help="Position title (created if missing)")
    ap.add_argument("--description", help="Job posting text (used for the relevance gate)")
    ap.add_argument("--description-file", type=Path, help="Text file with the job posting")
    ap.add_argument("--custom-fields", type=Path, help="JSON file with custom questions")
    ap.add_argument("--min-score", type=int, help="Minimum relevance score 0-100 (default from config: 50)")
    ap.add_argument("--no-screening", action="store_true", help="Disable the relevance gate")
    ap.add_argument("--workers", type=int, default=1, help="Parallel extractions (default 1)")
    ap.add_argument("--force", action="store_true", help="Re-process CVs that are already done/rejected")
    ap.add_argument("--fresh", action="store_true", help="Delete database and storage first")
    ap.add_argument("--out", type=Path, help="Output folder (default: output/<position>)")
    return ap.parse_args()


def reset_storage():
    from cv_analyzer import config
    if config.DATABASE_URL.startswith("sqlite:///"):
        db = config.DATABASE_URL.removeprefix("sqlite:///")
        for suffix in ("", "-wal", "-shm"):
            p = Path(db + suffix)
            if p.exists():
                p.unlink()
    shutil.rmtree(config.STORAGE_DIR, ignore_errors=True)
    config.STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def _timed(fn, *a):
    t = time.time()
    return fn(*a), time.time() - t


def review_flags(d, p, max_pages: int) -> list[str]:
    """Automatic sanity checks: things a human should look at."""
    if d.status == "rejected":
        return [d.error or "rejected"]
    if d.status != "done" or p is None:
        return [f"FAILED: {d.error}"]
    ex, dv, flags = p.data, p.derived, []
    for k in ("full_name", "email", "phone"):
        if not ex["contact"].get(k):
            flags.append(f"missing {k}")
    if not ex["work_experience"]:
        flags.append("no work experience found")
    llm, comp = ex.get("total_years_experience"), dv.get("computed_years_experience")
    if llm is not None and comp is not None and abs(llm - comp) > 1.0:
        flags.append(f"experience mismatch: LLM {llm}y vs computed {comp}y")
    if d.page_count and d.page_count > max_pages:
        flags.append(f"truncated: {d.page_count} pages, only {max_pages} sent")
    if dv.get("short_tenures"):
        flags.append("short tenures: " + ", ".join(
            f"{t['company']} ({t['duration_months']}m)" for t in dv["short_tenures"]))
    if dv.get("employment_gaps"):
        flags.append("gaps: " + ", ".join(
            f"{g['from']}->{g['to']} ({g['months']}m)" for g in dv["employment_gaps"]))
    nf = [c["field_name"] for c in p.custom_fields if c["confidence"] == "not_found"]
    if nf:
        flags.append("custom fields not found: " + ", ".join(nf))
    if ex["quality"].get("notes"):
        flags.append(f"model note: {ex['quality']['notes']}")
    return flags


def cut(v, n):
    s = "-" if v in (None, "") else str(v)
    return s if len(s) <= n else s[: n - 1] + "â€¦"


def main():
    args = parse_args()
    if not args.folder.is_dir():
        sys.exit(f"Folder not found: {args.folder}")
    if args.fresh:
        reset_storage()
        print("Deleted database and storage.")

    from sqlalchemy import select

    from cv_analyzer import config
    if args.no_screening:
        config.SCREENING_ENABLED = False
    if args.min_score is not None:
        config.MIN_RELEVANCE_SCORE = args.min_score
    from cv_analyzer.db import CVDocument, Organization, Position, SessionLocal, init_db
    from cv_analyzer.documents import SUPPORTED_EXT
    from cv_analyzer.service import (create_organization, create_position, process_document,
                                     register_file, to_dataframe)

    init_db()
    custom = (json.loads(args.custom_fields.read_text(encoding="utf-8"))
              if args.custom_fields else None)
    description = (args.description_file.read_text(encoding="utf-8")
                   if args.description_file else args.description)

    # ---- 1. organization + position ----
    with SessionLocal() as s:
        org = (s.scalar(select(Organization).where(Organization.name == args.org))
               or create_organization(s, args.org))
        pos = s.scalar(select(Position).where(Position.org_id == org.id,
                                              Position.title == args.position))
        if pos is None:
            pos = create_position(s, org.id, args.position, description, custom or [])
        else:
            changed = False
            if custom is not None and custom != pos.custom_fields:
                pos.custom_fields, changed = custom, True
            if description and description != pos.description:
                pos.description, changed = description, True
            if changed:
                s.commit()
                print("Position updated. Use --force to re-process existing CVs with the new definition.")
        org_id, pos_id = org.id, pos.id
        gate = config.SCREENING_ENABLED and bool(pos.description)
        print(f"Org '{org.name}' (id={org_id}, api_key={org.api_key[:6]}â€¦) | "
              f"Position '{pos.title}' (id={pos_id}) | custom fields: "
              f"{[c['name'] for c in pos.custom_fields] or 'none'}")
        print(f"Relevance gate: {'ON (min score ' + str(config.MIN_RELEVANCE_SCORE) + ')' if gate else 'OFF'}"
              + ("" if gate or args.no_screening else " - no job description given"))

        # ---- 2. register files ----
        files = sorted(p for p in args.folder.rglob("*")
                       if p.is_file() and p.suffix.lower() in SUPPORTED_EXT)
        if not files:
            sys.exit(f"No supported files in {args.folder}")
        names, to_process = {}, []
        for f in files:
            doc, created = register_file(s, org_id, pos_id, f)
            names[doc.id] = doc.original_filename
            if created or args.force or doc.status not in ("done", "rejected"):
                to_process.append(doc.id)
        print(f"{len(files)} file(s) found, {len(to_process)} to process, "
              f"{len(files) - len(to_process)} already done.")

    # ---- 3. screening + extraction ----
    if to_process:
        print(f"\nProcessing with {config.OPENAI_MODEL}, {args.workers} worker(s)â€¦")
        t0 = time.time()
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(_timed, process_document, i): i for i in to_process}
            for n, fut in enumerate(as_completed(futs), 1):
                try:
                    status, secs = fut.result()
                except Exception as e:  # noqa: BLE001
                    status, secs = f"crashed: {type(e).__name__}: {e}", 0.0
                print(f"  [{n}/{len(to_process)}] {status:<8} {secs:5.0f}s  {names[futs[fut]]}")
        print(f"Finished in {time.time() - t0:.0f}s")

    # ---- 4. review + exports ----
    out = args.out or Path("output") / "".join(ch if ch.isalnum() else "_" for ch in args.position).strip("_").lower()
    out.mkdir(parents=True, exist_ok=True)
    json_dir = out / "json"
    shutil.rmtree(json_dir, ignore_errors=True)
    json_dir.mkdir(parents=True, exist_ok=True)

    lines, tok_in, tok_out, n_done, n_rej = [], 0, 0, 0, 0
    header = (f"{'id':>3}  {'status':<8} {'file':<34} {'name':<22} {'current title':<28} "
              f"{'level':<15} {'yrs':>5}")
    lines += [header, "-" * len(header)]
    with SessionLocal() as s:
        docs = s.scalars(select(CVDocument).where(CVDocument.org_id == org_id,
                                                  CVDocument.position_id == pos_id)
                         .order_by(CVDocument.id)).all()
        for d in docs:
            p = d.profile
            lines.append(f"{d.id:>3}  {d.status:<8} {cut(d.original_filename, 34):<34} "
                         f"{cut(p.full_name if p else None, 22):<22} "
                         f"{cut(p.current_job_title if p else None, 28):<28} "
                         f"{cut(p.career_level if p else None, 15):<15} "
                         f"{cut(p.total_years_experience if p else None, 5):>5}")
            for flag in review_flags(d, p, config.MAX_PAGES):
                lines.append(f"       ! {flag}")
            if d.status == "rejected":
                n_rej += 1
            if p:
                n_done += 1
                tok_in += p.prompt_tokens
                tok_out += p.completion_tokens
                (json_dir / f"{d.id:03d}_{Path(d.original_filename).stem}.json").write_text(
                    json.dumps({"document": {"id": d.id, "file": d.original_filename,
                                             "pages": d.page_count},
                                "extraction": p.data, "derived": p.derived,
                                "usage": {"model": p.model, "prompt_tokens": p.prompt_tokens,
                                          "completion_tokens": p.completion_tokens}},
                               indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")
        df = to_dataframe(s, org_id, pos_id)

    lines.append(f"\n{n_done} accepted, {n_rej} rejected as not relevant, "
                 f"{len(docs) - n_done - n_rej} failed/pending | "
                 f"extraction tokens: {tok_in:,} in / {tok_out:,} out")
    report = "\n".join(lines)
    print("\n" + report)
    (out / "review.txt").write_text(report, encoding="utf-8")

    # lists/dicts -> readable text for CSV/Excel
    for col in df.columns:
        df[col] = df[col].map(lambda v: "; ".join(map(str, v)) if isinstance(v, list)
                              else json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v)
    written = []
    for name, save in (("candidates.csv", lambda p: df.to_csv(p, index=False, encoding="utf-8-sig")),
                       ("candidates.xlsx", lambda p: df.to_excel(p, index=False))):
        try:
            try:
                save(out / name)
                written.append(name)
            except PermissionError:   # file is open in Excel/an editor -> write a side copy
                alt = f"{Path(name).stem}_{time.strftime('%H%M%S')}{Path(name).suffix}"
                save(out / alt)
                written.append(f"{alt} ({name} is locked)")
        except ImportError:
            pass
    print(f"\nWritten to {out}/: {', '.join(written)}, review.txt, json/ ({n_done} files)")


if __name__ == "__main__":
    main()
