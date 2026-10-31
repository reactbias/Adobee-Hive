"""Serve three vaults from `testdata/vaults/` as plain files over HTTP, honouring their visibility.

The other half of search is not the Card. A Card is already structured: `offers`, `needs`, a digest
per file. The harder job is the one an end-user agent has on the owner's own machine — point it at a
folder of real files and ask it a question. This serves three such folders over HTTP with a
directory listing, so an agent can crawl them with nothing but an HTTP client: no Python, no venv,
no knowledge of this repo.

    python tools/serve_folders.py                      # the three default vaults on 127.0.0.1:8600
    python tools/serve_folders.py --port 9000
    python tools/serve_folders.py --host 0.0.0.0       # reachable from another device
    python tools/serve_folders.py --vault hotel-krafft --vault lena-hofmann
    python tools/serve_folders.py --strict             # only `public`, not `public-summary`
    python tools/serve_folders.py --list               # print what would be served, serve nothing

## What it will not serve, and why that is the whole point

A vault's `visibility.md` says how much of each path its owner lets out. The five values are the
ones in `documentation/cards/README.md`, and `tools/seed_vaults.py` is where they are parsed — this
module imports that parser rather than reimplementing it, so the fixture cannot drift from the Card
the hub actually publishes:

| `visibility.md` says | In the Card (`structure`)      | Served here           |
| -------------------- | ------------------------------ | --------------------- |
| `public`             | path, size, media type, digest | **yes**               |
| `public-summary`     | the same; also the default     | yes (no with `--strict`) |
| `private`            | the folder and a file count    | **no** — count only   |
| `shared`             | absent entirely                | **no** — not mentioned |
| `hidden`             | absent entirely                | **no** — not mentioned |

Anything not on the allowlist answers **404**, including a path an agent guesses from a Card's own
`structure` rows. A `private` folder is listed as a count and nothing else, because a count is "how
much" and never "what"; a `shared` or `hidden` folder is not mentioned at all, because listing a
folder in order to say it is secret still leaks that it exists.

The default serves `public` and `public-summary` together: that is the set the hub itself reads
(`seed_vaults.readable`, which turns these files into the Card's `offers` and `needs`) and the set
whose paths and digests the Card already publishes. `documentation/cards/README.md` draws a finer
line — `public` contents are for anyone, `public-summary` contents for a handshaked peer — and
`--strict` is that reading, for an agent that should only see what a stranger may read.

Read-only, GET and HEAD only, no writes and no traversal out of a vault.
"""

from __future__ import annotations

import argparse
import html
import importlib.util
import mimetypes
import socketserver
import sys
from collections.abc import Iterable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parents[1]
VAULTS = ROOT / "testdata" / "vaults"

#: Three deliberately unlike folders: a tavern with rooms, a freelance developer, an electrician.
#: One is a stay on `basel`, one a person on `zurich`, one a trade on `bern`; between them they
#: carry markdown, PDFs, a PNG and CSVs, and each one withholds something, so an agent pointed at
#: these three faces genuinely different material and a real privacy boundary in every folder.
DEFAULT_VAULTS = ("wirtshaus-anker", "jonas-brun", "elektro-mattenhof")

DEFAULT_PORT = 8600
DEFAULT_HOST = "127.0.0.1"


def _seed_vaults():
    """`tools/seed_vaults.py` as a module. It is a script, so it is loaded by path, not imported.

    The visibility rule lives there because that is what builds the Card. Importing it is what keeps
    this fixture and the hub from ever disagreeing about which file is private.
    """
    spec = importlib.util.spec_from_file_location("seed_vaults", BACKEND / "tools" / "seed_vaults.py")
    if spec is None or spec.loader is None:  # pragma: no cover - the file is in the repo
        raise RuntimeError(f"cannot load {BACKEND / 'tools' / 'seed_vaults.py'}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_seed = _seed_vaults()
read_visibility = _seed.read_visibility
visibility_of = _seed.visibility_of
media_type = _seed.media_type
OPEN_VISIBILITIES: tuple[str, ...] = tuple(_seed.OPEN_VISIBILITIES)
COUNT_ONLY: str = _seed.COUNT_ONLY
UNLISTED: tuple[str, ...] = tuple(_seed.UNLISTED)
#: What `--strict` serves: only what `documentation/cards/README.md` says a stranger may read.
STRICT_VISIBILITIES: tuple[str, ...] = ("public",)


class Vault:
    """One folder, split into what may be served, what may only be counted, and what is not named."""

    def __init__(self, path: Path, allowed: Iterable[str] = OPEN_VISIBILITIES) -> None:
        self.path = path
        self.name = path.name
        self.allowed = tuple(allowed)
        rules = read_visibility(path)
        self.served: dict[str, Path] = {}
        self.counted: dict[str, int] = {}
        self.withheld = 0
        for file in sorted(f for f in path.rglob("*") if f.is_file()):
            relative = file.relative_to(path).as_posix()
            visibility, rule = visibility_of(relative, rules)
            if visibility in self.allowed:
                self.served[relative] = file
                continue
            self.withheld += 1
            if visibility == COUNT_ONLY:
                # A `private` folder is admitted to as a count, exactly as the Card admits to it.
                key = rule if rule.endswith("/") else relative
                self.counted[key] = self.counted.get(key, 0) + 1

    @property
    def title(self) -> str:
        """The owner's own name for themselves: the first heading of about.md, or the folder name."""
        about = self.path / "about.md"
        if "about.md" in self.served and about.exists():
            for line in about.read_text(encoding="utf-8").splitlines():
                if line.startswith("# "):
                    return line[2:].strip()
        return self.name

    @property
    def kinds(self) -> dict[str, int]:
        """How many of each media type is served, so the startup banner can say what is in here."""
        out: dict[str, int] = {}
        for relative in self.served:
            suffix = Path(relative).suffix.lstrip(".").lower() or "no extension"
            out[suffix] = out.get(suffix, 0) + 1
        return dict(sorted(out.items()))

    def summary(self) -> str:
        """One line: how many files of what, and how many are withheld."""
        spread = ", ".join(f"{count} {ext}" for ext, count in self.kinds.items()) or "nothing"
        held = f", {self.withheld} withheld" if self.withheld else ""
        return f"{len(self.served)} file{'' if len(self.served) == 1 else 's'} ({spread}){held}"

    def resolve(self, relative: str) -> Path | None:
        """The file for one served path, or None. The allowlist decides; the filesystem never does."""
        return self.served.get(relative)


def load(names: Iterable[str], allowed: Iterable[str] = OPEN_VISIBILITIES) -> list[Vault]:
    """The named vaults, in the order given. Raises when one is not a folder in testdata/vaults."""
    vaults = []
    for name in names:
        path = VAULTS / name
        if not path.is_dir():
            raise FileNotFoundError(f"no vault {name!r} in {VAULTS}")
        vaults.append(Vault(path, allowed))
    return vaults


# ---------------------------------------------------------------- the pages

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font:15px/1.6 system-ui,sans-serif;max-width:46rem;margin:3rem auto;padding:0 1rem}}
h1{{font-size:1.3rem}} li{{margin:.15rem 0}} .note{{color:#666;font-size:.9rem}}
code{{background:#f3f3f3;padding:0 .25rem;border-radius:3px}}</style></head>
<body><h1>{title}</h1>{body}</body></html>
"""


def index_page(vaults: list[Vault]) -> bytes:
    """The root listing: one entry per folder, with what is in it."""
    rows = "".join(
        f'<li><a href="/{html.escape(v.name)}/">{html.escape(v.name)}/</a> — '
        f"{html.escape(v.title)} · {html.escape(v.summary())}</li>"
        for v in vaults
    )
    body = (
        f"<ul>{rows}</ul>"
        '<p class="note">Fictional entities from the Adobee Hive test corpus. Nothing here is a real '
        "business or a real person. Files their owner marked private, shared or hidden are not served "
        "and answer 404.</p>"
    )
    return _PAGE.format(title="Vaults", body=body).encode()


def vault_page(vault: Vault) -> bytes:
    """One folder's listing: every served file, then the counts of what is withheld."""
    rows = "".join(
        f'<li><a href="/{html.escape(vault.name)}/{html.escape(path)}">{html.escape(path)}</a> '
        f"<span class=note>{vault.served[path].stat().st_size} B · "
        f"{html.escape(media_type(vault.served[path]))}</span></li>"
        for path in sorted(vault.served)
    )
    held = "".join(
        f"<li><code>{html.escape(folder)}</code> — {count} file(s), withheld by the owner</li>"
        for folder, count in sorted(vault.counted.items())
    )
    body = f"<p class=note>{html.escape(vault.title)}</p><ul>{rows}</ul>"
    if held:
        body += f'<h2 style="font-size:1rem">Not served</h2><ul>{held}</ul>'
        body += '<p class="note">A count is how much, never what: no names, no sizes, no digests.</p>'
    return _PAGE.format(title=f"{vault.name}/", body=body).encode()


class Handler(BaseHTTPRequestHandler):
    """Read-only GET/HEAD over the allowlist. Anything else is 404 or 405."""

    server_version = "AdobeeHiveVaults/1"
    vaults: dict[str, Vault] = {}
    order: list[Vault] = []

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's own naming
        """Serve the index, a folder listing or one allowed file."""
        self._respond(body=True)

    def do_HEAD(self) -> None:  # noqa: N802
        """The same decision as GET, with no body: an agent can check a path before fetching it."""
        self._respond(body=False)

    def _respond(self, *, body: bool) -> None:
        target = unquote(self.path.split("?")[0].split("#")[0])
        if target in ("", "/"):
            self._send(200, "text/html; charset=utf-8", index_page(self.order), body)
            return
        head, _, rest = target.lstrip("/").partition("/")
        vault = self.vaults.get(head)
        if vault is None:
            self._send(404, "text/plain; charset=utf-8", b"not found\n", body)
            return
        if rest in ("", "/"):
            self._send(200, "text/html; charset=utf-8", vault_page(vault), body)
            return
        # The allowlist is a dict of exact relative paths, so "../" and symlinks cannot reach
        # anything: a path that is not a key is not served, whatever it resolves to on disk.
        file = vault.resolve(rest)
        if file is None:
            self._send(404, "text/plain; charset=utf-8", b"not found\n", body)
            return
        kind = media_type(file)
        charset = "; charset=utf-8" if kind.startswith("text/") or kind == "application/json" else ""
        self._send(200, f"{kind}{charset}", file.read_bytes(), body)

    def _send(self, status: int, kind: str, payload: bytes, body: bool) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        """One line per request on stderr, so a crawl can be watched."""
        sys.stderr.write(f"  {self.address_string()} {fmt % args}\n")


def make_server(vaults: list[Vault], host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> socketserver.BaseServer:
    """An HTTP server over these vaults. Port 0 picks a free one, which is what the tests use."""
    handler = type("BoundHandler", (Handler,), {"vaults": {v.name: v for v in vaults}, "order": vaults})
    ThreadingHTTPServer.allow_reuse_address = True
    return ThreadingHTTPServer((host, port), handler)


def banner(vaults: list[Vault], host: str, port: int, allowed: tuple[str, ...]) -> str:
    """What is being served and where, printed before the first request arrives."""
    shown = host if host != "0.0.0.0" else "<this machine>"  # noqa: S104 - printed, not bound here
    lines = [
        "Adobee Hive · three vaults as plain files",
        f"  serving visibility: {', '.join(allowed)}",
        f"  index:  http://{shown}:{port}/",
        "",
    ]
    for vault in vaults:
        lines.append(f"  http://{shown}:{port}/{vault.name}/")
        lines.append(f"      {vault.title}")
        lines.append(f"      {vault.summary()}")
        for folder, count in sorted(vault.counted.items()):
            lines.append(f"      not served: {folder} ({count} file(s), the owner's own rule)")
        lines.append("")
    lines += [
        "  Fictional test data. A file marked private, shared or hidden answers 404.",
        "  Ctrl-C to stop.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Start the server, or just print what it would serve."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"default {DEFAULT_PORT}")
    ap.add_argument("--host", default=DEFAULT_HOST, help=f"default {DEFAULT_HOST}; 0.0.0.0 for the LAN")
    ap.add_argument(
        "--vault",
        action="append",
        default=None,
        metavar="NAME",
        help=f"a folder in testdata/vaults, repeatable; default {' '.join(DEFAULT_VAULTS)}",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="serve only `public`, not `public-summary`: what a stranger may read per cards/README.md",
    )
    ap.add_argument("--list", action="store_true", help="print what would be served and exit")
    args = ap.parse_args(argv)

    allowed = STRICT_VISIBILITIES if args.strict else OPEN_VISIBILITIES
    try:
        vaults = load(args.vault or DEFAULT_VAULTS, allowed)
    except FileNotFoundError as err:
        print(f"{err}", file=sys.stderr)
        return 2

    print(banner(vaults, args.host, args.port, allowed))
    if args.list:
        return 0
    with make_server(vaults, args.host, args.port) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    mimetypes.init()
    sys.exit(main())
