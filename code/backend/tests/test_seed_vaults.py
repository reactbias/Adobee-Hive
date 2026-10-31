"""The vault folders are the demo's real data, and what they say they do and need is the index.

tools/seed_vaults.py registers `testdata/vaults/*/` through the signup endpoint. These tests pin that the two
sides of the market are *parsed out of the owner's own markdown* — the folder stays the single source of truth —
and that a card built that way is actually findable by what it offers and by what it needs.
"""

from __future__ import annotations

import importlib.util
import sys
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
