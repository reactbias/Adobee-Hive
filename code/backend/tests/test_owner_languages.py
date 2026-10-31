"""The owner studio works offline in every UI language: add, remove and price changes in EN, DE, FR and IT."""

import pytest

from app import owner

CARD = {
    "features": ["wifi", "dog-friendly"],
    "policies": {"pets": "Dogs welcome"},
    "units": [
        {"id": "single", "name": "Courtyard single", "price_chf": 128},
        {"id": "double", "name": "Courtyard double", "price_chf": 172},
        {"id": "river", "name": "River-view double", "price_chf": 238},
    ],
}

# The sample sentence each language shows in the owner studio (code/frontend/src/i18n).
SAMPLES = [
    "Add sauna. The courtyard double is 165 francs from today.",
    "Sauna hinzufügen. Das Courtyard-Doppelzimmer kostet ab heute 165 Franken.",
    "Ajouter un sauna. La double côté cour coûte 165 francs dès aujourd'hui.",
    "Aggiungi la sauna. La doppia sul cortile costa 165 franchi da oggi.",
]


@pytest.mark.parametrize("instruction", SAMPLES)
def test_each_language_sample_works_offline(instruction):
    card, summary = owner.mock_edit(CARD, instruction)
    assert "sauna" in card["features"]
    prices = {u["id"]: u["price_chf"] for u in card["units"]}
    assert prices == {"single": 128, "double": 165, "river": 238}
    assert summary["items"] == [
        {"code": "added", "tag": "sauna"},
        {"code": "price", "unit": "Courtyard double", "price_chf": 165},
    ]


@pytest.mark.parametrize(
    "instruction",
    [
        "remove dog-friendly",
        "Hundefreundlich entfernen",
        "Entferne hundefreundlich",
        "Retirer chiens acceptés",
        "Supprimer dog-friendly",
        "Rimuovi cani ammessi",
        "Togli dog-friendly",
    ],
)
def test_remove_in_every_language_maps_to_the_card_tag(instruction):
    card, _ = owner.mock_edit(CARD, instruction)
    assert "dog-friendly" not in card["features"] and card["policies"]["pets"] == "No pets"


@pytest.mark.parametrize(
    "instruction",
    [
        "add vegan breakfast, add coworking",
        "vegan breakfast hinzufügen, coworking hinzufügen",
        "Füge veganes Frühstück hinzu",
        "ajouter vegan breakfast, ajouter coworking",
        "aggiungi colazione vegana, aggiungi coworking",
    ],
)
def test_several_tags_and_translated_tags(instruction):
    card, _ = owner.mock_edit(CARD, instruction)
    assert "vegan breakfast" in card["features"]


def test_nothing_understood_says_so_without_english_text():
    card, summary = owner.mock_edit(CARD, "Bitte alles schöner machen")
    assert card == CARD and summary["items"] == [] and summary["text"].startswith("Mock mode understood nothing")
