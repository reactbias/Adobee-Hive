import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from .db import SessionLocal, init_db
from .documents import SUPPORTED_EXT
from .service import (create_organization, create_position, process_document,
                      register_file, to_dataframe)


def main():
    ap = argparse.ArgumentParser(prog="cv-analyzer")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("create-org"); a.add_argument("name")

    b = sub.add_parser("create-position")
    b.add_argument("--org-id", type=int, required=True)
    b.add_argument("--title", required=True)
    b.add_argument("--description")
    b.add_argument("--custom-fields", help='JSON file: [{"name": "...", "description": "..."}]')

    c = sub.add_parser("ingest")
    c.add_argument("folder")
    c.add_argument("--org-id", type=int, required=True)
    c.add_argument("--position-id", type=int)
    c.add_argument("--workers", type=int, default=3)

    d = sub.add_parser("export")
    d.add_argument("--org-id", type=int, required=True)
    d.add_argument("--position-id", type=int)
    d.add_argument("--out", default="candidates.csv")

    args = ap.parse_args()
    init_db()

    with SessionLocal() as s:
        if args.cmd == "create-org":
            org = create_organization(s, args.name)
            print(f"org_id={org.id}  api_key={org.api_key}")

        elif args.cmd == "create-position":
            custom = json.loads(Path(args.custom_fields).read_text()) if args.custom_fields else []
            pos = create_position(s, args.org_id, args.title, args.description, custom)
            print(f"position_id={pos.id}")

        elif args.cmd == "ingest":
            files = [p for p in Path(args.folder).rglob("*") if p.suffix.lower() in SUPPORTED_EXT]
            to_process = []
            for f in files:
                doc, created = register_file(s, args.org_id, args.position_id, f)
                if created or doc.status in ("failed", "pending"):
                    to_process.append(doc.id)
            print(f"{len(files)} files found, {len(to_process)} to process")
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(process_document, i) for i in to_process]
                stats = {}
                for fut in tqdm(as_completed(futures), total=len(futures)):
                    st = fut.result()
                    stats[st] = stats.get(st, 0) + 1
            print(stats)

        elif args.cmd == "export":
            df = to_dataframe(s, args.org_id, args.position_id)
            df.to_csv(args.out, index=False)
            print(f"wrote {len(df)} rows to {args.out}")


if __name__ == "__main__":
    main()