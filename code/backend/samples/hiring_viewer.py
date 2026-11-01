"""SAMPLE, for presenting: the hiring path in one page, with nothing to install but the backend.

This is not the Hive's app. The app's hiring screen is `code/frontend/src/panels/HiringPanel.tsx` on the real
hub (`documentation/HIRING.md`). This is a small local server (standard library only) that runs the same
`talent.search` and `interview.run` on a throwaway hub, so a talk can show the process without a frontend build,
Node or a seeded hub:

    python samples/hiring_viewer.py                 # then open http://127.0.0.1:8765
    python samples/hiring_viewer.py --port 9000 --no-browser

Step by step, as the page does it: it opens on a posting and the people it fits; edit the posting and the people
change; press the button and the agents interview; tick a person who says `ask` to play their yes and run again.
It listens on 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import recruit_demo  # noqa: E402

BACKEND = recruit_demo.BACKEND
sys.path.insert(0, str(BACKEND))
POSTINGS = BACKEND.parent / "cv_analyzer" / "job_postings"
MAX_BODY = 100_000
LOCK = threading.Lock()  # one hub at a time: a corpus switch rebuilds the database
CURRENT: dict = {"corpus": None, "people": 0}

FRONTEND_POSTING = """Frontend Developer (m/w/d) - Zürich

We are building an online shop and need someone to own the part customers see.

Requirements:
- 5+ years of professional frontend development experience
- Strong TypeScript; experience with Vue or React
- Experience with component libraries and design systems

Nice to have:
- Accessibility (WCAG) know-how
"""


def _is_person(name: str) -> bool:
    """Whether a vault of the original corpus is registered as a person (the seeder's own table decides)."""
    spec = importlib.util.spec_from_file_location("seed_vaults", BACKEND / "tools" / "seed_vaults.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    return seed.KIND.get(name) == "person"


def people(corpus: str) -> list[dict]:
    """The people in a corpus with what their folder says about screening, read from the folders directly."""
    out = []
    for vault in sorted(v for v in recruit_demo.corpus_path(corpus).iterdir() if v.is_dir()):
        if corpus == "vaults" and not _is_person(vault.name):
            continue
        policy = "ask"
        agent = vault / "agent.md"
        if agent.exists():
            found = re.search(r"(?im)^\s*[-*]?\s*screening\s*:\s*(\w+)", agent.read_text(encoding="utf-8"))
            policy = found.group(1).lower() if found else "ask"
        out.append({"id": vault.name, "policy": policy if policy in ("yes", "ask", "no") else "ask"})
    return out


def options() -> dict:
    """What the page offers: the corpora, and postings to start from."""
    postings = [
        {"name": p.stem.replace("_", " "), "text": p.read_text(encoding="utf-8-sig")}
        for p in sorted(POSTINGS.glob("*.txt"))
    ]
    postings.append({"name": "frontend developer (for the original vaults)", "text": FRONTEND_POSTING})
    return {"corpora": {name: people(name) for name in ("candidates", "vaults")}, "postings": postings}


def ensure(corpus: str) -> int:
    """The throwaway hub for this corpus: built once, rebuilt only when the corpus changes. Hold LOCK."""
    if CURRENT["corpus"] != corpus:
        CURRENT["people"] = len(recruit_demo.load(recruit_demo.corpus_path(corpus)))
        CURRENT["corpus"] = corpus
    return CURRENT["people"]


def _corpus(body: dict) -> str:
    corpus = body.get("corpus", "candidates")
    if corpus not in ("candidates", "vaults"):
        raise ValueError("corpus must be candidates or vaults")
    return corpus


def search(body: dict) -> dict:
    """Steps 1 and 2: the posting read into requirements, and the people whose cards fit it."""
    from app import talent

    corpus = _corpus(body)
    limit = max(1, min(int(body.get("limit", 8)), 20))
    with LOCK:
        count = ensure(corpus)
        found = talent.search(talent.parse_job(str(body.get("posting", ""))), limit=limit)
    return {"people": count, "search": found}


def run(body: dict) -> dict:
    """Step 3 onwards: the call `hr_interview` makes. `approve` plays the part of a person saying yes."""
    from app import interview, talent

    corpus = _corpus(body)
    limit = max(1, min(int(body.get("limit", 5)), 10))
    approve = [str(a) for a in (body.get("approve") or [])][:50]
    with LOCK:
        ensure(corpus)
        job = talent.parse_job(str(body.get("posting", "")))
        result = interview.run(job, recruiter="acme-hr", limit=limit, approve=approve)
    return {"result": result}


class Handler(BaseHTTPRequestHandler):
    """The page, its options, a search and a run."""

    def _send(self, status: int, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, data: dict) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str).encode()
        self._send(status, body, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802 - the stdlib's name
        """Serve the page and its options."""
        path = self.path.split("?")[0]
        if path == "/":
            self._send(200, PAGE.read_text(encoding="utf-8").encode(), "text/html; charset=utf-8")
        elif path == "/api/options":
            self._json(200, options())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - the stdlib's name
        """Search for a posting, or run its interviews."""
        routes = {"/api/run": run, "/api/search": search}
        if self.path not in routes:
            return self._json(404, {"error": "not found"})
        size = int(self.headers.get("Content-Length") or 0)
        if size > MAX_BODY:
            return self._json(413, {"error": "posting too large"})
        try:
            body = json.loads(self.rfile.read(size) or b"{}")
            self._json(200, routes[self.path](body))
        except (ValueError, KeyError) as err:
            self._json(400, {"error": str(err)})

    def log_message(self, fmt: str, *args) -> None:
        """Quiet: the page is the output."""


PAGE = Path(__file__).with_suffix(".html")


def main() -> int:
    """Start the server."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"Hiring sample on {url}  (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
