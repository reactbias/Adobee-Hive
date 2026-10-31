"""The same folder link, against the real ClaudeConnect.

`folders.LocalFolderLink` is the seam's in-process implementation. This is the other one: the same
calls, but the state that decides access lives where ClaudeConnect's own server looks for it — an
`authz` file beside a `files/` directory, one pair per identity — so a link made here is a link the
real library enforces, and a `claudeconnect sync` on the other side sees it.

What was read out of `bstadt/cc_daemon` before writing this, because the design rests on it:

- **Identity is a string, and the string needs an `@`.** `server/routes/bot.py` claims any handle
  matching `^[a-z0-9_-]+$` and `server/auth.py` issues it the address `<handle>@moltbook.cc.bot`.
  Nothing in the friend or file path is human-specific. So *any two agents* can be the two ends of a
  link, which is the premise this module needed to be true — and a handle becomes an address here,
  because `server/authz.py` refuses a recipient with no `@` in it.
- **That same check is the `*` trap.** `server/authz.py:205` raises
  `AuthzParseError: Invalid user email: *` for the wildcard its own `SKILL.md` documents as
  supported, and it is worse than it sounds: `parse_authz` raises on the first bad line, so one `*`
  voids the whole file, `load_authz` then returns `None`, and *nobody* can read anything. We never
  write a wildcard. Grants name handles.
- **Friendship in the library is a blanket read.** `cli.add_friend_to_authz` gives a new friend `r`
  on `[/]` — the entire context directory — plus `rw` on the folder they share. That is one layer
  where this product needs two, so this module does not call it and writes the sections itself.
- **Per-path grants are native to that file format.** `Authz.can_read` finds the *most specific*
  section covering a path and denies implicitly when the asker has no rule in it; the library's own
  `tests/test_authz_permissions.py::test_exact_path_match` pins exactly the shape used here. So a
  `[/]` that does not name the peer, plus a `[/rates/2027-spring.md]` that does, *is* a link that
  carries no content and a grant that carries one file. The two layers are not bolted on.

The parsing rule is re-implemented rather than imported. It lives in the library's `server/`
package, which is not what `pip install claudeconnect` ships, and that package reads a pydantic
settings object at import: the library's own tests `exec()` the file with a mocked config to get at
it. Importing a FastAPI app with its own settings into this hub to answer "may this handle read this
path" would be a worse dependency than forty lines that match it line for line, and the matching
lines are marked.

**Nothing here is on the demo's critical path.** The library is imported lazily, the implementation
is chosen once, and every failure — not installed, no key, no answer from claudeconnect.io — comes
back as a reason instead of an exception, so `folders.configured()` falls back to local and
`/api/health` says why. A demo that cannot book because a server in another country is down is a
worse outcome than a demo that books against folders on this disk and says that is what it did.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import config, folders

log = logging.getLogger(__name__)

#: The address shape ClaudeConnect gives a claimed bot handle (`server/auth.py:161`).
BOT_DOMAIN = "moltbook.cc.bot"

#: `server/authz.py` wants this first, lower-case hex, and refuses the file without it. 64 hex
#: characters is an X25519 public key.
KEY_LINE = re.compile(r"^#\s*Public[-\s]Key:\s*([a-fA-F0-9]{64})\s*$")
SECTION = re.compile(r"^\[([^\]]+)\]$")
PERMISSION = re.compile(r"^([^=]+?)\s*=\s*([rw]*)\s*$")

#: Where the library keeps a pending friend request, named as `server/routes/friends.py` names it.
INBOX = "claudeconnect/with-claudeconnect-io"


class CcError(folders.FolderError):
    """Something the real ClaudeConnect could not be asked to do."""


# --- the file formats, as the library defines them ----------------------------------


def address(handle: str) -> str:
    """A handle as an identity ClaudeConnect accepts: `hotel-krafft@moltbook.cc.bot`.

    The address is required, not decorative. `server/authz.py:205` refuses a recipient with no `@`
    in it, and takes the rest of the file down with it.
    """
    name = folders.check_handle(handle)
    return name if "@" in name else f"{name}@{BOT_DOMAIN}"


def repo_name(identity: str) -> str:
    """An identity as the library writes it into a folder name (`server/routes/friends.py`)."""
    return identity.replace("@", "-").replace(".", "-").lower()


def with_section(peer: str) -> str:
    """The folder a pair shares, which is where the library puts a friend's conversations.

    An established link is this section and nothing else: the two agents may write to the folder
    they share, and to none of the owner's own files. It is `bilateral` in the Card vocabulary
    (documentation/cards/manifest-after-handshake.json) — the only thing a link opens by itself.
    """
    return f"/claudeconnect/with-{repo_name(address(peer))}"


def request_path(sender: str) -> str:
    """Where a pending friend request from this sender sits, relative to `files/`."""
    return f"{INBOX}/friend-request-{repo_name(address(sender))}.md"


def request_body(sender: str, key: str) -> str:
    """A friend request in the library's own format, so its client can read one we wrote.

    `cli.auto_accept_reciprocal_requests` looks for the sender with `**From**: <\\S+@\\S+>` and the
    key with `**Public-Key**`, and `server/routes/friends.py` writes both. An address again, which
    is the third place the same assumption shows up.
    """
    return (
        f"# Friend Request from {sender}\n\n"
        f"**From**: {sender}\n"
        f"**Date**: {folders._now().isoformat()}Z\n\n"
        f"**Public-Key**: {key}\n\n"
        "---\n\nTo accept this friend request, run:\n```\n"
        f"claudeconnect accept-friend {sender}\n```\n"
    )


@dataclass(frozen=True)
class Rule:
    """One line of an authz file: who, where, and what they may do there."""

    path: str
    user: str
    read: bool
    write: bool


def parse_authz(text: str) -> tuple[str, list[Rule]]:
    """An authz file as its public key and its rules, by the library's own rules.

    Matches `server/authz.py::parse_authz`, refusals included: the public key comes first, a
    permission outside a section is an error, and a recipient with no `@` is an error — which is the
    line that makes `*` unusable.
    """
    key, rules, section = "", [], ""
    for number, raw in enumerate(text.strip().splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if not key:
            found = KEY_LINE.match(line)
            if found:
                key = found.group(1).lower()
                continue
            if line.startswith("#"):
                continue
            raise CcError(f"authz line {number}: the public key must come first, got {line[:50]!r}")
        if line.startswith("#"):
            continue
        header = SECTION.match(line)
        if header:
            section = header.group(1)
            if not section.startswith("/"):
                raise CcError(f"authz line {number}: a section path starts with /, got [{section}]")
            continue
        perm = PERMISSION.match(line)
        if not perm:
            raise CcError(f"authz line {number}: unrecognised line {line!r}")
        if not section:
            raise CcError(f"authz line {number}: a permission outside a section: {line!r}")
        user, flags = perm.group(1).strip(), perm.group(2).lower()
        if "@" not in user:
            raise CcError(f"authz line {number}: invalid user email: {user}")
        rules.append(Rule(section, user, "r" in flags, "w" in flags))
    if not key:
        raise CcError("authz has no public key; the file must start with '# Public Key: <64 hex>'")
    return key, rules


def covers(section: str, path: str) -> bool:
    """Whether a section governs a path (`server/authz.py::_path_matches`)."""
    return path == section or path.startswith(section.rstrip("/") + "/") or section == "/"


def can_read_authz(rules: list[Rule], user: str, path: str) -> bool:
    """The library's rule, kept exactly: the most specific section wins, and silence is a no.

    The subtlety worth keeping is that the most specific section is chosen over *all* rules, not
    over the asking user's rules. A `[/rooms]` naming somebody else denies this user even though
    `[/]` would have allowed them — implicit deny, their issue #82. It is also why a grant is
    written as its own section instead of being appended to `[/]`.
    """
    if not path.startswith("/"):
        path = "/" + path
    sections = {r.path for r in rules if covers(r.path, path)}
    if not sections:
        return False
    deepest = max(sections, key=len)
    return any(r.read for r in rules if r.path == deepest and r.user == user)


def writable(section: str) -> bool:
    """Whether a peer named in this section may write there, as the library's convention has it.

    One section is writable and no other: the folder a pair shares, because the whole point of it is
    that the peer pushes their side of the conversation into it (`cli.add_friend_to_authz` gives a
    friend `rw` there and the server lets them PUT into it). A grant on the owner's own content is
    read-only — it is the owner showing a peer a file, not handing it over.
    """
    return section.startswith("/claudeconnect/with-")


def authz_text(key: str, owner: str, sections: dict[str, list[str]]) -> str:
    """An authz file: the owner everywhere, and one section per thing that was granted.

    `[/]` names the owner and nobody else, so a link on its own opens nothing. Every grant is its
    own section, which the most-specific-section rule reads as permission for that path alone. No
    wildcards, ever — see the module docstring.

    A peer already named at `[/]` by the library's own `add_friend_to_authz` keeps that read, since
    this hub is not in the business of quietly revoking what somebody granted elsewhere; it is
    written back as `r`, never `rw`.
    """
    out = [f"# Public Key: {key}", ""]
    root = sorted(set(sections.get("/", [])))
    out += ["[/]", f"{owner} = rw", *[f"{user} = r" for user in root if user != owner], ""]
    for path in sorted(p for p in sections if p != "/"):
        flags = "rw" if writable(path) else "r"
        users = sorted(set(sections[path]))
        out += [f"[{path}]", f"{owner} = rw", *[f"{user} = {flags}" for user in users if user != owner], ""]
    return "\n".join(out)


# --- the real library, if it is here at all ------------------------------------------


def library() -> tuple[Any, str]:
    """The ClaudeConnect package, or None and the reason it is not usable.

    A submodule is imported, not the top-level name: a bare `import claudeconnect` succeeds as an
    empty namespace package whenever the process happens to be running next to a clone of the repo,
    which is exactly the situation this hub is developed in. That false positive would be reported
    as "the real library is in use" on stage.
    """
    try:
        from claudeconnect import encryption  # imported here, not at module load
    except Exception as err:  # ImportError, and whatever the library's own imports raise
        return None, f"claudeconnect is not installed here ({type(err).__name__}: {err})"
    if not getattr(encryption, "is_encryption_available", lambda: False)():
        return None, "claudeconnect is installed without its cryptography extra, so it cannot hold a key"
    return encryption, "claudeconnect is installed"


class CcFolderLink(folders.LocalFolderLink):
    """Folder links kept in ClaudeConnect's own layout: `<root>/<address>/{authz,files/}`.

    The hub's bookkeeping — which link has which id — stays in DuckDB, inherited from
    `LocalFolderLink`. The state that *decides access* is the authz file and the friend-request
    file, because those are what the library and its server enforce. When the two disagree the authz
    file wins: `linked()` and `can_read()` read it, never the table.
    """

    kind = "claudeconnect"

    def __init__(self, root: Path, keys: Any) -> None:
        super().__init__(root)
        self.keys = keys

    # --- where things live -----------------------------------------------------------

    def home(self, handle: str) -> Path:
        """This handle's identity directory, the one the server's `get_user_dir` would return."""
        return self.root / address(handle).replace("/", "_")

    def folder(self, handle: str) -> Path | None:
        """Where this handle's files are: `files/` under its identity directory, or None."""
        files = self.home(handle) / "files"
        return files if files.is_dir() else None

    def authz_path(self, handle: str) -> Path:
        """This handle's authz file, which is the thing the library actually enforces."""
        return self.home(handle) / "authz"

    def public_key(self, handle: str) -> str:
        """This handle's X25519 public key as hex, generating one on first use.

        The keys are the library's own (`encryption.generate_keypair`), kept beside the identity
        rather than in `~/.claude-connect`, because a hub is a server and a server does not have a
        home directory it should be writing keys into.
        """
        who = address(handle)
        keys_dir = self.home(handle) / "keys"
        keys_dir.mkdir(parents=True, exist_ok=True)
        if not (keys_dir / "public.key").exists():
            self.keys.generate_keypair(who, keys_dir=keys_dir)
        return self.keys.load_public_key(who, keys_dir=keys_dir).hex()

    # --- the authz file as this module reads and writes it ---------------------------

    def read_authz(self, handle: str) -> tuple[str, list[Rule]]:
        """This handle's authz file, parsed. A missing file is an empty one with a fresh key."""
        path = self.authz_path(handle)
        if not path.is_file():
            return self.public_key(handle), []
        return parse_authz(path.read_text(encoding="utf-8"))

    def write_authz(self, handle: str, sections: dict[str, list[str]]) -> None:
        """Rewrite this handle's authz file from the sections given, keeping its key."""
        key, _ = self.read_authz(handle)
        path = self.authz_path(handle)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(authz_text(key, address(handle), sections), encoding="utf-8")

    def sections(self, handle: str) -> dict[str, list[str]]:
        """This handle's authz as a plain map of section to the users named in it."""
        _, rules = self.read_authz(handle)
        out: dict[str, list[str]] = {}
        for rule in rules:
            out.setdefault(rule.path, []).append(rule.user)
        return out

    # --- the protocol ----------------------------------------------------------------

    def claim(self, handle: str) -> dict[str, Any]:
        """Take a handle: its identity directory, its keypair, and an authz file naming only it."""
        row = super().claim(handle)
        (self.home(handle) / "files").mkdir(parents=True, exist_ok=True)
        key = self.public_key(handle)
        if not self.authz_path(handle).is_file():
            self.write_authz(handle, {})
        return {**row, "address": address(handle), "root": str(self.folder(handle) or ""), "public_key": key}

    def request_link(self, from_handle: str, to_handle: str) -> dict[str, Any]:
        """Ask to link, by writing the friend request where the library's client looks for it."""
        row = super().request_link(from_handle, to_handle)
        self.claim(from_handle)
        self.claim(to_handle)
        if not self.linked(from_handle, to_handle):
            inbox = (self.folder(to_handle) or (self.home(to_handle) / "files")) / request_path(from_handle)
            inbox.parent.mkdir(parents=True, exist_ok=True)
            inbox.write_text(request_body(address(from_handle), self.public_key(from_handle)), encoding="utf-8")
        return row

    def accept_link(self, link_id: str, *, by: str = "") -> dict[str, Any]:
        """Accept it on both sides, as the library's own flow does, and clear the request file.

        Both sides, because friendship there is reciprocal: each writes the other into its own
        authz. What it grants is only the folder the pair shares — never the owner's files, which
        still wait for a grant.
        """
        row = super().accept_link(link_id, by=by)
        one, two = row["from_handle"], row["to_handle"]
        for owner, peer in ((one, two), (two, one)):
            sections = self.sections(owner)
            sections.setdefault(with_section(peer), [])
            if address(peer) not in sections[with_section(peer)]:
                sections[with_section(peer)].append(address(peer))
            self.write_authz(owner, sections)
            stale = (self.folder(owner) or (self.home(owner) / "files")) / request_path(peer)
            stale.unlink(missing_ok=True)
        return row

    def linked(self, a: str, b: str) -> bool:
        """Whether both authz files say so. The table is bookkeeping; this is the enforced answer.

        Both, because friendship in the library is reciprocal — each side writes the other into its
        own file — and because the half that matters is the one belonging to whoever is being read.
        A file that cannot be parsed is not a yes: `load_authz` returns `None` for one, and `None`
        means no access to anybody, so agreeing with it here keeps the two implementations honest
        about the same file.
        """
        try:
            return address(b) in self.sections(a).get(with_section(b), []) and address(a) in self.sections(b).get(
                with_section(a), []
            )
        except folders.FolderError as err:
            log.warning("cc_folders: cannot read an authz file for %s/%s (%s)", a, b, err)
            return False

    def grant(self, path: str, to_handle: str) -> dict[str, Any]:
        """Write the grant as its own authz section, which is how the library reads a per-path right."""
        owner, rel = folders.split_path(path)
        row = super().grant(path, to_handle)  # does the admitting and the link check, and records it
        sections = self.sections(owner)
        section = "/" + rel if rel else "/"
        sections.setdefault(section, [])
        if address(to_handle) not in sections[section]:
            sections[section].append(address(to_handle))
        self.write_authz(owner, sections)
        return {**row, "authz": section, "to_address": address(to_handle)}

    def can_read(self, path: str, handle: str) -> bool:
        """The owner's visibility first, then the library's own authz rule. Both have to say yes.

        Two gates, because they answer different questions. Visibility is what the owner admits
        exists at all, and nothing — not a grant, not a link, not an authz file somebody edited by
        hand — makes a `hidden` or `private` path readable. The authz rule is who was let in.
        """
        owner, rel = folders.split_path(path)
        entry = next((e for e in self._entries(owner) if e["path"] == rel), None)
        if entry is None or not rel:
            return False
        if owner == folders.check_handle(handle):
            return True
        if entry["visibility"] not in folders.ADMITTED:
            return False
        if entry["visibility"] == folders.PUBLIC:
            return True
        if not self.linked(owner, handle):
            return False
        try:
            _, rules = self.read_authz(owner)
        except folders.FolderError as err:
            log.warning("cc_folders: %s has an authz file that cannot be read (%s)", owner, err)
            return False
        return can_read_authz(rules, address(handle), "/" + rel)


def open_cc() -> tuple[CcFolderLink | None, str]:
    """The real adapter, or None and the reason the hub should stay on local folders.

    Reasons, in the order they actually happen: the library is not installed, it is installed
    without the cryptography extra, or its root cannot be written to. None of them raises. The hub
    comes up either way and `/api/health` carries the reason.
    """
    keys, why = library()
    if keys is None:
        return None, why
    root = config.CC_ROOT
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".writable"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as err:
        return None, f"{root} cannot be written to ({err})"
    return CcFolderLink(root, keys), f"{why}; folders under {root}"
