"""The folder link: two agents connecting their private folders, before anything is booked.

The public index gets an agent to a candidate. It does not get it the contents of that candidate's
folder, and it must not: the Card publishes the *shape* of the folder — paths, sizes, digests — and
never a byte of it. Between "found you in the index" and "booked you" there is a step this module
owns:

    search ──> request_link ──> accept_link ──> grant ──> read ──> connect ──> rate
              └──────────── the two folders are now linked ────────┘

Two layers, kept apart on purpose, because collapsing them is how a directory turns into a leak:

**The link** is handle to handle. It says these two agents know each other, nothing more. It carries
no content. What it unlocks is the *manifest*: the linked peer gets to see that the `shared` files
exist at all, which the Card deliberately never says.

**A grant** is per path. It is the only thing that makes contents readable, and it is the owner's to
give. This is the shape ClaudeConnect already has — `add_friend`/`accept_friend_request` for the
link, `add_recipient_to_file` for the grant — and the reason `CcFolderLink` can sit behind the same
protocol without bending either side.

`structure.visibility` has five values (documentation/cards/README.md), and two of them are not
flags on a listed file but the absence of a listing:

| value            | in the Card              | a linked peer sees it | who reads the contents  |
| ---------------- | ------------------------ | --------------------- | ----------------------- |
| `public`         | path · digest            | yes                   | anyone                  |
| `public-summary` | path · digest            | yes                   | linked peer, with grant |
| `shared`         | **omitted entirely**     | yes                   | linked peer, with grant |
| `private`        | path, no digest          | no                    | owner only              |
| `hidden`         | **omitted entirely**     | no                    | owner only              |

Listing a file in order to say it is secret leaks its existence, so `hidden` and `private` paths are
never named to anyone but their owner — not in a manifest, and not in the reason a grant was
refused. A refused grant says the same words whether the file is hidden or simply absent.

Nothing here judges content. A file's visibility is read from the owner's own marker file; this
module never opens a file to decide anything about it, and the digest is over bytes it does not
interpret.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from . import config, db

log = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS folder_handles (
    handle VARCHAR PRIMARY KEY,
    root VARCHAR,
    claimed_at TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS folder_links (
    id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    state VARCHAR NOT NULL,
    from_handle VARCHAR NOT NULL,
    to_handle VARCHAR NOT NULL,
    accepted_at TIMESTAMP,
    accepted_by VARCHAR
);
CREATE TABLE IF NOT EXISTS folder_grants (
    id VARCHAR PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    owner VARCHAR NOT NULL,
    path VARCHAR NOT NULL,
    to_handle VARCHAR NOT NULL,
    link_id VARCHAR NOT NULL
);
"""

# --- the five values of structure.visibility ----------------------------------------
PUBLIC = "public"
PUBLIC_SUMMARY = "public-summary"
SHARED = "shared"
PRIVATE = "private"
HIDDEN = "hidden"
VISIBILITIES: tuple[str, ...] = (PUBLIC, PUBLIC_SUMMARY, SHARED, PRIVATE, HIDDEN)
#: What the owner may admit to a linked peer. `private` and `hidden` are the owner's alone.
ADMITTED: frozenset[str] = frozenset({PUBLIC, PUBLIC_SUMMARY, SHARED})
#: What the published Card lists. `shared` and `hidden` are omitted from it entirely.
IN_CARD: frozenset[str] = frozenset({PUBLIC, PUBLIC_SUMMARY, PRIVATE})
#: A path `visibility.md` says nothing about. Unchanged from when every vault was markdown, so a
#: folder that never thought about visibility keeps the Card it had (tools/seed_vaults.py agrees).
DEFAULT_VISIBILITY = PUBLIC_SUMMARY
#: Where the owner writes it, in the corpus's own format (testdata/README.md):
#:
#:     # Visibility
#:
#:     - hausordnung.pdf: public
#:     - gaeste/: private
#:     - buchhaltung/: hidden
#:
#: The file is itself an ordinary listed file, because the Card lists it: a folder that says what it
#: shows is not hiding the saying of it.
MARKER = "visibility.md"

REQUESTED = "requested"
ESTABLISHED = "established"

#: A handle is an agent's name on a hub: an entity id (`hotel-krafft`) or an address
#: (`mara@example.com`). ClaudeConnect validates a claimed bot handle with `^[a-z0-9_-]+$` and
#: issues it the synthetic address `<handle>@moltbook.cc.bot`, so both shapes are the same kind of
#: thing to it, and both have to be legal here.
HANDLE = re.compile(r"^[a-z0-9][a-z0-9._@+-]{0,99}$")


class FolderError(ValueError):
    """A folder link, grant or read that cannot be done as asked."""


@runtime_checkable
class FolderLink(Protocol):
    """Connecting two agents' folders, whoever is actually holding the files.

    `LocalFolderLink` is in-process and backed by the folders in `testdata/vaults/`; `CcFolderLink`
    is the same six calls against ClaudeConnect. The hub only ever sees this protocol, so the demo
    does not change shape when the real library is switched on — or when it is switched off again
    because claudeconnect.io is unreachable from the venue's wifi.

    A `path` is owner-qualified, `"<handle>/<relative/path.md>"`, so a grant and a read name the
    same file across both implementations and nothing has to carry the owner separately.
    """

    #: Which implementation this is, as `/api/health` reports it.
    kind: str

    def claim(self, handle: str) -> dict[str, Any]:
        """Take a handle and whatever folder belongs to it. Idempotent."""
        ...

    def request_link(self, from_handle: str, to_handle: str) -> dict[str, Any]:
        """Ask to link two folders. Returns the link, `requested` until the other side accepts."""
        ...

    def accept_link(self, link_id: str, *, by: str = "") -> dict[str, Any]:
        """The other side says yes. The link is now `established`."""
        ...

    def grant(self, path: str, to_handle: str) -> dict[str, Any]:
        """Let a linked handle read one path, or one folder of them."""
        ...

    def can_read(self, path: str, handle: str) -> bool:
        """Whether that handle may read that path right now."""
        ...

    def files(self, handle: str) -> list[dict[str, Any]]:
        """The owner's own view of their folder: every file, with its visibility."""
        ...


def init() -> None:
    """Create the tables. Idempotent, and safe to call from more than one module's `init`."""
    with db.write() as cur:
        cur.execute(SCHEMA_SQL)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def check_handle(handle: str) -> str:
    """A handle as it is stored: lower-cased, and refused outright if it could be a path.

    The refusal matters more than the normalising. A handle becomes a folder name below
    `FOLDER_ROOT`, so `../` in one would read somebody else's vault, and a hub that resolves it
    quietly is a hub that serves whatever an agent asks for.
    """
    name = (handle or "").strip().lower()
    if not name:
        raise FolderError("a folder link needs a handle")
    if not HANDLE.match(name):
        raise FolderError(f"{handle!r} is not a handle: letters, digits and . _ @ + - only")
    return name


def split_path(path: str) -> tuple[str, str]:
    """An owner-qualified path as its two halves: `"hotel-krafft/rooms.md"` → handle, relative.

    A bare handle is the whole folder, which is what a folder-wide grant is written as.
    """
    raw = (path or "").strip().strip("/")
    if not raw:
        raise FolderError("a path is needed")
    handle, _, rest = raw.partition("/")
    rel = "/".join(part for part in rest.split("/") if part not in ("", "."))
    if ".." in rel.split("/"):
        raise FolderError(f"{path!r} leaves the folder it names")
    return check_handle(handle), rel


def media_type(file: Path) -> str:
    """What a reader would need to open the file, guessed from its name, never from its contents.

    The same answer `tools/seed_vaults.py::media_type` gives, markdown included, because a Card row
    and a manifest row describe one file and should not disagree about what it is.
    """
    if file.suffix == ".md":
        return "text/markdown"
    guessed, _ = mimetypes.guess_type(file.name)
    return guessed or "application/octet-stream"


def digest(body: bytes) -> str:
    """A file's digest, in the form the Card publishes (tools/seed_vaults.py writes the same)."""
    return "sha256:" + hashlib.sha256(body).hexdigest()[:12]


def read_markers(root: Path) -> dict[str, str]:
    """The owner's `visibility.md`, parsed: one path or folder per line, `- gaeste/: private`.

    The same rules `tools/seed_vaults.py::read_visibility` applies when it builds a Card, because
    the folder and the Card have to be talking about the same file. `tests/test_folders.py` pins
    that agreement over the whole corpus rather than trusting this comment.

    An unreadable or malformed line leaves a path at `DEFAULT_VISIBILITY`, which is the safe
    direction: a typo cannot open a file, only fail to close it further than the default.
    """
    marker = root / MARKER
    if not marker.is_file():
        return {}
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except OSError as err:  # pragma: no cover - unreadable marker, same answer as a missing one
        log.warning("folders: cannot read %s (%s); every file keeps its default visibility", marker, err)
        return {}
    rules: dict[str, str] = {}
    for raw in lines:
        line = raw.strip().lstrip("-").strip()
        if ":" not in line or line.startswith("#"):
            continue
        target, _, value = line.partition(":")
        value = value.strip().lower()
        if value in VISIBILITIES:
            rules[target.strip().lstrip("/")] = value
    return rules


def visibility_of(rel: str, markers: dict[str, str]) -> str:
    """What the owner says about this one path. The longest rule wins.

    Longest, not last, so a folder can be `private` with one file inside it published — which is
    the rule `tools/seed_vaults.py` uses, and the same idea as ClaudeConnect's most-specific-section
    rule. Anything dotted is `hidden` without being written down: a folder's own bookkeeping is not
    part of what it offers, and `.git` is nobody's business.
    """
    if any(part.startswith(".") for part in rel.split("/")):
        return HIDDEN
    best, found = "", DEFAULT_VISIBILITY
    for target, value in markers.items():
        covers = rel == target or (target.endswith("/") and rel.startswith(target))
        if covers and len(target) >= len(best):
            best, found = target, value
    return found


class LocalFolderLink:
    """Folder links between folders this process can see, with the state in DuckDB.

    This is what the demo and the tests run on: no network, no key, no new dependency, and the same
    answer every time. The folders are the ones already in `testdata/vaults/` — the same markdown
    the seeded Cards were built from, so a file's digest here matches the digest the Card published.

    A handle with no folder (a traveller, say) is a perfectly good party to a link. It simply has
    nothing to offer: `files()` is empty and every `can_read` against it is False.
    """

    kind = "local"

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else config.FOLDER_ROOT

    # --- handles ---------------------------------------------------------------------

    def folder(self, handle: str) -> Path | None:
        """Where this handle's files are, or None when it holds none."""
        name = check_handle(handle)
        candidate = self.root / name
        return candidate if candidate.is_dir() else None

    def claim(self, handle: str) -> dict[str, Any]:
        """Take a handle and whatever folder belongs to it. Idempotent, so a re-claim is cheap."""
        name = check_handle(handle)
        folder = self.folder(name)
        with db.write() as cur:
            row = cur.execute("SELECT handle, root, claimed_at FROM folder_handles WHERE handle = ?", [name]).fetchone()
            if row is None:
                cur.execute(
                    "INSERT INTO folder_handles (handle, root, claimed_at) VALUES (?,?,?)",
                    [name, str(folder) if folder else "", _now()],
                )
            elif (row[1] or "") != (str(folder) if folder else ""):
                cur.execute(
                    "UPDATE folder_handles SET root = ? WHERE handle = ?", [str(folder) if folder else "", name]
                )
        return {"handle": name, "root": str(folder) if folder else "", "files": len(self.files(name))}

    # --- the link --------------------------------------------------------------------

    def request_link(self, from_handle: str, to_handle: str) -> dict[str, Any]:
        """Ask to link two folders.

        Idempotent in both directions: asking again for a link that exists returns that link rather
        than a second one, because two rows for one pair of agents is two answers to "are these two
        linked?" and only one of them can be right.
        """
        a, b = check_handle(from_handle), check_handle(to_handle)
        if a == b:
            raise FolderError(f"{a} is already {a}; a folder link joins two different agents")
        self.claim(a)
        self.claim(b)
        existing = self.between(a, b)
        if existing is not None:
            return existing
        link_id = f"fl-{db.new_id()}"
        with db.write() as cur:
            cur.execute(
                "INSERT INTO folder_links (id, created_at, state, from_handle, to_handle) VALUES (?,?,?,?,?)",
                [link_id, _now(), REQUESTED, a, b],
            )
        return self.get_link(link_id)

    def accept_link(self, link_id: str, *, by: str = "") -> dict[str, Any]:
        """The other side says yes.

        Accepting an already-established link returns it unchanged. That tolerance is deliberate:
        the owner's yes can arrive twice (a retry, a second confirm) and the second one must not be
        an error on stage.
        """
        link = self.get_link(link_id)
        if link["state"] == ESTABLISHED:
            return link
        with db.write() as cur:
            cur.execute(
                "UPDATE folder_links SET state = ?, accepted_at = ?, accepted_by = ? WHERE id = ?",
                [ESTABLISHED, _now(), check_handle(by) if by else link["to_handle"], link_id],
            )
        return self.get_link(link_id)

    def get_link(self, link_id: str) -> dict[str, Any]:
        """One link by id."""
        with db.cursor() as cur:
            row = cur.execute(
                "SELECT id, created_at, state, from_handle, to_handle, accepted_at, accepted_by"
                " FROM folder_links WHERE id = ?",
                [link_id],
            ).fetchone()
        if row is None:
            raise FolderError(f"no folder link {link_id!r}")
        return _link_row(row)

    def between(self, a: str, b: str) -> dict[str, Any] | None:
        """The link between two handles whichever way round it was asked for, or None."""
        one, two = check_handle(a), check_handle(b)
        with db.cursor() as cur:
            row = cur.execute(
                "SELECT id, created_at, state, from_handle, to_handle, accepted_at, accepted_by FROM folder_links"
                " WHERE (from_handle = ? AND to_handle = ?) OR (from_handle = ? AND to_handle = ?)"
                " ORDER BY created_at DESC LIMIT 1",
                [one, two, two, one],
            ).fetchone()
        return None if row is None else _link_row(row)

    def linked(self, a: str, b: str) -> bool:
        """Whether these two folders are actually linked, not merely asked about."""
        link = self.between(a, b)
        return bool(link and link["state"] == ESTABLISHED)

    def links(self, handle: str, state: str = "") -> list[dict[str, Any]]:
        """Every link this handle is party to, newest first."""
        name = check_handle(handle)
        sql = (
            "SELECT id, created_at, state, from_handle, to_handle, accepted_at, accepted_by FROM folder_links"
            " WHERE (from_handle = ? OR to_handle = ?)"
        )
        args: list[Any] = [name, name]
        if state:
            sql += " AND state = ?"
            args.append(state)
        with db.cursor() as cur:
            return [_link_row(r) for r in cur.execute(f"{sql} ORDER BY created_at DESC", args).fetchall()]

    # --- grants ----------------------------------------------------------------------

    def grant(self, path: str, to_handle: str) -> dict[str, Any]:
        """Let a linked handle read one path, or a whole folder of them.

        Refused unless the folders are linked, and refused for anything the owner does not admit
        exists. The refusal says the same words for a `hidden` file and for a missing one, on
        purpose: "you may not read that" and "there is no such thing" have to be indistinguishable
        or the refusal itself is the leak.
        """
        owner, rel = split_path(path)
        peer = check_handle(to_handle)
        link = self.between(owner, peer)
        if link is None or link["state"] != ESTABLISHED:
            raise FolderError(f"{owner} and {peer} have no established folder link, so there is nothing to grant on")
        if rel and not self._admits(owner, rel):
            raise FolderError(f"{owner} admits no file or folder at {rel!r}")
        grant_id = f"fg-{db.new_id()}"
        with db.write() as cur:
            row = cur.execute(
                "SELECT id FROM folder_grants WHERE owner = ? AND path = ? AND to_handle = ?", [owner, rel, peer]
            ).fetchone()
            if row is not None:
                grant_id = row[0]
            else:
                cur.execute(
                    "INSERT INTO folder_grants (id, created_at, owner, path, to_handle, link_id) VALUES (?,?,?,?,?,?)",
                    [grant_id, _now(), owner, rel, peer, link["id"]],
                )
        return {
            "id": grant_id,
            "owner": owner,
            "path": rel,
            "ref": f"{owner}/{rel}" if rel else owner,
            "to": peer,
            "link": link["id"],
        }

    def grants(self, owner: str, to_handle: str = "") -> list[dict[str, Any]]:
        """What this owner has granted, to everyone or to one handle."""
        name = check_handle(owner)
        sql, args = "SELECT id, owner, path, to_handle, link_id FROM folder_grants WHERE owner = ?", [name]
        if to_handle:
            sql += " AND to_handle = ?"
            args.append(check_handle(to_handle))
        with db.cursor() as cur:
            rows = cur.execute(f"{sql} ORDER BY created_at ASC", args).fetchall()
        return [
            {
                "id": r[0],
                "owner": r[1],
                "path": r[2],
                "ref": f"{r[1]}/{r[2]}" if r[2] else r[1],
                "to": r[3],
                "link": r[4],
            }
            for r in rows
        ]

    # --- reading ---------------------------------------------------------------------

    def _entries(self, handle: str) -> list[dict[str, Any]]:
        """Every file in this handle's folder, with the visibility its owner gave it.

        A dotted path is the folder's own bookkeeping — the marker file, a `.git` — and is not
        content. It is left out of the count as well as the listing: a withheld *number* that moves
        when a tool writes a dotfile says something about the folder that nobody chose to say.
        """
        folder = self.folder(handle)
        if folder is None:
            return []
        markers = read_markers(folder)
        out = []
        for file in sorted(p for p in folder.rglob("*") if p.is_file()):
            rel = file.relative_to(folder).as_posix()
            if any(part.startswith(".") for part in rel.split("/")):
                continue
            try:
                body = file.read_bytes()
            except OSError:  # pragma: no cover - a file we cannot read is a file we do not admit
                continue
            out.append(
                {
                    "path": rel,
                    "bytes": len(body),
                    "media_type": media_type(file),
                    "digest": digest(body),
                    "visibility": visibility_of(rel, markers),
                }
            )
        return out

    def files(self, handle: str) -> list[dict[str, Any]]:
        """The owner's own view: every file in their folder, with what they have said about it."""
        name = check_handle(handle)
        return [{**e, "ref": f"{name}/{e['path']}"} for e in self._entries(name)]

    def _admits(self, owner: str, rel: str) -> bool:
        """Whether the owner admits anything at this path at all — a file, or a folder of them."""
        prefix = rel.rstrip("/") + "/"
        return any(
            e["visibility"] in ADMITTED and (e["path"] == rel or e["path"].startswith(prefix))
            for e in self._entries(owner)
        )

    def manifest(self, owner: str, viewer: str) -> dict[str, Any]:
        """The folder as one viewer may see it, plus a count of what was withheld without naming it.

        Unlinked, a viewer sees what the published Card already says. Linked, they also see the
        `shared` files, which the Card never mentioned — that difference *is* the folder link, and
        it is the thing worth putting on a screen. Either way `private` and `hidden` paths are
        counted, never named.
        """
        name, peer = check_handle(owner), check_handle(viewer)
        entries = self._entries(name)
        if name == peer:
            return {"owner": name, "viewer": peer, "linked": True, "files": self.files(name), "withheld": 0}
        linked = self.linked(name, peer)
        allowed = ADMITTED if linked else frozenset({PUBLIC, PUBLIC_SUMMARY})
        shown = [
            {**e, "ref": f"{name}/{e['path']}", "readable": self.can_read(f"{name}/{e['path']}", peer)}
            for e in entries
            if e["visibility"] in allowed
        ]
        return {
            "owner": name,
            "viewer": peer,
            "linked": linked,
            "files": shown,
            "withheld": len(entries) - len(shown),
        }

    def can_read(self, path: str, handle: str) -> bool:
        """Whether that handle may read that path right now.

        Three things have to hold, and the order is the whole privacy model: the owner admits the
        file exists, the two folders are linked, and the owner has granted this path. `public` is
        the one case that needs no grant — it is published, and a grant for it would be theatre.
        """
        owner, rel = split_path(path)
        peer = check_handle(handle)
        entry = next((e for e in self._entries(owner) if e["path"] == rel), None)
        if entry is None or not rel:
            return False
        if owner == peer:
            return True
        if entry["visibility"] not in ADMITTED:
            return False
        if entry["visibility"] == PUBLIC:
            return True
        if not self.linked(owner, peer):
            return False
        return any(
            g["path"] == "" or g["path"] == rel or rel.startswith(g["path"].rstrip("/") + "/")
            for g in self.grants(owner, peer)
        )

    def read(self, path: str, handle: str) -> bytes:
        """The bytes, if that handle may have them. Raises rather than returning a hint otherwise."""
        owner, rel = split_path(path)
        if not self.can_read(path, handle):
            raise FolderError(f"{check_handle(handle)} may not read {rel!r} from {owner}")
        folder = self.folder(owner)
        assert folder is not None  # can_read found an entry in it
        return (folder / rel).read_bytes()


def _link_row(row: tuple) -> dict[str, Any]:
    """One `folder_links` row as JSON."""
    keys = ("id", "created_at", "state", "from_handle", "to_handle", "accepted_at", "accepted_by")
    out: dict[str, Any] = {}
    for key, value in zip(keys, row, strict=True):
        out[key] = value.isoformat() if isinstance(value, datetime) else value
    return out


# --- which implementation is in use -------------------------------------------------

_link: FolderLink | None = None
_why: str = ""


def configured() -> tuple[FolderLink, str]:
    """The folder link this hub is using, and why it is that one.

    `FOLDER_LINK=claudeconnect` asks for the real library. If it cannot be had — not installed, no
    key, nothing answering at claudeconnect.io — the hub says so and runs on `local` rather than
    failing. A demo that cannot book because a server in another country is down is a worse outcome
    than a demo that books against folders on this disk and says that is what it did.
    """
    global _link, _why
    if _link is not None:
        return _link, _why
    want = (config.FOLDER_LINK or "local").strip().lower()
    if want == "claudeconnect":
        try:
            from .cc_folders import open_cc  # local import: the adapter imports the library lazily too

            link, why = open_cc()
        except ImportError as err:  # no adapter in this build, which is still not a reason to fail
            link, why = None, f"no ClaudeConnect adapter here ({err})"
        if link is not None:
            _link, _why = link, why
            return _link, _why
        log.warning("folders: FOLDER_LINK=claudeconnect unavailable (%s); running on local folders", why)
        _link, _why = LocalFolderLink(), f"fell back to local: {why}"
        return _link, _why
    if want != "local":
        _link, _why = LocalFolderLink(), f"unknown FOLDER_LINK={want!r}, using local"
        log.warning("folders: %s", _why)
        return _link, _why
    _link, _why = LocalFolderLink(), "local folders"
    return _link, _why


def link() -> FolderLink:
    """The folder link in use."""
    return configured()[0]


def reset() -> None:
    """Forget which implementation was chosen, so a test or a config change can pick again."""
    global _link, _why
    _link, _why = None, ""


def status() -> dict[str, Any]:
    """What `/api/health` says about the folder link: which one, asked for, and why."""
    chosen, why = configured()
    return {
        "folder_link": chosen.kind,
        "requested": (config.FOLDER_LINK or "local").strip().lower(),
        "why": why,
        "root": str(getattr(chosen, "root", "")),
    }


# --- the calls the rest of the hub makes --------------------------------------------


def claim(handle: str) -> dict[str, Any]:
    """Take a handle and its folder on the configured link."""
    return link().claim(handle)


def request_link(from_handle: str, to_handle: str) -> dict[str, Any]:
    """Ask to link two folders on the configured link."""
    return link().request_link(from_handle, to_handle)


def accept_link(link_id: str, *, by: str = "") -> dict[str, Any]:
    """Accept a link on the configured link."""
    return link().accept_link(link_id, by=by)


def grant(path: str, to_handle: str) -> dict[str, Any]:
    """Grant a path on the configured link."""
    return link().grant(path, to_handle)


def can_read(path: str, handle: str) -> bool:
    """Whether a handle may read a path on the configured link."""
    return link().can_read(path, handle)


def files(handle: str) -> list[dict[str, Any]]:
    """A handle's own files on the configured link."""
    return link().files(handle)


def between(a: str, b: str) -> dict[str, Any] | None:
    """The link between two handles on the configured link, or None."""
    return link().between(a, b)


def linked(a: str, b: str) -> bool:
    """Whether two folders are established on the configured link."""
    return link().linked(a, b)


def manifest(owner: str, viewer: str) -> dict[str, Any]:
    """What one handle may see of another's folder on the configured link."""
    return link().manifest(owner, viewer)


def open_link(from_handle: str, to_handle: str, *, auto_accept: bool = False, by: str = "") -> dict[str, Any]:
    """Request a link and, when the other side's standing answer is yes, accept it in the same step.

    A published, freely connectable Card *is* a standing yes to being contacted — that is what
    publishing it means — so `hub.connect` auto-accepts for one. A Card that waits for its owner
    stays `requested` until the owner says yes, which is the same moment they confirm the
    introduction. The link is not the grant: an auto-accepted link still reads nothing without one.
    """
    row = request_link(from_handle, to_handle)
    if auto_accept and row["state"] != ESTABLISHED:
        return accept_link(row["id"], by=by or to_handle)
    return row
