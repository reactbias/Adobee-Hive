"""One tokeniser and one stopword list, across four languages.

Two bugs found by typing plain sentences at the hub instead of keywords, both in the same place — the
literal search had its own idea of what a word is:

- Filler words were evidence (#151). `hive.STOPWORDS` was 21 words where `semantic.STOPWORDS` was 323, and
  the literal path is the one that pays 10 points for a word it finds on the offers side. So a
  screen-reader auditor came second for a Python performance request on *"offers someone"*, and the single
  card that scored for *"Ich suche jemanden, der meine Python-Simulation schneller macht"* was a roofer,
  on "macht".
- German, French and Italian queries were silently unusable (#153). The tokeniser was
  `re.findall(r"[a-zäöü]+", q.lower())`: a hand-written list of the letters somebody remembered, which
  dropped `é à è ù ò ç` and every upper-case umlaut, so "café" tokenised to nothing at all.

Both are now `semantic.content_words`, used by both paths, and these tests pin that it stays one of each.
The corpus is deliberately four languages; a search that only reads one of them reads a quarter of it.
"""

from __future__ import annotations

import pytest

from app import hive, semantic


@pytest.fixture(scope="module")
def corpus(client):
    """Four cards, one per language of the corpus, each offering something the others do not.

    Published here rather than read out of `testdata/vaults/`, so these tests pin the *mechanism* and
    cannot be quietly fixed or broken by someone editing a vault.
    """
    cards = [
        {
            "id": "t-de-app",
            "slug": "t-de-app",
            "kind": "person",
            "name": "Basil Zürcher",
            "tagline": "Apps für iPhone und Android",
            "description": "Ich baue Apps für beide Systeme aus einer Codebasis.",
            "offers": ["Eine App für beide Systeme, aus einer Codebasis"],
        },
        {
            "id": "t-fr-maquette",
            "slug": "t-fr-maquette",
            "kind": "person",
            "name": "Fabienne Roulet",
            "tagline": "Maquettes et parcours",
            "description": "Je dessine des maquettes cliquables, à Zurich.",
            "offers": ["Maquettes cliquables pour une application mobile"],
        },
        {
            "id": "t-it-react",
            "slug": "t-it-react",
            "kind": "person",
            "name": "Ilaria Conti",
            "tagline": "Interfacce React",
            "description": "Mi occupo di interfacce React da sette anni.",
            "offers": ["Revisione del codice di un team, una settimana"],
        },
        {
            "id": "t-en-cafe",
            "slug": "t-en-cafe",
            "kind": "cafe",
            "name": "Café Rhein",
            "tagline": "Vegan breakfast by the river",
            "description": "A quiet café with a vegan breakfast served all day.",
            "offers": ["Vegan breakfast — CHF 18, served all day"],
        },
    ]
    for card in cards:
        hive.publish(dict(card))
    return [c["id"] for c in cards]


def _ranked(query: str, **kwargs) -> list[str]:
    """The ids that actually scored for a query, best first. A score of zero is not an answer."""
    found = hive.discover(query=query, **kwargs)
    return [m["id"] for m in found["matches"] if m["score"] > 0]


# --- one list, one tokeniser ---------------------------------------------------------------------


def test_there_is_exactly_one_stopword_list():
    """`hive.STOPWORDS` is `semantic.STOPWORDS`, not a copy of it and not a shorter cousin.

    Identity, not equality: two lists that are equal today drift apart on the next commit, which is
    precisely what happened — the hub-specific list stopped at 21 words and nobody noticed that the two
    search paths had started disagreeing about what a word means.
    """
    assert hive.STOPWORDS is semantic.STOPWORDS


@pytest.mark.parametrize(
    "filler",
    # The words the two user tests actually caught scoring, in the four languages of the corpus.
    ["where", "someone", "need", "my", "slow", "macht", "jemanden", "meine", "suche", "pour", "cherche", "vorrei"],
)
def test_a_filler_word_is_filler_to_both_search_paths(filler):
    """No query word in this list is evidence about a card, on either path."""
    assert filler in semantic.STOPWORDS
    assert semantic.content_words(filler) == []
    assert hive.query_terms(f"{filler} {filler}") == []


@pytest.mark.parametrize(
    "errand",
    # The other half of the bargain: a generic word that still says what the errand is stays a word.
    # These sat in the old `hive.STOPWORDS` and dropping them for good would cost the answer key.
    ["hotel", "room", "breakfast", "haircut", "developer", "maquettes", "codice"],
)
def test_a_word_that_names_the_errand_is_not_filler(errand):
    """ "Generic" is not "meaningless": a card that offers a room differs from one that does not."""
    assert errand not in semantic.STOPWORDS
    assert hive.query_terms(errand) == [errand]


def test_the_letter_class_is_not_a_list_of_remembered_letters():
    """Tokenising is "a run of letters", not "a run of the letters someone thought of".

    `[a-zäöü]` was the bug, and adding `é à è ù ò ç` to it would only be the same bug with a longer list.
    So this checks the general property on a script nobody had in mind at all: Greek is text, not
    whitespace. Digits and underscores are still not letters.
    """
    assert semantic.LETTERS.findall("σχεδιασμός") == ["σχεδιασμός"]
    assert semantic.LETTERS.findall("ελληνικά 42_x") == ["ελληνικά", "x"]
    assert semantic.LETTERS.findall("2026-12-04") == []


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("café", ["cafe"]),  # the whole of #153 in one case: this used to tokenise to nothing
        ("CAFÉ", ["cafe"]),
        ("Café", ["cafe"]),
        ("développeur", ["developpeur"]),
        ("accélérer", ["accelerer"]),
        ("ZÜRICH", []),  # a place name, and folded before the stopword list is consulted
        ("Zürich", []),
        ("Grüezi, ich bräuchte MASSAGEN", ["massagen"]),  # greeting, modal, and the one real word
        ("Straße", ["strasse"]),  # ß folds to ss, so one word and not two
        ("città", ["citta"]),
        ("niño", ["nino"]),
    ],
)
def test_case_and_accents_are_folded_before_matching_not_after(query, expected):
    """Every accent and every upper-case umlaut survives tokenising as its folded letter.

    Upper case mattered as much as the accents: the old class was lower-case-only *and* applied to
    `q.lower()`, so it happened to work — until a word carried an accent, where lower-casing is not
    folding and `é` was simply not a letter.
    """
    assert hive.query_terms(query) == expected


# --- folding is half of a comparison ------------------------------------------------------------


def test_an_accented_query_literally_matches_an_accented_card(corpus):
    """ "café" finds the Café, and folding the query alone would have broken this rather than fixed it.

    The haystack folds with the same function as the needle. Fold one side only and a query for "café"
    becomes "cafe", which is not a substring of "Café" — a tokeniser fix that made search worse.
    """
    assert "t-en-cafe" in _ranked("café")
    assert "t-en-cafe" in _ranked("CAFÉ")
    # And the mirror case: an unaccented query still finds the accented card.
    assert "t-en-cafe" in _ranked("cafe")
    why = [m["why"] for m in hive.discover(query="café")["matches"] if m["id"] == "t-en-cafe"][0]
    assert any("cafe" in reason for reason in why), why


def test_an_accent_inside_an_offer_is_found_literally_on_the_offers_side(client):
    """The offers side folds too, and that is a different code path from the prose blob.

    Worth its own test because the obvious case hides it: "Café Rhein" has the accent in its *name*,
    which the prose blob carries, so a search for "café" scores through `text_relevance` whether
    `_side_hits` folds or not. Only an accented word that appears nowhere but in an offer tells the two
    apart — and `offers_needs` is the component that pays 10 a word, so it is the one that matters.
    """
    hive.publish(
        {
            "id": "t-accent-offer",
            "slug": "t-accent-offer",
            "kind": "person",
            "name": "Zweiunddreissig",  # deliberately nothing to match on
            "offers": ["Crème brûlée für zwei", "Apéro riche für fünfzig"],
        }
    )
    for query in ("crème brûlée", "CRÈME BRÛLÉE", "creme brulee", "apéro"):
        scored = {m["id"]: m for m in hive.discover(query=query)["matches"] if m["score"] > 0}
        assert "t-accent-offer" in scored, (query, sorted(scored))
        assert scored["t-accent-offer"]["score_breakdown"]["offers_needs"] > 0, (query, scored["t-accent-offer"])


def test_an_umlaut_in_a_card_is_found_by_a_query_without_one(corpus):
    """A German card is findable by someone who cannot type an umlaut, and by someone who can."""
    assert "t-de-app" in _ranked("Codebasis")
    assert "t-de-app" in _ranked("codebasis")


# --- the two user tests, as regressions ----------------------------------------------------------


def test_filler_words_buy_no_relevance_at_all(corpus):
    """A sentence made only of filler words earns nobody a point of relevance, in any of the four languages.

    The point of #151: these are not low-scoring queries, they are queries with no evidence in them, and a
    hub that finds evidence in them is making the answer up. Checked against the four relevance components
    rather than against the total, because reputation is not relevance — an entity with verified reviews
    still carries them, and whether a reputation-only row may be called a match at all is #152's question,
    not this one's.
    """
    relevance = ("constraints", "text_relevance", "offers_needs", "semantic", "proximity")
    for nothing in (
        "I need someone to do this for me",
        "Ich suche jemanden, der das für mich macht",
        "Je cherche quelqu'un pour faire cela",
        "Cerco qualcuno che lo faccia",
        "where can I find someone",
    ):
        for match in hive.discover(query=nothing)["matches"]:
            earned = {k: v for k, v in match["score_breakdown"].items() if k in relevance and v}
            assert not earned, (nothing, match["id"], earned)
            assert match["why"] == [] or not match["why"][0].startswith(("offers", "needs", "mentions"))


def test_a_question_word_does_not_decide_who_answers(corpus):
    """Asking the same thing as a question and as a keyword finds the same entity.

    "Wo", "où" and "dove" are in every question and say nothing about the errand, so they must not
    reorder the answers. They did: an interrogative was a content word worth 10 points on a card that
    happened to contain it.
    """
    assert _ranked("Wo finde ich jemanden für Codebasis?")[:1] == _ranked("Codebasis")[:1]
    assert _ranked("Où puis-je trouver des maquettes ?")[:1] == _ranked("maquettes")[:1]
    assert _ranked("Dove trovo una revisione del codice?")[:1] == _ranked("revisione codice")[:1]


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("Ich brauche eine App für iPhone und Android", "t-de-app"),
        ("Wer kann mir eine App aus einer Codebasis bauen?", "t-de-app"),
        ("Je cherche quelqu'un pour des maquettes cliquables", "t-fr-maquette"),
        ("J'ai besoin d'une maquette pour une application mobile", "t-fr-maquette"),
        ("Vorrei una revisione del codice", "t-it-react"),
        ("Cerco una revisione del codice del mio team", "t-it-react"),
        ("a café with a vegan breakfast", "t-en-cafe"),
        ("Gibt es ein Café mit veganem Frühstück?", "t-en-cafe"),
    ],
)
def test_a_question_asked_in_the_cards_own_language_finds_it_first(corpus, query, expected):
    """#153: a German, French or Italian question ranks its own-language card first.

    Four languages in the corpus was a deliberate choice, and a tokeniser that reads one of them makes
    three quarters of it undiscoverable without telling anybody.
    """
    assert _ranked(query)[:1] == [expected]


def test_a_word_too_short_to_be_evidence_is_not_a_literal_term():
    """A three-letter word is inside somebody's prose by accident, and the literal path pays 10 a word.

    `MIN_TERM_LENGTH` is the guard. Short words still reach the similarity bag, which weighs them against
    a whole line instead of paying a flat rate for containing them.
    """
    assert hive.query_terms("cab bus van") == []
    assert hive.query_terms("taxi") == ["taxi"]
    assert "cab" in semantic.content_words("cab bus van")


def test_a_tie_on_points_goes_to_the_closer_match(client):
    """When the points cannot separate two entities, the one more like the question wins.

    The semantic component pays a whole number of points per query word covered, so ties are the normal
    case rather than the rare one — nine lodgings cover "hostel, bunk, beds" identically. The sort used to
    settle them by whatever order `list_cards` returned, which is how a hairdresser's *"Flechtfrisur für
    ein Fest"* came ahead of a caterer for "catering for a wedding of fifty people": same two words
    covered, same points, and the hairdresser happened to be published first.

    Slugged so that corpus order and closeness disagree: `list_cards` orders by slug, so the weaker
    match sorts first and a scorer that ignores closeness returns it first. Getting this backwards is
    how the test passed against the bug it was written for — "published in the wrong order" is not the
    same thing as "sorts in the wrong order", and only the slug decides.
    """
    query = "catering for a wedding of fifty people"
    weaker, closer = "t-tie-aaa-hair", "t-tie-zzz-cook"
    for card_id, offer in [(weaker, "Flechtfrisur für ein Fest"), (closer, "Eine Köchin für einen Abend")]:
        hive.publish({"id": card_id, "slug": card_id, "kind": "person", "name": card_id, "offers": [offer]})
    # The precondition the test rests on: the weaker match really is the one slug order puts first.
    assert [c["id"] for c in hive.list_cards() if c["id"].startswith("t-tie-")] == [weaker, closer]

    scored = {m["id"]: m for m in hive.discover(query=query)["matches"] if m["score"] > 0}
    assert {weaker, closer} <= set(scored), scored.keys()
    # Tied on points, which is the precondition for the test meaning anything.
    assert scored[weaker]["score"] == scored[closer]["score"]
    # And the closer of the two really is the cook, so closeness is a signal here and not a coin flip.
    hair = semantic.best(query, ["Flechtfrisur für ein Fest"])
    cook = semantic.best(query, ["Eine Köchin für einen Abend"])
    assert cook.score > hair.score

    order = [m["id"] for m in hive.discover(query=query)["matches"]]
    assert order.index(closer) < order.index(weaker)


def test_the_requesters_own_words_about_themselves_are_not_evidence(corpus):
    """Adding filler around a real question does not change who answers it, or in what order."""
    bare = _ranked("maquettes cliquables")
    padded = _ranked("Bonjour, je cherche quelqu'un qui pourrait me faire des maquettes cliquables, merci !")
    assert bare and padded[: len(bare)] == bare
