"""The ClaudeConnect adapter: the same folder link, in the library's own file formats.

Two kinds of test here, and the split is deliberate.

Most of it is the formats, which are pure functions and run everywhere: the authz file this hub
writes, the rule the library applies to it, the address a handle becomes, and the wildcard that
cannot be written. Several cases are lifted from the library's own
`tests/test_authz_permissions.py`, so a drift in our reading of its rule shows up here.

The rest needs a key, and is run against the real library when it is importable — it is an optional
dependency, so in CI it is not — or against a keypair this test makes itself with `cryptography`,
which the backend depends on anyway. What is stood in for is key *storage*, never the access rule.

    PYTHONPATH=../../../claudeconnect/src pytest tests/test_cc_folders.py -q   # with the real library
"""

from __future__ import annotations

import pytest

from app import cc_folders, config, db, folders

#: The published placeholder the library's own authz tests put in that header position, 64 characters
#: of repeated hex. Named and written to read as what it is: gitleaks fired twice on the earlier
#: spelling, and it was right to — an identifier like that beside a value like this is its whole job.
PUBLIC_HEX = "0123456789abcdef" * 4  # gitleaks:allow


@pytest.fixture(autouse=True)
def clean_slate(client):
    folders.init()
    with db.write() as cur:
        cur.execute("DELETE FROM folder_links")
        cur.execute("DELETE FROM folder_grants")
        cur.execute("DELETE FROM folder_handles")
    folders.reset()
    yield
    folders.reset()


class Keys:
    """A stand-in for `claudeconnect.encryption`'s key storage, and only that.

    It generates a real X25519 keypair with `cryptography` — the same primitive, the same 32 bytes —
    and puts it where the library would. The access rule is never stood in for: that is
    `cc_folders.can_read_authz`, which matches `server/authz.py` and is tested on its own above.
    """

    def generate_keypair(self, email, keys_dir=None):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

        private = X25519PrivateKey.generate()
        raw = private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )
        keys_dir.mkdir(parents=True, exist_ok=True)
        (keys_dir / "public.key").write_bytes(raw)
        return b"", raw

    def load_public_key(self, email, keys_dir=None):
        return (keys_dir / "public.key").read_bytes()

    def is_encryption_available(self):
        return True


@pytest.fixture
def cc(tmp_path, monkeypatch):
    """An adapter over a throwaway root, with the real library's keys when they can be had."""
    keys, why = cc_folders.library()
    link = cc_folders.CcFolderLink(tmp_path, keys if keys is not None else Keys())
    monkeypatch.setattr("app.folders._link", link)
    monkeypatch.setattr("app.folders._why", why)
    return link


# ---------------------------------------------------------------- identity


def test_a_handle_becomes_an_address_because_authz_demands_one():
    """`server/authz.py:205` refuses a recipient with no `@`, and voids the whole file with it."""
    assert cc_folders.address("hotel-krafft") == "hotel-krafft@moltbook.cc.bot"
    assert cc_folders.address("mara@example.com") == "mara@example.com", "an address stays itself"
    assert "@" in cc_folders.address("agent_42")


def test_an_identity_becomes_a_folder_name_the_library_would_recognise():
    assert cc_folders.repo_name("mara@example.com") == "mara-example-com"
    assert cc_folders.with_section("hotel-krafft") == "/claudeconnect/with-hotel-krafft-moltbook-cc-bot"


# ---------------------------------------------------------------- the authz file


def test_the_file_this_hub_writes_names_the_owner_at_the_root_and_nobody_else():
    """A link opens nothing on its own. That is a property of the file, so it is tested as one."""
    text = cc_folders.authz_text(PUBLIC_HEX, "hotel@moltbook.cc.bot", {})
    key, rules = cc_folders.parse_authz(text)

    assert key == PUBLIC_HEX
    assert [(r.path, r.user, r.read, r.write) for r in rules] == [("/", "hotel@moltbook.cc.bot", True, True)]


def test_a_grant_is_its_own_section_which_is_how_the_library_reads_a_per_path_right():
    """Lifted from the library's own test_exact_path_match: `[/]` without the peer, `[/file]` with."""
    text = cc_folders.authz_text(PUBLIC_HEX, "hotel@moltbook.cc.bot", {"/rates/2027-spring.md": ["mara@example.com"]})
    _, rules = cc_folders.parse_authz(text)

    assert cc_folders.can_read_authz(rules, "mara@example.com", "/rates/2027-spring.md")
    assert not cc_folders.can_read_authz(rules, "mara@example.com", "/rates/2028-spring.md")
    assert not cc_folders.can_read_authz(rules, "mara@example.com", "/about.md")
    assert cc_folders.can_read_authz(rules, "hotel@moltbook.cc.bot", "/anything/at/all.md")


def test_a_grant_shows_a_file_and_does_not_hand_it_over():
    """Read, not write. The one writable section is the folder the pair shares, because that is what
    the peer pushes their side of the conversation into."""
    text = cc_folders.authz_text(
        PUBLIC_HEX,
        "hotel@moltbook.cc.bot",
        {"/rates/2027-spring.md": ["mara@example.com"], "/claudeconnect/with-mara-example-com": ["mara@example.com"]},
    )
    _, rules = cc_folders.parse_authz(text)
    granted = {(r.path, r.read, r.write) for r in rules if r.user == "mara@example.com"}

    assert ("/rates/2027-spring.md", True, False) in granted, "a grant is read-only"
    assert ("/claudeconnect/with-mara-example-com", True, True) in granted


def test_the_most_specific_section_wins_even_when_it_denies():
    """The library's issue #82: a child section that omits a user denies them, whatever `[/]` says."""
    _, rules = cc_folders.parse_authz(
        f"# Public Key: {PUBLIC_HEX}\n\n[/]\nowner@example.com = rw\npeer@example.com = r\n\n"
        "[/relationships]\nowner@example.com = rw\n"
    )
    assert cc_folders.can_read_authz(rules, "peer@example.com", "/notes/todo.md")
    assert not cc_folders.can_read_authz(rules, "peer@example.com", "/relationships/family.md")
    assert cc_folders.can_read_authz(rules, "owner@example.com", "/relationships/family.md")


def test_a_path_no_section_covers_is_a_no():
    assert not cc_folders.can_read_authz([], "peer@example.com", "/anything.md")


def test_the_wildcard_the_skill_documents_cannot_be_written_or_read():
    """`SKILL.md` documents `* = rw`. `server/authz.py:205` refuses it — and takes the file with it.

    So the trap is not that a wildcard fails to work. It is that one wildcard line voids the whole
    authz file, `load_authz` returns None, and *nobody* can read anything. This hub never writes one,
    and refuses to read one, in the same words the library uses.
    """
    with pytest.raises(cc_folders.CcError, match="invalid user email: \\*"):
        cc_folders.parse_authz(f"# Public Key: {PUBLIC_HEX}\n\n[/claudeconnect/with-claudeconnect-io]\n* = rw\n")

    written = cc_folders.authz_text(PUBLIC_HEX, "hotel@moltbook.cc.bot", {"/x.md": ["mara@example.com"]})
    assert "*" not in written


def test_a_file_without_a_public_key_is_refused_as_the_library_refuses_it():
    for bad, why in [
        ("[/]\nowner@example.com = rw\n", "public key must come first"),
        (f"# Public Key: {PUBLIC_HEX}\nowner@example.com = rw\n", "outside a section"),
        (f"# Public Key: {PUBLIC_HEX}\n[relationships]\nowner@example.com = rw\n", "starts with /"),
        ("# Public Key: nothex\n[/]\nowner@example.com = rw\n", "public key must come first"),
    ]:
        with pytest.raises(cc_folders.CcError, match=why):
            cc_folders.parse_authz(bad)


# ---------------------------------------------------------------- the adapter


def test_the_library_is_not_assumed_to_be_here(monkeypatch):
    """A bare `import claudeconnect` succeeds as an empty namespace package whenever this hub runs
    next to a clone of the repo — which is how it is developed. Reporting that as "the real library
    is in use" on stage is the one answer this must never give."""
    import sys
    import types

    monkeypatch.setitem(sys.modules, "claudeconnect", types.ModuleType("claudeconnect"))
    monkeypatch.delitem(sys.modules, "claudeconnect.encryption", raising=False)
    found, why = cc_folders.library()
    assert found is None
    assert "not installed" in why


def test_a_library_without_its_crypto_extra_is_not_usable(monkeypatch):
    import sys
    import types

    pkg, enc = types.ModuleType("claudeconnect"), types.ModuleType("claudeconnect.encryption")
    enc.is_encryption_available = lambda: False
    pkg.encryption = enc
    monkeypatch.setitem(sys.modules, "claudeconnect", pkg)
    monkeypatch.setitem(sys.modules, "claudeconnect.encryption", enc)

    found, why = cc_folders.library()
    assert found is None and "cannot hold a key" in why


def test_claiming_a_handle_lays_out_what_the_librarys_own_server_expects(cc):
    out = cc.claim("hotel-krafft")

    assert out["address"] == "hotel-krafft@moltbook.cc.bot"
    assert (cc.home("hotel-krafft") / "files").is_dir()
    assert len(out["public_key"]) == 64, "an X25519 public key, as the authz header wants it"
    key, rules = cc.read_authz("hotel-krafft")
    assert key == out["public_key"]
    assert [r.user for r in rules] == ["hotel-krafft@moltbook.cc.bot"], "the owner, and nobody else"


def test_asking_to_link_writes_the_friend_request_where_the_librarys_client_looks(cc):
    cc.request_link("mara@example.com", "hotel-krafft")

    pending = cc.home("hotel-krafft") / "files" / cc_folders.request_path("mara@example.com")
    assert pending.is_file()
    body = pending.read_text(encoding="utf-8")
    assert "**From**: mara@example.com" in body, "the client's own regex wants an address here"
    assert "**Public-Key**:" in body
    assert not cc.linked("mara@example.com", "hotel-krafft"), "asking is not linking"


def test_accepting_writes_both_sides_and_clears_the_request(cc):
    link = cc.request_link("mara@example.com", "hotel-krafft")
    cc.accept_link(link["id"])

    assert cc.linked("mara@example.com", "hotel-krafft")
    assert cc.linked("hotel-krafft", "mara@example.com")
    assert not (cc.home("hotel-krafft") / "files" / cc_folders.request_path("mara@example.com")).exists()

    # And what it granted is the folder the pair shares, not one file of the hotel's.
    _, rules = cc.read_authz("hotel-krafft")
    granted = {r.path for r in rules if r.user == "mara@example.com"}
    assert granted == {"/claudeconnect/with-mara-example-com"}


def test_a_grant_becomes_a_section_the_library_would_enforce(cc):
    (cc.home("hotel-krafft") / "files" / "rates").mkdir(parents=True)
    (cc.home("hotel-krafft") / "files" / "rates" / "2027-spring.md").write_text("CHF 190\n", encoding="utf-8")
    (cc.home("hotel-krafft") / "files" / "about.md").write_text("# Krafft\n", encoding="utf-8")
    cc.accept_link(cc.request_link("mara@example.com", "hotel-krafft")["id"])

    assert not cc.can_read("hotel-krafft/rates/2027-spring.md", "mara@example.com")
    out = cc.grant("hotel-krafft/rates/2027-spring.md", "mara@example.com")

    assert out["authz"] == "/rates/2027-spring.md" and out["to_address"] == "mara@example.com"
    assert cc.can_read("hotel-krafft/rates/2027-spring.md", "mara@example.com")
    assert not cc.can_read("hotel-krafft/about.md", "mara@example.com"), "one file, not the folder"

    _, rules = cc.read_authz("hotel-krafft")
    assert cc_folders.can_read_authz(rules, "mara@example.com", "/rates/2027-spring.md")


def test_the_owners_visibility_overrules_the_authz_file(cc):
    """Two gates, answering different questions. Nothing in an authz file makes a hidden file
    readable — not a grant, not a link, not somebody editing the file by hand."""
    files = cc.home("hotel-krafft") / "files"
    files.mkdir(parents=True)
    (files / "takings.md").write_text("Not yours.\n", encoding="utf-8")
    (files / folders.MARKER).write_text("takings.md = hidden\n", encoding="utf-8")
    cc.accept_link(cc.request_link("mara@example.com", "hotel-krafft")["id"])

    with pytest.raises(folders.FolderError, match="admits no file"):
        cc.grant("hotel-krafft/takings.md", "mara@example.com")

    # Even written straight into the file the library enforces, the owner's own word wins here.
    sections = cc.sections("hotel-krafft")
    sections["/takings.md"] = ["mara@example.com"]
    cc.write_authz("hotel-krafft", sections)
    assert not cc.can_read("hotel-krafft/takings.md", "mara@example.com")


def test_a_published_file_needs_no_grant_and_an_unlinked_stranger_gets_nothing_else(cc):
    files = cc.home("hotel-krafft") / "files"
    files.mkdir(parents=True)
    (files / "about.md").write_text("# Krafft\n", encoding="utf-8")
    (files / "rooms.md").write_text("Rear room\n", encoding="utf-8")
    (files / folders.MARKER).write_text("about.md = public\n", encoding="utf-8")

    assert cc.can_read("hotel-krafft/about.md", "a-stranger"), "published is published"
    assert not cc.can_read("hotel-krafft/rooms.md", "a-stranger")


def test_a_malformed_authz_file_is_not_a_yes(cc):
    cc.accept_link(cc.request_link("mara@example.com", "hotel-krafft")["id"])
    cc.authz_path("hotel-krafft").write_text("this is not an authz file\n", encoding="utf-8")

    assert not cc.linked("mara@example.com", "hotel-krafft")
    assert not cc.can_read("hotel-krafft/about.md", "mara@example.com")


# ---------------------------------------------------------------- choosing, and falling back


def test_asking_for_claudeconnect_without_the_library_runs_on_local_folders(monkeypatch):
    """The rule for the whole adapter: a missing key or an unreachable claudeconnect.io cannot break
    the demo. It falls back, and says why."""
    monkeypatch.setattr("app.config.FOLDER_LINK", "claudeconnect")
    monkeypatch.setattr(cc_folders, "library", lambda: (None, "claudeconnect is not installed here (test)"))
    folders.reset()

    status = folders.status()
    assert status["folder_link"] == "local"
    assert status["requested"] == "claudeconnect"
    assert "fell back to local" in status["why"] and "not installed" in status["why"]


def test_a_root_it_cannot_write_to_falls_back_too(monkeypatch, tmp_path):
    monkeypatch.setattr(cc_folders, "library", lambda: (Keys(), "claudeconnect is installed"))
    monkeypatch.setattr(config, "CC_ROOT", tmp_path / "nope" / "deeper")
    (tmp_path / "nope").write_text("a file where a directory should be\n", encoding="utf-8")

    link, why = cc_folders.open_cc()
    assert link is None and "cannot be written to" in why


def test_the_adapter_is_the_same_protocol(monkeypatch, tmp_path):
    """Whatever is behind it, the hub only ever sees the six calls."""
    monkeypatch.setattr(cc_folders, "library", lambda: (Keys(), "claudeconnect is installed"))
    monkeypatch.setattr(config, "CC_ROOT", tmp_path)
    monkeypatch.setattr("app.config.FOLDER_LINK", "claudeconnect")
    folders.reset()

    assert isinstance(folders.link(), folders.FolderLink)
    assert folders.status()["folder_link"] == "claudeconnect"
    link = folders.request_link("mara@example.com", "hotel-krafft")
    folders.accept_link(link["id"])
    assert folders.linked("mara@example.com", "hotel-krafft")


@pytest.mark.skipif(cc_folders.library()[0] is None, reason="claudeconnect is an optional dependency")
def test_the_real_library_holds_the_key_when_it_is_installed(cc):
    """Run with the library importable, this is the adapter end to end on its own keys."""
    out = cc.claim("hotel-krafft")
    assert len(out["public_key"]) == 64
    assert (cc.home("hotel-krafft") / "keys" / "private.key").exists(), "the library's own key storage"
    cc.accept_link(cc.request_link("mara@example.com", "hotel-krafft")["id"])
    assert cc.linked("mara@example.com", "hotel-krafft")
