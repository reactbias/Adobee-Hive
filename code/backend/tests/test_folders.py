"""The folder link: two agents connecting their folders, and what that does and does not open.

The product's claim is that the public index gets you to a candidate and the folders then connect
and negotiate on the real contents. These tests pin the half of that which has to be true before a
booking is allowed to exist: a link is between two handles and carries nothing, a grant is per path
and is the only thing that makes bytes readable, and a file the owner never admitted is not named,
not granted and not read — including in the refusal.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import db, folders

ROOT = Path(__file__).resolve().parents[3]
VAULTS = ROOT / "testdata" / "vaults"


@pytest.fixture(autouse=True)
def clean_slate(client):
    """Links and grants are per test; the tables are append-only in life, not in the suite."""
    folders.init()
    with db.write() as cur:
        cur.execute("DELETE FROM folder_links")
        cur.execute("DELETE FROM folder_grants")
        cur.execute("DELETE FROM folder_handles")
    folders.reset()
    yield
    folders.reset()


@pytest.fixture
def two(tmp_path) -> folders.LocalFolderLink:
    """Two folders on disk: a hotel that marks its files, and a traveller who holds none."""
    hotel = tmp_path / "hotel-rheinblick"
    (hotel / "rooms").mkdir(parents=True)
    (hotel / "claudeconnect").mkdir()
    (hotel / "notes").mkdir()
    (hotel / "about.md").write_text("# Rheinblick\nA quiet house by the river.\n", encoding="utf-8")
    (hotel / "rooms" / "012-rhine-quiet.md").write_text("Rear room, 2 guests, CHF 180.\n", encoding="utf-8")
    (hotel / "rooms" / "rates-2027.md").write_text("Spring: CHF 190.\n", encoding="utf-8")
    (hotel / "claudeconnect" / "tx-verband.md").write_text("Transcript with the Verband.\n", encoding="utf-8")
    (hotel / "notes" / "takings.md").write_text("Not yours.\n", encoding="utf-8")
    (hotel / folders.MARKER).write_text(
        "\n".join(
            [
                "# what the house offers, and to whom",
                "about.md = public",
                "rooms/*.md = public-summary",
                "claudeconnect/** = shared",
                "notes/takings.md = hidden",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "mara@example.com").mkdir()  # a handle with a folder but nothing in it
    return folders.LocalFolderLink(tmp_path)


# ---------------------------------------------------------------- handles


def test_a_handle_can_be_an_entity_id_or_an_address(two):
    """ClaudeConnect gives a claimed bot handle the address `<handle>@moltbook.cc.bot`, so both shapes are one
    kind of thing to it, and both have to be legal here."""
    assert two.claim("hotel-rheinblick")["handle"] == "hotel-rheinblick"
    assert two.claim("mara@example.com")["handle"] == "mara@example.com"
    assert two.claim("agent_42")["handle"] == "agent_42"


def test_a_handle_that_could_be_a_path_is_refused():
    """A handle becomes a folder name, so `../` in one would read somebody else's vault."""
    for bad in ["../secrets", "a/b", "", "  ", "Robert'); DROP TABLE folder_links;--"]:
        with pytest.raises(folders.FolderError):
            folders.check_handle(bad)


def test_claiming_twice_is_the_same_claim(two):
    first, second = two.claim("hotel-rheinblick"), two.claim("hotel-rheinblick")
    assert first == second
    with db.cursor() as cur:
        assert cur.execute("SELECT count(*) FROM folder_handles").fetchone()[0] == 1


def test_a_handle_with_no_folder_is_still_a_party_to_a_link(two):
    """A traveller holds no files. That is not a reason they cannot link and be linked to."""
    assert two.claim("stranger")["root"] == ""
    assert two.files("stranger") == []
    link = two.request_link("stranger", "hotel-rheinblick")
    assert link["state"] == folders.REQUESTED


# ---------------------------------------------------------------- the link


def test_a_link_starts_requested_and_is_established_only_when_the_other_side_accepts(two):
    link = two.request_link("mara@example.com", "hotel-rheinblick")
    assert link["state"] == folders.REQUESTED
    assert not two.linked("mara@example.com", "hotel-rheinblick")

    accepted = two.accept_link(link["id"])
    assert accepted["state"] == folders.ESTABLISHED
    assert accepted["accepted_by"] == "hotel-rheinblick"
    assert two.linked("mara@example.com", "hotel-rheinblick")
    assert two.linked("hotel-rheinblick", "mara@example.com"), "a link is not directional once it holds"


def test_asking_twice_does_not_make_a_second_link(two):
    """Two rows for one pair of agents is two answers to 'are these linked?' and only one can be right."""
    first = two.request_link("mara@example.com", "hotel-rheinblick")
    assert two.request_link("mara@example.com", "hotel-rheinblick")["id"] == first["id"]
    assert two.request_link("hotel-rheinblick", "mara@example.com")["id"] == first["id"]


def test_accepting_an_established_link_again_is_not_an_error(two):
    """The owner's yes can arrive twice — a retry, a second confirm — and the second must not fail on stage."""
    link = two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])
    assert two.accept_link(link["id"])["state"] == folders.ESTABLISHED


def test_an_agent_cannot_link_to_itself(two):
    with pytest.raises(folders.FolderError, match="two different agents"):
        two.request_link("hotel-rheinblick", "hotel-rheinblick")


def test_an_unknown_link_id_is_a_readable_refusal(two):
    with pytest.raises(folders.FolderError, match="no folder link"):
        two.accept_link("fl-nope")


def test_the_link_alone_opens_no_contents(two):
    """The whole design in one test: linked, and still not a byte of anything but what was published."""
    two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])

    assert two.can_read("hotel-rheinblick/about.md", "mara@example.com"), "published is published"
    assert not two.can_read("hotel-rheinblick/rooms/012-rhine-quiet.md", "mara@example.com")
    assert not two.can_read("hotel-rheinblick/claudeconnect/tx-verband.md", "mara@example.com")


# ---------------------------------------------------------------- grants


def test_a_grant_is_what_makes_a_file_readable(two):
    two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])
    path = "hotel-rheinblick/rooms/012-rhine-quiet.md"
    assert not two.can_read(path, "mara@example.com")

    two.grant(path, "mara@example.com")
    assert two.can_read(path, "mara@example.com")
    assert b"CHF 180" in two.read(path, "mara@example.com")


def test_a_folder_grant_covers_what_is_under_it_and_nothing_else(two):
    two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])
    two.grant("hotel-rheinblick/rooms", "mara@example.com")

    assert two.can_read("hotel-rheinblick/rooms/012-rhine-quiet.md", "mara@example.com")
    assert two.can_read("hotel-rheinblick/rooms/rates-2027.md", "mara@example.com")
    assert not two.can_read("hotel-rheinblick/claudeconnect/tx-verband.md", "mara@example.com")


def test_a_grant_without_a_link_is_refused(two):
    """Granting first and linking later would make the link decorative."""
    with pytest.raises(folders.FolderError, match="no established folder link"):
        two.grant("hotel-rheinblick/about.md", "mara@example.com")

    two.request_link("mara@example.com", "hotel-rheinblick")  # asked for, not accepted
    with pytest.raises(folders.FolderError, match="no established folder link"):
        two.grant("hotel-rheinblick/about.md", "mara@example.com")


def test_a_grant_on_a_file_the_owner_never_admitted_is_refused_in_the_same_words_as_a_missing_one(two):
    """'You may not read that' and 'there is no such thing' have to be indistinguishable, or the refusal leaks."""
    two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])

    with pytest.raises(folders.FolderError) as hidden:
        two.grant("hotel-rheinblick/notes/takings.md", "mara@example.com")
    with pytest.raises(folders.FolderError) as absent:
        two.grant("hotel-rheinblick/notes/no-such-file.md", "mara@example.com")
    assert str(hidden.value) == str(absent.value).replace("no-such-file.md", "takings.md")
    assert "takings" not in str(absent.value)


def test_a_grant_is_not_doubled(two):
    two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])
    first = two.grant("hotel-rheinblick/about.md", "mara@example.com")
    assert two.grant("hotel-rheinblick/about.md", "mara@example.com")["id"] == first["id"]
    assert len(two.grants("hotel-rheinblick")) == 1


def test_a_grant_to_one_agent_is_not_a_grant_to_another(two):
    two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])
    two.accept_link(two.request_link("someone-else", "hotel-rheinblick")["id"])
    two.grant("hotel-rheinblick/rooms/012-rhine-quiet.md", "mara@example.com")

    assert two.can_read("hotel-rheinblick/rooms/012-rhine-quiet.md", "mara@example.com")
    assert not two.can_read("hotel-rheinblick/rooms/012-rhine-quiet.md", "someone-else")


# ---------------------------------------------------------------- what the owner admits


def test_the_owner_sees_their_whole_folder_with_what_they_said_about_each_file(two):
    seen = {f["path"]: f["visibility"] for f in two.files("hotel-rheinblick")}
    assert seen["about.md"] == folders.PUBLIC
    assert seen["rooms/012-rhine-quiet.md"] == folders.PUBLIC_SUMMARY
    assert seen["claudeconnect/tx-verband.md"] == folders.SHARED
    assert seen["notes/takings.md"] == folders.HIDDEN
    assert folders.MARKER not in seen, "the folder's own bookkeeping is not part of what it offers"


def test_an_unmarked_file_is_no_more_open_than_the_seeded_cards_say(tmp_path):
    """tools/seed_vaults.py writes `public-summary` for every file; an unmarked folder has to agree."""
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "about.md").write_text("# Plain\n", encoding="utf-8")
    assert folders.LocalFolderLink(tmp_path).files("plain")[0]["visibility"] == folders.DEFAULT_VISIBILITY


def test_a_broken_marker_line_cannot_open_a_file(tmp_path):
    """A typo must fail to close a file further, never to open one."""
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "about.md").write_text("# Plain\n", encoding="utf-8")
    (tmp_path / "plain" / folders.MARKER).write_text("about.md = publick\nnonsense\n= public\n", encoding="utf-8")
    assert folders.LocalFolderLink(tmp_path).files("plain")[0]["visibility"] == folders.DEFAULT_VISIBILITY


def test_the_digest_is_the_one_the_card_published(two):
    """A Card carries paths and digests, never contents. The folder has to agree with the Card, or the
    handshake is talking about a different file than the index was."""
    import hashlib

    body = (two.root / "hotel-rheinblick" / "about.md").read_bytes()
    expected = "sha256:" + hashlib.sha256(body).hexdigest()[:12]
    assert next(f for f in two.files("hotel-rheinblick") if f["path"] == "about.md")["digest"] == expected


# ---------------------------------------------------------------- the manifest


def test_an_unlinked_viewer_sees_only_what_the_card_already_says(two):
    manifest = two.manifest("hotel-rheinblick", "mara@example.com")
    assert manifest["linked"] is False
    assert {f["path"] for f in manifest["files"]} == {
        "about.md",
        "rooms/012-rhine-quiet.md",
        "rooms/rates-2027.md",
    }
    assert manifest["withheld"] == 2, "the transcript and the takings are counted, not named"


def test_a_linked_viewer_sees_the_shared_files_the_card_never_mentioned(two):
    """This difference *is* the folder link, and it is the thing worth putting on a screen."""
    two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])
    manifest = two.manifest("hotel-rheinblick", "mara@example.com")

    assert manifest["linked"] is True
    assert "claudeconnect/tx-verband.md" in {f["path"] for f in manifest["files"]}
    assert manifest["withheld"] == 1, "only the owner's own file is withheld now"


def test_no_manifest_ever_names_a_hidden_or_private_file(two):
    """Listing a file in order to say it is secret leaks its existence."""
    two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])
    two.grant("hotel-rheinblick", "mara@example.com")  # the whole folder, as wide as a grant gets

    text = str(two.manifest("hotel-rheinblick", "mara@example.com"))
    assert "takings" not in text
    assert not two.can_read("hotel-rheinblick/notes/takings.md", "mara@example.com")


def test_the_owner_sees_everything_and_needs_no_link(two):
    assert two.can_read("hotel-rheinblick/notes/takings.md", "hotel-rheinblick")
    assert two.manifest("hotel-rheinblick", "hotel-rheinblick")["withheld"] == 0


def test_reading_without_a_grant_raises_rather_than_hinting(two):
    two.accept_link(two.request_link("mara@example.com", "hotel-rheinblick")["id"])
    with pytest.raises(folders.FolderError, match="may not read"):
        two.read("hotel-rheinblick/claudeconnect/tx-verband.md", "mara@example.com")


def test_a_path_cannot_climb_out_of_the_folder_it_names(two):
    for bad in ["hotel-rheinblick/../mara@example.com/x.md", "hotel-rheinblick/rooms/../../x"]:
        with pytest.raises(folders.FolderError, match="leaves the folder"):
            two.can_read(bad, "mara@example.com")


# ---------------------------------------------------------------- the real vaults, and the config


def test_the_default_root_is_the_vault_corpus_the_cards_were_built_from():
    """Slice 1 runs on what is already there: the folders in testdata/vaults/, not a fixture of its own."""
    assert folders.LocalFolderLink().root == VAULTS
    held = folders.LocalFolderLink().files("hotel-krafft")
    assert {f["path"] for f in held} >= {"about.md", "contact.md"}
    assert all(f["visibility"] == folders.DEFAULT_VISIBILITY for f in held)


def test_an_unknown_folder_link_falls_back_to_local_and_says_so(monkeypatch):
    monkeypatch.setattr("app.config.FOLDER_LINK", "telepathy")
    folders.reset()
    status = folders.status()
    assert status["folder_link"] == "local"
    assert "telepathy" in status["why"]


def test_the_default_is_local_folders(monkeypatch):
    monkeypatch.setattr("app.config.FOLDER_LINK", "local")
    folders.reset()
    assert folders.status() == {
        "folder_link": "local",
        "requested": "local",
        "why": "local folders",
        "root": str(VAULTS),
    }


def test_the_module_level_calls_go_through_the_configured_link(monkeypatch, tmp_path):
    """The hub never holds an implementation; it asks `folders` and gets whichever one is configured."""
    monkeypatch.setattr("app.config.FOLDER_LINK", "local")
    monkeypatch.setattr("app.config.FOLDER_ROOT", tmp_path)
    folders.reset()
    (tmp_path / "a-business").mkdir()
    (tmp_path / "a-business" / "about.md").write_text("# A\n", encoding="utf-8")

    link = folders.request_link("a-traveller", "a-business")
    assert folders.between("a-business", "a-traveller")["id"] == link["id"]
    assert not folders.linked("a-traveller", "a-business")
    folders.accept_link(link["id"])
    assert folders.linked("a-traveller", "a-business")

    folders.grant("a-business/about.md", "a-traveller")
    assert folders.can_read("a-business/about.md", "a-traveller")
    assert folders.files("a-business")[0]["path"] == "about.md"
    assert folders.manifest("a-business", "a-traveller")["linked"] is True


def test_open_link_accepts_only_when_the_other_sides_answer_is_already_yes(monkeypatch, tmp_path):
    """A published, freely connectable Card is a standing yes. A Card that waits for its owner is not."""
    monkeypatch.setattr("app.config.FOLDER_ROOT", tmp_path)
    folders.reset()
    waiting = folders.open_link("a-traveller", "a-person", auto_accept=False)
    assert waiting["state"] == folders.REQUESTED

    open_now = folders.open_link("a-traveller", "a-business", auto_accept=True)
    assert open_now["state"] == folders.ESTABLISHED
    assert open_now["accepted_by"] == "a-business"


def test_asking_for_claudeconnect_before_the_adapter_exists_still_runs(monkeypatch):
    """Slice 3 brings the adapter. Until it does — and if it is ever dropped from a build — asking for it
    must leave a working hub, not an import error on startup."""
    monkeypatch.setattr("app.config.FOLDER_LINK", "claudeconnect")
    monkeypatch.setitem(__import__("sys").modules, "app.cc_folders", None)
    folders.reset()
    status = folders.status()
    assert status["folder_link"] == "local"
    assert status["requested"] == "claudeconnect"
    assert "local" in status["why"]
