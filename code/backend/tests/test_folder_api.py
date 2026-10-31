"""The folder surface over HTTP: a link secret, a manifest, and one granted file at a time.

`folders.py` decides access and moves no bytes; `folder_keys.py` says who is asking; these two
endpoints are the door. The tests below are the invariants that door stands on, and they are
written at the HTTP edge on purpose — that is where the percent-decoding, the header parsing and
the response codes happen, and a traversal that `split_path` refuses in Python can still be a
traversal if the route decodes it afterwards.

The one that matters most is the first: **a withheld file and a file that never existed are
indistinguishable.** Every other refusal in here is checked against that same sentence and that
same status, because a caller who can tell "not allowed" from "not there" can map a folder it is
not allowed to read.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app import audit, config, db, folder_keys, folders, guard, main

ROOT = Path(__file__).resolve().parents[3]
VAULTS = ROOT / "testdata" / "vaults"

HOTEL = "hotel-rheinblick"
MARA = "mara@example.com"
STRANGER = "someone-else"


@pytest.fixture(autouse=True)
def clean_slate(client):
    """Links, grants, keys and the ledger are per test; in life these tables only ever grow."""
    folders.init()
    folder_keys.init()
    audit.init()
    with db.write() as cur:
        for table in ("folder_links", "folder_grants", "folder_handles", "folder_keys", "hub_admin_log"):
            cur.execute(f"DELETE FROM {table}")
    folders.reset()
    guard.folder_reads.hits.clear()
    yield
    folders.reset()
    guard.folder_reads.hits.clear()


@pytest.fixture
def vault(monkeypatch, tmp_path) -> Path:
    """One folder with a file at each visibility, and a traveller who holds none.

    `public` needs no grant (it is published), `public-summary` is listed and needs one, `shared` is
    not in the Card at all, and `private`/`hidden` are the owner's alone.
    """
    hotel = tmp_path / HOTEL
    (hotel / "rooms").mkdir(parents=True)
    (hotel / "drafts").mkdir()
    (hotel / "guests").mkdir()
    (hotel / "books").mkdir()
    (hotel / "about.md").write_text("# Rheinblick\nA quiet house by the river.\n", encoding="utf-8")
    (hotel / "rooms" / "012-rhine-quiet.md").write_text("Rear room, 2 guests, CHF 180.\n", encoding="utf-8")
    (hotel / "rooms" / "rates-2027.md").write_text("Spring: CHF 190.\n", encoding="utf-8")
    (hotel / "drafts" / "refurbishment.md").write_text("Third floor, 2028.\n", encoding="utf-8")
    (hotel / "guests" / "arrivals.md").write_text("Frau Berger, room 12.\n", encoding="utf-8")
    (hotel / "books" / "takings.md").write_text("Not yours.\n", encoding="utf-8")
    (hotel / folders.MARKER).write_text(
        "\n".join(
            [
                "# Visibility",
                "",
                "- about.md: public",
                "- rooms/: public-summary",
                "- drafts/: shared",
                "- guests/: private",
                "- books/: hidden",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / MARA).mkdir()
    monkeypatch.setattr(config, "FOLDER_LINK", "local")
    monkeypatch.setattr(config, "FOLDER_ROOT", tmp_path)
    folders.reset()
    return hotel


def link_up(viewer: str = MARA, owner: str = HOTEL) -> dict:
    """An established link between two handles, and a minted secret for the viewer's side."""
    row = folders.open_link(viewer, owner, auto_accept=True, by=owner)
    return folder_keys.mint(row["id"], viewer)


def auth(key: dict) -> dict[str, str]:
    """The header a read presents its secret in."""
    return {"Authorization": f"Bearer {key['secret']}"}


# ---------------------------------------------------------------- slice A: who is asking


def test_a_read_without_a_secret_is_refused_and_says_how_to_bring_one(client, vault):
    """401, not 404: the endpoint exists, and a caller with no credential should be told that."""
    for url in ("/api/folders/manifest", "/api/folders/file?path=about.md"):
        answer = client.get(url)
        assert answer.status_code == 401, url
        assert answer.headers["WWW-Authenticate"] == "Bearer"
        assert "Bearer" in answer.json()["detail"]


def test_a_wrong_secret_a_missing_one_and_a_wrong_scheme_all_say_the_same_thing(client, vault):
    """A password endpoint that distinguishes its noes is an oracle. So is this one."""
    key = link_up()
    said = set()
    for header in ({}, {"Authorization": "Bearer not-a-secret"}, {"Authorization": key["secret"]}):
        answer = client.get("/api/folders/manifest", headers=header)
        assert answer.status_code == 401
        said.add(answer.json()["detail"])
    assert len(said) == 1, "the refusals differ, so they can be told apart"
    assert client.get("/api/folders/manifest", headers=auth(key)).status_code == 200


def test_the_secret_is_hashed_at_rest_and_the_plaintext_is_nowhere_in_the_database(client, vault):
    """A stolen dump must not be a stolen folder."""
    key = link_up()
    with db.cursor() as cur:
        rows = cur.execute("SELECT id, secret_sha256 FROM folder_keys").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == folder_keys.fingerprint(key["secret"])
    assert key["secret"] not in rows[0][1]
    # And nothing anywhere in the row holds it, whatever column it might have been put in.
    with db.cursor() as cur:
        every = cur.execute("SELECT * FROM folder_keys").fetchall()
    assert key["secret"] not in "".join(str(v) for v in every[0])


def test_the_secret_is_returned_once_and_no_later_call_hands_it_back(client, vault):
    """`mint` is the only call that ever holds the plaintext. Nothing stores it, so nothing can."""
    key = link_up()
    listed = folder_keys.keys_for(key["link"])
    assert [k["id"] for k in listed] == [key["id"]]
    assert "secret" not in listed[0] and key["secret"] not in str(listed)
    assert key["secret"] not in client.get("/api/folders/manifest", headers=auth(key)).text


def test_minting_is_never_logged(client, vault, caplog):
    """Never logged, so a log shipped off the box is not a folder shipped off the box."""
    with caplog.at_level(logging.DEBUG):
        key = link_up()
        client.get("/api/folders/manifest", headers=auth(key))
        client.get("/api/folders/file?path=about.md", headers=auth(key))
    assert key["secret"] not in caplog.text


def test_a_secret_for_a_link_the_other_side_has_not_accepted_is_refused(client, vault):
    """A capability handed out before consent would make the other side's yes decorative."""
    row = folders.request_link(MARA, HOTEL)
    assert row["state"] == folders.REQUESTED
    with pytest.raises(folder_keys.KeyError_, match="not established"):
        folder_keys.mint(row["id"], MARA)


def test_a_secret_can_only_be_minted_for_a_party_to_the_link(client, vault):
    """The key names a side of a link. A handle that is party to neither side has no side to name."""
    key = link_up()
    with pytest.raises(folder_keys.KeyError_, match="not a party"):
        folder_keys.mint(key["link"], STRANGER)


def test_revoking_the_link_kills_its_secrets_on_the_very_next_request(client, vault):
    """Invariant 5: on the next request, not on a cache expiry. The state is re-read every time."""
    key = link_up()
    folders.grant(f"{HOTEL}/rooms/012-rhine-quiet.md", MARA)
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(key)).status_code == 200

    folders.revoke_link(key["link"])
    assert folders.get_link(key["link"])["state"] == folders.REVOKED
    assert folder_keys.resolve(key["secret"]) is None
    assert client.get("/api/folders/manifest", headers=auth(key)).status_code == 401
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(key)).status_code == 401


def test_revoking_one_secret_leaves_the_link_and_the_other_secrets_alone(client, vault):
    """A lost laptop is not a withdrawn relationship."""
    first, second = link_up(), folder_keys.mint(folders.between(MARA, HOTEL)["id"], MARA)
    assert first["secret"] != second["secret"]
    assert folder_keys.revoke(first["id"]) is True
    assert folder_keys.revoke(first["id"]) is False, "revoking twice is not two revocations"
    assert client.get("/api/folders/manifest", headers=auth(first)).status_code == 401
    assert client.get("/api/folders/manifest", headers=auth(second)).status_code == 200


def test_an_operator_can_mint_a_secret_and_an_unconfigured_hub_refuses_to(client, vault, monkeypatch):
    """The escape hatch for curl and for the party that did not call connect. It fails closed."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    row = folders.open_link(MARA, HOTEL, auto_accept=True, by=HOTEL)
    closed = client.post("/api/folders/keys", json={"link": row["id"], "handle": MARA})
    assert closed.status_code == 503, "an unconfigured hub must refuse, not mint"

    monkeypatch.setattr(config, "ADMIN_TOKEN", "operator-secret")
    assert client.post("/api/folders/keys", json={"link": row["id"], "handle": MARA}).status_code == 403
    minted = client.post(
        "/api/folders/keys",
        json={"link": row["id"], "handle": MARA},
        headers={"X-Admin-Token": "operator-secret"},
    )
    assert minted.status_code == 200
    assert client.get("/api/folders/manifest", headers=auth(minted.json())).status_code == 200


def test_connecting_hands_the_requester_the_secret_for_its_side(client, vault):
    """The demo path, end to end: one call opens the connection and comes back with the folder's key.

    This is what slice D needs from the connect button — a link, a manifest and a credential in one
    answer — and it is the reason the read routes need no bootstrap of their own.
    """
    answer = client.post("/api/hub/connect", json={"requester": "Mara Keller", "entity_id": HOTEL})
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["folder"]["owner"] == HOTEL
    key = body["folder_key"]
    assert key["handle"] == "mara-keller" and key["peer"] == HOTEL
    assert key["link"] == body["folder_link"]
    manifest = client.get("/api/folders/manifest", headers=auth(key))
    assert manifest.status_code == 200
    assert manifest.json()["owner"] == HOTEL
    assert client.get("/api/folders/file?path=about.md", headers=auth(key)).status_code == 200


# ---------------------------------------------------------------- slice B: the manifest


def test_the_manifest_comes_from_the_bearer_and_takes_no_handle_at_all(client, vault):
    """No handle parameter means no enumeration surface: a caller cannot ask about a folder it has
    no link to, and naming somebody else in the query string changes nothing about its authority."""
    key = link_up()
    plain = client.get("/api/folders/manifest", headers=auth(key)).json()
    assert plain["owner"] == HOTEL and plain["viewer"] == MARA and plain["linked"] is True
    assert plain["link"] == key["link"]
    for query in ("?viewer=hotel-rheinblick", "?owner=someone-else", "?viewer=someone-else&owner=someone-else"):
        again = client.get(f"/api/folders/manifest{query}", headers=auth(key)).json()
        assert again == plain, f"{query} changed the answer, so a parameter is deciding authority"


def test_no_manifest_ever_names_a_private_or_hidden_path_and_withheld_is_a_number(client, vault):
    """`withheld` admits to how much and never to what. A name is the leak, not a count."""
    key = link_up()
    body = client.get("/api/folders/manifest", headers=auth(key)).json()
    text = client.get("/api/folders/manifest", headers=auth(key)).text
    assert isinstance(body["withheld"], int) and body["withheld"] == 2
    for secret in ("guests", "arrivals", "books", "takings"):
        assert secret not in text, f"{secret} was named in a manifest"
    assert {f["visibility"] for f in body["files"]} <= folders.ADMITTED


def test_a_linked_viewer_sees_the_shared_file_the_card_never_mentioned_but_cannot_read_it(client, vault):
    """The folder link's whole point, and its honest limit: seen is not served (`folders.SERVED`)."""
    key = link_up()
    body = client.get("/api/folders/manifest", headers=auth(key)).json()
    draft = next(f for f in body["files"] if f["path"] == "drafts/refurbishment.md")
    assert draft["visibility"] == folders.SHARED
    assert draft["readable"] is False, "a manifest must not promise a byte this hub would refuse"

    folders.grant(f"{HOTEL}/drafts/refurbishment.md", MARA)
    after = client.get("/api/folders/manifest", headers=auth(key)).json()
    assert next(f for f in after["files"] if f["path"] == "drafts/refurbishment.md")["readable"] is False
    assert client.get("/api/folders/file?path=drafts/refurbishment.md", headers=auth(key)).status_code == 404


def test_the_manifest_says_readable_for_exactly_what_the_file_route_serves(client, vault):
    """One definition of readable, or a client is told one thing and handed another."""
    key = link_up()
    folders.grant(f"{HOTEL}/rooms/012-rhine-quiet.md", MARA)
    for file in client.get("/api/folders/manifest", headers=auth(key)).json()["files"]:
        got = client.get(f"/api/folders/file?path={file['path']}", headers=auth(key))
        assert (got.status_code == 200) is file["readable"], f"{file['path']} says {file['readable']}"


# ---------------------------------------------------------------- slice B: reading a file


def test_a_public_file_needs_no_grant_and_arrives_byte_for_byte(client, vault):
    """`public` is published; a grant for it would be theatre. The bytes are the bytes on disk."""
    key = link_up()
    answer = client.get("/api/folders/file?path=about.md", headers=auth(key))
    assert answer.status_code == 200
    assert answer.content == (vault / "about.md").read_bytes()
    assert answer.headers["content-type"].startswith("text/markdown")
    assert answer.headers["accept-ranges"] == "none"
    assert answer.headers["x-folder-link"] == key["link"]


def test_a_listed_file_is_refused_until_the_owner_grants_that_one_path(client, vault):
    """The grant is the only thing that makes bytes readable, and it names one path."""
    key = link_up()
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(key)).status_code == 404

    folders.grant(f"{HOTEL}/rooms/012-rhine-quiet.md", MARA)
    opened = client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(key))
    assert opened.status_code == 200 and b"CHF 180" in opened.content
    # Invariant 4: one path, not a pattern. The sibling in the same folder stayed shut.
    assert client.get("/api/folders/file?path=rooms/rates-2027.md", headers=auth(key)).status_code == 404


def test_a_grant_to_one_handle_is_not_a_grant_to_another(client, vault):
    """Invariant 4's other half: one handle. Two links, one grant, one reader."""
    mine, theirs = link_up(MARA), link_up(STRANGER)
    folders.grant(f"{HOTEL}/rooms/012-rhine-quiet.md", MARA)
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(mine)).status_code == 200
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(theirs)).status_code == 404


def test_a_withheld_file_and_a_file_that_never_existed_are_the_same_404(client, vault):
    """**Invariant 1.** Hidden, private, shared, unlisted, and plain absent: one status, one sentence."""
    key = link_up()
    answers = [
        client.get(f"/api/folders/file?path={path}", headers=auth(key))
        for path in (
            "guests/arrivals.md",  # private
            "books/takings.md",  # hidden
            "drafts/refurbishment.md",  # shared, not served
            "rooms/no-such-file.md",  # never existed, in a folder that does
            "no-such-folder/no-such-file.md",  # never existed at all
            "guests",  # a directory, which is not a file
        )
    ]
    assert {a.status_code for a in answers} == {404}
    assert len({a.json()["detail"] for a in answers}) == 1, "the refusals differ, so they can be told apart"
    for answer in answers:
        assert "arrivals" not in answer.text and "takings" not in answer.text


def test_a_private_or_hidden_file_stays_shut_even_with_a_grant_forced_into_the_table(client, vault):
    """`private` and `hidden` are never served, grant or no grant. Checked past the grant check."""
    key = link_up()
    link = folders.between(MARA, HOTEL)
    with db.write() as cur:  # what folders.grant refuses to write, written anyway
        for path in ("guests/arrivals.md", "books/takings.md"):
            cur.execute(
                "INSERT INTO folder_grants (id, created_at, owner, path, to_handle, link_id) VALUES (?,?,?,?,?,?)",
                [f"fg-forced-{path.count('/')}{path[0]}", db.now().replace(tzinfo=None), HOTEL, path, MARA, link["id"]],
            )
    assert len(folders.grants(HOTEL, MARA)) == 2, "the forced grants are really in the table"
    for path in ("guests/arrivals.md", "books/takings.md"):
        assert client.get(f"/api/folders/file?path={path}", headers=auth(key)).status_code == 404


def test_a_wildcard_grant_opens_nothing(client, vault):
    """Invariant 4. `*` is not a path, and the folder admits nothing at it."""
    key = link_up()
    for pattern in ("*", "rooms/*", "**", "rooms/*.md"):
        with pytest.raises(folders.FolderError, match="admits no file or folder"):
            folders.grant(f"{HOTEL}/{pattern}", MARA)
    assert folders.grants(HOTEL, MARA) == []
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(key)).status_code == 404


# ---------------------------------------------------------------- traversal, from the HTTP edge


TRAVERSALS = [
    "../mara@example.com/stolen.md",
    "..%2fmara@example.com%2fstolen.md",
    "%2e%2e/mara@example.com/stolen.md",
    "%2e%2e%2fmara@example.com%2fstolen.md",
    "rooms/../../mara@example.com/stolen.md",
    "....//mara@example.com/stolen.md",
    "．．/mara@example.com/stolen.md",  # fullwidth full stop
    "․․/mara@example.com/stolen.md",  # one dot leader
    ".․/mara@example.com/stolen.md",
    "/etc/passwd",
    "//etc/passwd",
    "etc/../../../../../../etc/passwd",
    "%2fetc%2fpasswd",
    "../../../../../../etc/passwd",
    "about.md%00.png",
]


def test_no_encoding_of_dot_dot_climbs_out_of_the_folder(client, vault, tmp_path):
    """**Invariant 2**, where the decoding happens. Every one of these is the same 404 as a typo.

    Pinned here and not only on `split_path` because the route percent-decodes *before* the module
    sees the path: a check that passed in Python on `..%2f` would be checking a string the server
    never actually resolved. The path travels in the query string precisely so that every one of
    these reaches the route — an HTTP client collapses `../` inside a URL *path* before sending it,
    which would quietly turn half of this list into a test of httpx rather than of the hub.
    """
    (tmp_path / MARA / "stolen.md").write_text("The traveller's own notes.\n", encoding="utf-8")
    key = link_up()
    plain = client.get("/api/folders/file?path=no-such-file.md", headers=auth(key))
    assert plain.json()["detail"] == main.NO_SUCH_FILE
    reached = 0
    for attempt in TRAVERSALS:
        answer = client.get(f"/api/folders/file?path={attempt}", headers=auth(key))
        assert answer.status_code == 404, f"{attempt} answered {answer.status_code}"
        assert b"traveller" not in answer.content and b"root:" not in answer.content
        assert answer.json() == plain.json(), f"{attempt} is distinguishable from a missing file"
        reached += 1
    assert reached == len(TRAVERSALS), "every one of these has to reach the route to prove anything"


def test_a_symlink_pointing_out_of_the_folder_is_not_a_file_in_it(client, vault, tmp_path):
    """`rglob` and `is_file` both follow a symlink happily, so this has to be closed on purpose."""
    outside = tmp_path.parent / "outside.md"
    outside.write_text("Somebody else's file.\n", encoding="utf-8")
    (vault / "rooms" / "escape.md").symlink_to(outside)
    (vault / "elsewhere").symlink_to(tmp_path.parent)
    key = link_up()
    folders.grant(f"{HOTEL}/rooms", MARA)

    body = client.get("/api/folders/manifest", headers=auth(key))
    assert "escape.md" not in body.text and "elsewhere" not in body.text, "a symlink was listed"
    for path in ("rooms/escape.md", "elsewhere/outside.md"):
        answer = client.get(f"/api/folders/file?path={path}", headers=auth(key))
        assert answer.status_code == 404
        assert b"Somebody else" not in answer.content


# ---------------------------------------------------------------- what a read costs


def test_a_file_over_the_cap_is_refused_rather_than_streamed(client, vault, monkeypatch):
    """Invariant 6. One read must not be able to hold a worker, and the refusal says the number."""
    key = link_up()
    monkeypatch.setattr(config, "FOLDER_READ_MAX_BYTES", 4)
    answer = client.get("/api/folders/file?path=about.md", headers=auth(key))
    assert answer.status_code == 413
    assert "4" in answer.json()["detail"] and "Range" in answer.json()["detail"]


def test_a_range_request_gets_the_whole_file_and_is_told_so(client, vault):
    """Invariant 6's other half: the policy is decided here rather than inherited by accident."""
    key = link_up()
    answer = client.get("/api/folders/file?path=about.md", headers={**auth(key), "Range": "bytes=0-3"})
    assert answer.status_code == 200, "a partial answer would be a policy nobody chose"
    assert answer.content == (vault / "about.md").read_bytes()
    assert answer.headers["accept-ranges"] == "none"


def test_reads_are_counted_per_link_and_not_per_address(client, vault, monkeypatch):
    """Invariant 7. The link is what the hub granted; an IP is not, so the budget follows the link."""
    mine, theirs = link_up(MARA), link_up(STRANGER)
    monkeypatch.setattr(guard.folder_reads, "per_client", 2)
    guard.folder_reads.hits.clear()

    assert client.get("/api/folders/file?path=about.md", headers=auth(mine)).status_code == 200
    assert client.get("/api/folders/file?path=about.md", headers=auth(mine)).status_code == 200
    over = client.get("/api/folders/file?path=about.md", headers=auth(mine))
    assert over.status_code == 429 and int(over.headers["Retry-After"]) >= 1
    # Same client address, a different link: its own budget, untouched by the one next door.
    assert client.get("/api/folders/file?path=about.md", headers=auth(theirs)).status_code == 200


def test_every_read_is_in_the_ledger_with_the_handle_that_made_it(client, vault):
    """Invariant 8. An owner who grants a path should be able to see it was used, and by whom."""
    key = link_up()
    folders.grant(f"{HOTEL}/rooms/012-rhine-quiet.md", MARA)
    client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(key))
    client.get("/api/folders/file?path=guests/arrivals.md", headers=auth(key))  # refused, so not a read

    rows = audit.entries(action_prefix="folder.read")
    assert [r["subject"] for r in rows] == [f"{HOTEL}/rooms/012-rhine-quiet.md"]
    assert rows[0]["actor"] == MARA, "the one ledger row that can name who acted"
    assert rows[0]["credential"] == "link secret"
    assert key["id"] in rows[0]["detail"] and key["secret"] not in str(rows)
    assert folder_keys.keys_for(key["link"])[0]["last_used_at"] is not None


# ---------------------------------------------------------------- the corpus


def test_every_byte_served_matches_the_digest_the_manifest_published(client):
    """**Invariant 3**, over the whole corpus: 61 folders, every file either served or counted.

    If a served byte could differ from the published digest, the handshake and the index would be
    describing different files and an agent could not tell which one it had been given.
    """
    checked, owners = 0, sorted(v.name for v in VAULTS.iterdir() if v.is_dir())
    assert len(owners) == 61, f"the corpus is {len(owners)} folders, not 61"
    key = link_up("a-reading-agent", owners[0])
    for owner in owners:
        bearer = key if owner == owners[0] else link_up("a-reading-agent", owner)
        manifest = client.get("/api/folders/manifest", headers=auth(bearer)).json()
        assert manifest["owner"] == owner
        for file in manifest["files"]:
            if file["visibility"] in folders.SERVED and file["visibility"] != folders.PUBLIC:
                folders.grant(file["ref"], "a-reading-agent")
        manifest = client.get("/api/folders/manifest", headers=auth(bearer)).json()
        for file in manifest["files"]:
            answer = client.get(f"/api/folders/file?path={file['path']}", headers=auth(bearer))
            if not file["readable"]:
                assert answer.status_code == 404, f"{owner}/{file['path']}"
                continue
            assert answer.status_code == 200, f"{owner}/{file['path']}: {answer.text}"
            assert folders.digest(answer.content) == file["digest"], f"{owner}/{file['path']} drifted"
            assert len(answer.content) == file["bytes"]
            assert answer.headers["etag"] == f'"{file["digest"]}"'
            assert answer.content == (VAULTS / owner / file["path"]).read_bytes()
            checked += 1
    assert checked > 150, f"only {checked} files were actually read"


def test_a_pdf_arrives_as_a_pdf(client):
    """An agent decides how to parse a file by what it is told it is."""
    key = link_up("a-reading-agent", "elektro-mattenhof")
    answer = client.get("/api/folders/file?path=preisliste.pdf", headers=auth(key))
    assert answer.status_code == 200
    assert answer.headers["content-type"] == "application/pdf"
    assert answer.content.startswith(b"%PDF-")


# ---------------------------------------------------------------- what the hub says about itself


def test_the_status_endpoint_is_honest_about_one_disk_and_names_no_server_path(client):
    """A screen that implied two machines would be the page that is wrong."""
    body = client.get("/api/folders/status").json()
    assert body["folder_link"] == "local" and body["requested"] == "local"
    assert "one disk" in body["honest"]
    assert sorted(body["served_visibilities"]) == sorted(folders.SERVED)
    assert body["max_read_bytes"] == config.FOLDER_READ_MAX_BYTES
    assert "root" not in body and str(VAULTS) not in str(body), "a server path is nobody's business"


# ---------------------------------------------------------------- giving and taking a grant back


@pytest.fixture
def owner_key(vault) -> dict:
    """The owner's own key for its side of the link, which is what makes a grant a per-owner write."""
    link = folders.open_link(MARA, HOTEL, auto_accept=True, by=HOTEL)
    return folder_keys.mint(link["id"], HOTEL)


def test_the_owner_grants_one_path_of_its_own_folder_and_the_peer_can_then_read_it(client, vault, owner_key):
    """The whole product in four calls: link, grant, manifest, bytes. No handle in any body."""
    viewer = folder_keys.mint(owner_key["link"], MARA)
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(viewer)).status_code == 404

    given = client.post("/api/folders/grants", json={"path": "rooms/012-rhine-quiet.md"}, headers=auth(owner_key))
    assert given.status_code == 200, given.text
    assert given.json()["owner"] == HOTEL and given.json()["to"] == MARA
    assert given.json()["link"] == owner_key["link"]

    opened = client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(viewer))
    assert opened.status_code == 200 and b"CHF 180" in opened.content
    assert client.get("/api/folders/file?path=rooms/rates-2027.md", headers=auth(viewer)).status_code == 404


def test_a_grant_cannot_name_somebody_elses_folder_or_somebody_else_to_give_it_to(client, vault, owner_key):
    """Owner and recipient come from the bearer, so there is no parameter left to lie in."""
    body = client.post("/api/folders/grants", json={"path": "rooms/012-rhine-quiet.md"}, headers=auth(owner_key))
    assert body.json()["owner"] == HOTEL and body.json()["to"] == MARA
    # A path that tries to name another folder is refused as leaving this one, not resolved.
    for bad in ("../mara@example.com/stolen.md", f"/{MARA}/stolen.md"):
        assert client.post("/api/folders/grants", json={"path": bad}, headers=auth(owner_key)).status_code == 400
    # The viewer's own key grants from the *viewer's* folder, which holds nothing to grant.
    viewer = folder_keys.mint(owner_key["link"], MARA)
    theirs = client.post("/api/folders/grants", json={"path": "rooms/rates-2027.md"}, headers=auth(viewer))
    assert theirs.status_code == 400 and "admits no file" in theirs.json()["detail"]


def test_the_grant_route_refuses_a_pattern_and_the_whole_folder(client, vault, owner_key):
    """Invariant 4 at the edge: one path, not a shape that matches many."""
    for bad in ("*", "rooms/*", "rooms/*.md", "rooms/?.md", "/", "   "):
        answer = client.post("/api/folders/grants", json={"path": bad}, headers=auth(owner_key))
        assert answer.status_code == 400, f"{bad!r} was accepted"
        assert "one path" in answer.json()["detail"]
    assert client.get("/api/folders/grants", headers=auth(owner_key)).json()["given"] == []


def test_a_grant_is_refused_for_anything_the_owner_never_admitted(client, vault, owner_key):
    """A grant on a hidden file says the same words as a grant on a file that was never there."""
    hidden = client.post("/api/folders/grants", json={"path": "books/takings.md"}, headers=auth(owner_key))
    absent = client.post("/api/folders/grants", json={"path": "books/no-such-file.md"}, headers=auth(owner_key))
    assert hidden.status_code == absent.status_code == 400
    assert hidden.json()["detail"] == absent.json()["detail"].replace("no-such-file.md", "takings.md")


def test_both_halves_of_a_links_grants_are_listed_and_kept_apart(client, vault, owner_key):
    """An owner looking at a screen has to know which of these is theirs to take back."""
    viewer = folder_keys.mint(owner_key["link"], MARA)
    client.post("/api/folders/grants", json={"path": "rooms/012-rhine-quiet.md"}, headers=auth(owner_key))
    mine = client.get("/api/folders/grants", headers=auth(owner_key)).json()
    assert [g["ref"] for g in mine["given"]] == [f"{HOTEL}/rooms/012-rhine-quiet.md"]
    assert mine["received"] == []
    theirs = client.get("/api/folders/grants", headers=auth(viewer)).json()
    assert theirs["given"] == [] and [g["ref"] for g in theirs["received"]] == [f"{HOTEL}/rooms/012-rhine-quiet.md"]


def test_only_the_owner_who_gave_a_grant_can_take_it_back(client, vault, owner_key):
    """And a grant that is not yours is *not found*, so ids cannot be mapped by deleting them."""
    viewer = folder_keys.mint(owner_key["link"], MARA)
    grant = client.post("/api/folders/grants", json={"path": "rooms/012-rhine-quiet.md"}, headers=auth(owner_key))
    grant_id = grant.json()["id"]

    refused = client.delete(f"/api/folders/grants/{grant_id}", headers=auth(viewer))
    invented = client.delete("/api/folders/grants/fg-never-existed", headers=auth(viewer))
    assert refused.status_code == invented.status_code == 404
    assert refused.json() == invented.json(), "the recipient can tell a real grant id from a made-up one"
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(viewer)).status_code == 200

    gone = client.delete(f"/api/folders/grants/{grant_id}", headers=auth(owner_key))
    assert gone.status_code == 200 and gone.json()["revoked"] is True
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(viewer)).status_code == 404
    assert [r["action"] for r in audit.entries(action_prefix="folder.grant")] == ["folder.grant.revoke"]


def test_withdrawing_the_link_over_http_retires_its_secrets_and_its_reads(client, vault, owner_key):
    """Invariant 5 at the edge. Either party may; neither needs the other's permission to stop."""
    viewer = folder_keys.mint(owner_key["link"], MARA)
    client.post("/api/folders/grants", json={"path": "rooms/012-rhine-quiet.md"}, headers=auth(owner_key))
    assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(viewer)).status_code == 200

    assert client.delete("/api/folders/links/fl-not-a-link", headers=auth(viewer)).status_code == 404
    gone = client.delete(f"/api/folders/links/{viewer['link']}", headers=auth(viewer))
    assert gone.status_code == 200 and gone.json()["secrets_retired"] == 2
    assert gone.json()["state"] == folders.REVOKED
    for key in (viewer, owner_key):
        assert client.get("/api/folders/manifest", headers=auth(key)).status_code == 401
        assert client.get("/api/folders/file?path=rooms/012-rhine-quiet.md", headers=auth(key)).status_code == 401
    assert folders.grants(HOTEL, MARA), "the grant stays in the table, and stays dead"
    assert not folders.can_read(f"{HOTEL}/rooms/012-rhine-quiet.md", MARA)
