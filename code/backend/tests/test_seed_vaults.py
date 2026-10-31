"""The vault folders are the demo's real data, and what they say they do and need is the index.

tools/seed_vaults.py registers `testdata/vaults/*/` through the signup endpoint. These tests pin that the two
sides of the market are *parsed out of the owner's own markdown* — the folder stays the single source of truth —
and that a card built that way is actually findable by what it offers and by what it needs.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import re
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path

from app import hive

ROOT = Path(__file__).resolve().parents[1]


def _seed_vaults():
    """Load tools/seed_vaults.py as a module; it is a script, not part of the app package."""
    if "seed_vaults" in sys.modules:
        return sys.modules["seed_vaults"]
    spec = importlib.util.spec_from_file_location("seed_vaults", ROOT / "tools" / "seed_vaults.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_vaults"] = module
    spec.loader.exec_module(module)
    return module


def test_every_seeded_vault_says_what_it_does(client):
    seed = _seed_vaults()
    cards = {v.name: seed.build_card(v) for v in sorted(seed.VAULTS.iterdir()) if v.is_dir()}
    assert set(cards) == set(seed.KIND), "a folder nobody assigned a kind is a folder nobody seeds"
    for name, card in cards.items():
        assert card["offers"], f"{name} offers nothing, so no search can find it"
        assert all(o["title"] and o["summary"] for o in card["offers"]), name

    # The people and the café also say what they want, which is the other half of a hub.
    for name in ("lena-hofmann", "grid-ops", "cafe-rhein"):
        assert cards[name]["needs"], name
    # A stay's rooms are its offers: parsed from rooms.md, not typed twice.
    assert [o["title"] for o in cards["pension-limmat"]["offers"]] == ["Attic single", "River double", "Corner double"]
    assert cards["pension-limmat"]["offers"][0]["price_chf"] == 110


def test_the_folder_is_the_source_and_nothing_is_hardcoded(tmp_path):
    """A folder written today, with words that appear nowhere in the repo, must come out as a card."""
    vault = tmp_path / "freia-ott"
    vault.mkdir()
    (vault / "about.md").write_text("# Freia Ott\n\nShe fixes looms.\n", encoding="utf-8")
    (vault / "work.md").write_text(
        "# What I do\n\n- Jacquard loom repair — CHF 240 an hour.\n\n# What I need\n\n- A warping mill, second hand.\n",
        encoding="utf-8",
    )
    card = _seed_vaults().build_card(vault)
    assert card["offers"] == [
        {"title": "Jacquard loom repair", "summary": "Jacquard loom repair — CHF 240 an hour.", "price_chf": 240}
    ]
    assert card["needs"] == [{"title": "A warping mill, second hand", "summary": "A warping mill, second hand."}]


def test_a_seeded_person_is_found_by_what_she_offers_and_by_what_she_needs(client):
    """End to end on real demo data: build the card from the folder, publish it, search for it."""
    seed = _seed_vaults()
    for name in ("lena-hofmann", "grid-ops"):
        hive.publish(seed.build_card(seed.VAULTS / name))

    offered = hive.discover(query="dataviz sprint")
    lena = next(m for m in offered["matches"] if m["id"] == "lena-hofmann")
    assert lena["score_breakdown"]["offers_needs"] > 0
    assert any(why.startswith("offers ") for why in lena["why"])

    # Both of them are looking for the same contractor, and only a needs search finds them.
    wanted = {m["id"]: m for m in hive.discover(query="svelte contractor", looking_for="needs")["matches"]}
    assert wanted["lena-hofmann"]["score_breakdown"]["offers_needs"] > 0
    assert wanted["grid-ops"]["score_breakdown"]["offers_needs"] > 0
    offers_side = {m["id"]: m for m in hive.discover(query="svelte contractor")["matches"]}
    assert offers_side["lena-hofmann"]["score_breakdown"]["offers_needs"] == 0
    assert offers_side["grid-ops"]["score_breakdown"]["offers_needs"] == 0


def _make_corpus():
    """Load tools/make_corpus.py the same way: the curated table is a script, not a package."""
    if "make_corpus" in sys.modules:
        return sys.modules["make_corpus"]
    spec = importlib.util.spec_from_file_location("make_corpus", ROOT / "tools" / "make_corpus.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_corpus"] = module
    spec.loader.exec_module(module)
    return module


def test_every_folder_is_assigned_a_hub_and_a_kind_the_backend_accepts():
    """A folder missing from either map is a folder no hub ever sees, and a bad kind is a dead card."""
    seed, corpus = _seed_vaults(), _make_corpus()
    folders = {v.name for v in seed.VAULTS.iterdir() if v.is_dir()}
    assert folders == set(seed.HOME), "every vault needs a home hub"
    assert folders == set(seed.KIND), "every vault needs a kind"
    assert set(seed.HOME.values()) <= {"basel", "zurich", "bern"}
    assert set(seed.KIND.values()) <= set(corpus.KINDS), "a kind the backend does not accept"
    assert folders >= seed.UNCLAIMED, "an unclaimed folder that does not exist"


def test_the_generated_folders_still_say_what_the_curated_table_says():
    """The table in make_corpus.py is the source. Drift between it and disk is a silent fork."""
    corpus = _make_corpus()
    drift = {e.slug: corpus.drifted(e) for e in corpus.ENTITIES}
    assert not {slug: names for slug, names in drift.items() if names}
    assert not {e.slug for e in corpus.ENTITIES} & corpus.PRE_EXISTING, "the hand-written ten stay hand-written"


def test_the_generator_and_the_seeder_agree_on_every_hub_and_kind():
    """Two files hold the same fact, so a test holds them together rather than a convention."""
    seed, corpus = _seed_vaults(), _make_corpus()
    for entity in corpus.ENTITIES:
        assert seed.HOME[entity.slug] == entity.hub, entity.slug
        assert seed.KIND[entity.slug] == entity.kind, entity.slug
    assert {e.slug for e in corpus.ENTITIES if e.unclaimed} == seed.UNCLAIMED & {e.slug for e in corpus.ENTITIES}


def test_an_unclaimed_folder_registers_as_a_lead_and_not_as_a_business_that_agreed(client):
    """Variety in the trust signals has to survive the round trip, or it is only a comment."""
    seed = _seed_vaults()
    slug = sorted(seed.UNCLAIMED)[0]
    hive.publish(seed.build_card(seed.VAULTS / slug))
    assert hive.get_card(slug)["trust"]["claimed"] is False
    claimed = sorted(set(seed.KIND) - seed.UNCLAIMED)[0]
    hive.publish(seed.build_card(seed.VAULTS / claimed))
    assert hive.get_card(claimed)["trust"]["claimed"] is True
    # Nothing seeded carries a rating: that needs the signed receipt of a stay that happened.
    assert hive.get_card(slug)["trust"]["verified_reviews"]["average"] is None


def test_a_room_name_with_a_hyphen_in_it_is_still_a_bookable_unit(tmp_path):
    """`River-view double` parsed as nothing, so the room existed in the prose and not in the hub."""
    vault = tmp_path / "haus-am-hang"
    vault.mkdir()
    (vault / "about.md").write_text("# Haus am Hang\n\nFour rooms.\n", encoding="utf-8")
    (vault / "rooms.md").write_text(
        "# Rooms\n\n- South-facing double — 2 guests, CHF 180, 3 of them.\n- Attic single - 1 guest, CHF 90, 2.\n",
        encoding="utf-8",
    )
    units = _seed_vaults().read_units(vault)
    assert [(u["name"], u["max_guests"], u["price_chf"], u["quantity"]) for u in units] == [
        ("South-facing double", 2, 180, 3),
        ("Attic single", 1, 90, 2),
    ]


def test_the_real_hotel_krafft_folder_has_all_three_of_its_rooms():
    """The hyphen bug cost the demo card its most expensive room; this is the folder on disk."""
    seed = _seed_vaults()
    units = seed.read_units(seed.VAULTS / "hotel-krafft")
    assert [u["name"] for u in units] == ["Courtyard single", "Courtyard double", "River-view double"]


#: The answer key in testdata/README.md, between the markers, is what semantic search is measured
#: against. A pair is only worth measuring if literal matching cannot reach it; tools/eval_answer_key.py
#: scores it, and this module reuses that script's parser so there is only one of them.


def _eval_tool():
    """Load tools/eval_answer_key.py: the scorer, and the one parser for the answer key."""
    if "eval_answer_key" in sys.modules:
        return sys.modules["eval_answer_key"]
    spec = importlib.util.spec_from_file_location("eval_answer_key", ROOT / "tools" / "eval_answer_key.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["eval_answer_key"] = module
    spec.loader.exec_module(module)
    return module


def _indexed_text(card: dict) -> str:
    """Everything hive.discover can match a query term against, offers and needs included."""
    parts = [card.get("name", ""), card.get("tagline", ""), card.get("description", ""), *card.get("features", [])]
    for side in ("offers", "needs"):
        for entry in card.get(side) or []:
            parts += [str(entry.get(f)) for f in hive.OFFER_FIELDS if entry.get(f)]
    return " ".join(parts).lower()


def test_the_answer_key_covers_entities_that_exist_and_is_not_a_softball():
    """Every pair must be a real vault, and must share no searchable word with it.

    This is the honesty check on the key. `hive.discover` matches a term of more than three
    characters as a substring, so a query that shares one is already findable and proves nothing
    about semantic search. Fourteen pairs that share none is the measurement.
    """
    seed = _seed_vaults()
    rows = [(query, slug) for query, slug, _ in _eval_tool().pairs()]
    assert len(rows) >= 10, "the key needs ten to fifteen pairs to measure anything"
    for query, slug in rows:
        assert slug in seed.KIND, f"{slug} is in the answer key but not a vault"
        text = _indexed_text(seed.build_card(seed.VAULTS / slug))
        terms = {t for t in re.findall(r"[a-zäöü]+", query.lower()) if len(t) > 3} - hive.STOPWORDS
        assert terms, f"{query!r} has nothing a hub would search for"
        shared = sorted(t for t in terms if t in text)
        assert not shared, f"{query!r} already finds {slug} literally through {shared}"


def test_structure_lists_every_file_in_the_folder_and_not_only_the_markdown(tmp_path):
    """A vault with a CV in it must say so. Listing only markdown made the other files invisible.

    "Point at a folder and it becomes your presence" is not true if the Card quietly drops the
    four files that are not markdown, which is exactly what it used to do.
    """
    seed = _seed_vaults()
    vault = tmp_path / "freia-ott"
    (vault / "bilder").mkdir(parents=True)
    (vault / "about.md").write_text("# Freia Ott\n\nShe fixes looms.\n", encoding="utf-8")
    (vault / "work.md").write_text("# What I do\n\n- Loom repair — CHF 240 an hour.\n", encoding="utf-8")
    (vault / "cv.pdf").write_bytes(b"%PDF-1.4 pretend\n%%EOF\n")
    (vault / "rates-2026.csv").write_text("service,chf\nloom repair,240\n", encoding="utf-8")
    (vault / "bilder" / "webstuhl.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 40)

    card = seed.build_card(vault)
    listed = {row["path"] for row in card["structure"]}
    assert listed == {"about.md", "work.md", "cv.pdf", "rates-2026.csv", "bilder/webstuhl.png"}
    by_path = {row["path"]: row for row in card["structure"]}
    assert by_path["cv.pdf"]["bytes"] == 23
    assert by_path["cv.pdf"]["digest"].startswith("sha256:")
    assert by_path["cv.pdf"]["media_type"] == "application/pdf"
    assert by_path["bilder/webstuhl.png"]["media_type"] == "image/png"

    # The shape of the folder, never its contents: only the two markdown files were read, and the
    # bytes of the others appear nowhere in the Card.
    assert [o["title"] for o in card["offers"]] == ["Loom repair"]
    assert "pretend" not in json.dumps(card)
    assert "loom repair,240" not in json.dumps(card)


def test_the_five_visibility_values_do_what_the_card_spec_says(tmp_path):
    """`private` loses its digest, `shared` and `hidden` lose their row entirely.

    documentation/cards/README.md defines five values. Listing a folder in order to say it is
    secret leaks its existence, so two of the five are absent from `structure` rather than flagged.
    """
    seed = _seed_vaults()
    vault = tmp_path / "pension-test"
    for folder in ("fotos", "gaeste", "finanzen", "entwuerfe"):
        (vault / folder).mkdir(parents=True)
    (vault / "about.md").write_text("# Pension Test\n\nFour rooms.\n", encoding="utf-8")
    (vault / "menu.pdf").write_bytes(b"%PDF menu\n")
    (vault / "fotos" / "zimmer.png").write_bytes(b"\x89PNG\r\n\x1a\nfoto")
    (vault / "gaeste" / "2026.csv").write_text("name,nights\n", encoding="utf-8")
    (vault / "gaeste" / "2025.csv").write_text("name,nights\n", encoding="utf-8")
    (vault / "finanzen" / "steuern.csv").write_text("chf\n", encoding="utf-8")
    (vault / "entwuerfe" / "idee.md").write_text("# Idee\n\nSpäter.\n", encoding="utf-8")
    (vault / "visibility.md").write_text(
        "# Visibility\n\n- menu.pdf: public\n- fotos/: public-summary\n"
        "- gaeste/: private\n- finanzen/: hidden\n- entwuerfe/: shared\n",
        encoding="utf-8",
    )

    rows = {row["path"]: row for row in seed.build_card(vault)["structure"]}
    assert rows["menu.pdf"]["visibility"] == "public"
    assert rows["menu.pdf"]["digest"]
    assert rows["fotos/zimmer.png"]["visibility"] == "public-summary"
    # private: the folder and how much is in it, and nothing that identifies a guest.
    assert rows["gaeste/"] == {"path": "gaeste/", "files": 2, "visibility": "private"}
    assert "digest" not in rows["gaeste/"] and "bytes" not in rows["gaeste/"]
    assert not [p for p in rows if p.startswith("gaeste/2")], "a private file must not be named"
    # hidden and shared are absent, not flagged: a row saying "secret" is still a row.
    assert not [p for p in rows if p.startswith(("finanzen", "entwuerfe"))]
    # A shared folder's markdown is still not an offer: it was never published.
    assert [row["path"] for row in seed.build_card(vault)["structure"] if row["path"].endswith("idee.md")] == []


def test_every_file_in_the_corpus_is_a_real_file_of_the_type_its_name_claims():
    """A .pdf that is not a PDF makes the digest and the size a lie, and breaks anything that reads it."""
    seed = _seed_vaults()
    seen = Counter()
    for path in sorted(seed.VAULTS.rglob("*")):
        if not path.is_file():
            continue
        seen[path.suffix] += 1
        body = path.read_bytes()
        assert body, f"{path} is empty"
        if path.suffix == ".pdf":
            assert body.startswith(b"%PDF-1."), path
            assert body.rstrip().endswith(b"%%EOF"), path
            assert b"/Root" in body and b"trailer" in body, path
        elif path.suffix == ".png":
            assert body[:8] == b"\x89PNG\r\n\x1a\n", path
            length, chunk = struct.unpack(">I4s", body[8:16])
            assert chunk == b"IHDR" and length == 13, path
            crc = struct.unpack(">I", body[16 + 13 : 20 + 13])[0]
            assert crc == zlib.crc32(body[12 : 16 + 13]) & 0xFFFFFFFF, f"{path} IHDR checksum"
        elif path.suffix == ".csv":
            rows = list(csv.reader(io.StringIO(body.decode("utf-8"))))
            assert len(rows) > 1 and len(rows[0]) > 1, path
        else:
            assert path.suffix in (".md", ".txt"), f"{path} is a type nothing here checks"
    assert seen[".pdf"] and seen[".png"] and seen[".csv"], f"the corpus has no files to connect to: {dict(seen)}"


def test_the_corpus_stays_small_enough_to_live_in_git():
    """Binary test data grows until somebody puts a number on it. This is the number."""
    seed = _seed_vaults()
    total = sum(p.stat().st_size for p in seed.VAULTS.rglob("*") if p.is_file())
    assert total < 400_000, f"{total} bytes of test data is too much for a repository"


def test_no_card_in_the_corpus_quotes_a_file_the_seeder_must_not_read():
    """Shape, never contents, over all 61 real folders and not only a vault built inside a test.

    The seeder now walks every file to measure and hash it, which is exactly the moment a careless
    change could start reading one. So this takes every line of every non-markdown file in the
    corpus and asserts it appears nowhere in the Card that folder produces.
    """
    seed = _seed_vaults()
    checked = 0
    for vault in sorted(p for p in seed.VAULTS.iterdir() if p.is_dir()):
        card = json.dumps(seed.build_card(vault), ensure_ascii=False)
        for file in sorted(vault.rglob("*")):
            if not file.is_file() or file.suffix == ".md":
                continue
            checked += 1
            for raw in file.read_bytes().splitlines():
                line = raw.decode("utf-8", "ignore").strip()
                # Long enough to be a quotation rather than a coincidence of short words.
                if len(line) > 12 and line.isprintable():
                    assert line not in card, f"{file.relative_to(seed.VAULTS)} is quoted in the card"
    assert checked > 100, f"only {checked} files to check: the corpus lost its non-markdown files"
