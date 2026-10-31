"""Semantic similarity for discovery, behind a small provider interface.

Matching was literal substring, and the index is `offers` and `needs` across every kind, so one failure hit
every domain on the hub at once: a search for "haircut" missed a card that says *"Cut, wash and finish"*, and
"web developer" missed *"builds user interfaces in React"*.

This module answers one question — *how close is this query to this line of a card?* — and answers it the same
way whether or not the hub has an API key:

- `OfflineProvider` is the default and is **always** available: no key, no network, no new dependency, and
  deterministic. Words are accent-folded and stemmed, expanded through a small four-language concept table, and
  mixed with unpadded character trigrams (which is what carries German compounds and typos). The two bags are
  compared with cosine similarity. It is not as good as embeddings and does not pretend to be; it is
  meaningfully better than substring at the mismatches above, and it costs one dictionary per distinct line.
- `EmbeddingProvider` is used only when a key is configured, reached the way `llm.py` reaches a model, with the
  vectors cached per card version so a search never re-embeds the corpus.

A provider is chosen the way `config.LLM_PROVIDER` is chosen: by which key is set, overridable with
`SEMANTIC_PROVIDER`, and `/api/health` reports the one in use. The key is read through `config` at call time and
never captured at import, so a key an operator sets at runtime takes effect without restarting the backend.

Nothing here decides ranking. `hive.discover()` turns a hit into one score component beside `offers_needs` and
`text_relevance`, and into a reason a person can read; a literal hit still outranks a merely similar one.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from . import config

#: A bag of weighted features. The offline provider's keys are words, concepts and trigrams; an embedding
#: provider's are dimension indices. Both are compared with the same cosine, so neither leaks into the caller.
Vector = dict[str, float]

#: The provider names, as `/api/health` reports them and as `SEMANTIC_PROVIDER` accepts them.
OFFLINE = "offline"
EMBEDDINGS = "embeddings"

#: How similar two pieces of text have to be before the hub calls it a match at all.
#:
#: Chosen by measurement, not by taste. `tools/eval_search.py --floor` prints the similarity of every
#: query-against-line pair in the evaluation corpus, split into the pairs that should match and the pairs that
#: must not, and the two sets are far apart: unrelated pairs score 0.00 and sit below 0.02 even when they share
#: a word root, while the pairs this was built for — "haircut" against *"Cut, wash and finish"* (0.53) and
#: "web developer" against *"builds user interfaces in React"* (0.29) — clear 0.28. The floor sits in that gap,
#: just under the weakest pair it has to catch. It is deliberately on the strict side: a missed near-match
#: costs one result, while a floor low enough to let the noise in makes every card similar to every query, turns
#: the semantic component into a constant, and ranking becomes noise. The cost is written down —
#: `KNOWN_MISSES` in `tests/test_semantic.py` lists the true matches this floor gives up.
SIMILARITY_FLOOR = 0.25

#: How much of a readable reason a hit quotes back from the owner's own line.
SNIPPET_CHARS = 72

#: What each kind of feature is worth in a bag before normalisation. A word carries the most, the concept it
#: belongs to almost as much (that is the part that sees past the words), and a trigram little: trigrams are
#: there for compounds and typos, not to decide a match on their own.
WORD_WEIGHT = 1.0
CONCEPT_WEIGHT = 0.9
TRIGRAM_WEIGHT = 0.22

#: Function words, units and place names: they are in every card, so they say nothing about what it offers.
#: Place names are dropped for the same reason `domains/explore.py` ignores them — "near Basel" is not a topic.
STOPWORDS = frozenset(
    """
    a an the and or of for to in on at by with without from into over under near about that this these those
    is are was were be been being have has had do does did can could would should will shall may might must
    it its they them their you your we our us i me my mine he she his her as not no nor but if then than so
    such some any all each every more most much many few less least other another same own very just also only
    need needs needed want wants wanted looking look find finds searching search someone somebody something
    chf eur euro franken hour hours day days half week weeks month months year years time per price prices cost
    costs free next about around also please thanks
    basel bern zurich zuerich luzern geneva genf schweiz switzerland swiss
    und oder der die das den dem des ein eine einen einer einem eines mit ohne fuer auf aus bei nach von vor
    zu zum zur im ist sind war waren sein haben hat hatte wir ich du sie er es nicht kein keine auch noch
    schon sehr mehr etwas jemand brauche suche moechte gibt
    le la les un une des du de et ou pour avec sans dans sur chez par au aux ce cette ces est sont nous vous je
    tu il elle on ne pas plus tres cherche besoin quelque quelqu
    lo gli un uno una dei delle del della con senza su da al alla allo siamo piu molto cerco qualcosa vorrei
    """.split()
)

#: A small four-language concept table: the one thing in here that sees past the words. A concept is a bag of
#: surface forms that mean roughly the same errand on a hub like this one, so a query lands on the concept and
#: the card's own words land on it too. It is hand-built and it is a *table*, with all the honesty that implies:
#: it knows the errands the hub carries and nothing else, and a word outside it can still match only by its stem
#: or its trigrams. Keeping a concept narrow matters more than covering everything — a broad concept makes
#: everything similar to everything, which is the floor's problem all over again.
CONCEPTS: dict[str, str] = {
    "haircut": """haircut hair cut cutting trim trimming shave shaving beard barber hairdresser hairdressing
        salon coiffeur blowdry styling colour color dye wash washing finish haarschnitt haare friseur
        coiffure cheveux coupe capelli taglio parrucchiere""",
    "software": """developer development dev engineer engineering programmer programming coder code coding
        software backend fullstack api integration refactor entwickler entwicklung logiciel
        developpeur sviluppatore programmazione informatico""",
    "web": """web website webseite site frontend ui interface interfaces react vue svelte angular javascript
        typescript css html page landing browser webdesign webentwicklung sito""",
    "design": """design designer designing graphic layout typography branding gestaltung grafik entwurf
        conception graphisme disegno grafica usability ux""",
    "data": """data dataviz visualisation visualization chart charts charting dashboard dashboards analytics
        analysis metrics reporting statistics statistik daten auswertung donnees dati""",
    "devops": """devops deploy deployment pipeline pipelines kubernetes docker terraform infrastructure
        platform cloud sre ops hosting server servers cluster runbook observability""",
    "photo": """photo photos photography photographer shoot shooting portrait portraits picture pictures
        image images foto fotografie fotograf photographie fotografia retouch retoucher retouching""",
    "bike": """bike bikes bicycle cycle cycling velo wheel wheels puncture tyre tire brake brakes chain gears
        fahrrad velomechanik bicicletta mechanic workshop werkstatt""",
    "repair": """repair repairs repairing fix fixing broken mend service servicing maintenance check
        reparatur reparieren wartung reparation riparazione manutenzione rescue cleanup""",
    "stay": """hotel hotels room rooms bed beds night nights stay stays sleep accommodation guesthouse pension
        hostel inn lodging zimmer uebernachtung unterkunft chambre albergo camera courtyard attic single
        double suite studio""",
    "food": """cafe coffee breakfast lunch dinner brunch food meal meals menu restaurant bakery pastry bun
        cake vegan vegetarian fruehstueck kaffee essen kuchen colazione caffe cucina""",
    "writing": """writer writing write copywriting text texts documentation docs handbook manual editor
        editing proofreading translation translator uebersetzung redaktion redacteur traduzione""",
    "cleaning": """cleaning cleaner clean laundry housekeeping tidy putzen reinigung waesche nettoyage
        menage pulizia""",
    "teaching": """teacher teaching lesson lessons tutor tutoring course courses training coach coaching
        workshop unterricht nachhilfe kurs schulung cours formation lezione corso""",
    "music": """music musician band singer concert gig sound audio recording mixing musik musique musica""",
    "event": """event events wedding party conference meetup festival catering stage veranstaltung fest
        hochzeit evenement evento""",
    "money": """accounting accountant bookkeeping tax taxes invoice invoicing payroll finance financial
        payments payment billing buchhaltung steuer rechnung comptabilite contabilita""",
    "legal": """legal lawyer law contract contracts notary compliance recht anwalt vertrag juridique avocat
        avvocato contratto""",
    "marketing": """marketing ads advertising campaign campaigns seo social newsletter brand werbung
        publicite pubblicita""",
    "moving": """moving movers transport delivery courier logistics shipping umzug lieferung livraison
        trasloco consegna""",
    "energy": """energy power grid substation electrical electrician solar heating strom netz elektriker
        heizung energie elettricista""",
    "health": """massage physio physiotherapy therapy yoga fitness trainer gym wellness nails cosmetic
        kosmetik massaggio""",
    "quiet": """quiet calm silent peaceful ruhig leise still calme tranquille tranquillo silenzioso""",
    "pet": """dog dogs pet pets puppy hund hunde haustier chien cane animals""",
}


def _fold(text: str) -> str:
    """Lower-case and strip accents, so "Zürich" and "Zurich" are one word and "ß" is "ss"."""
    folded = unicodedata.normalize("NFKD", text.lower().replace("ß", "ss"))
    return "".join(c for c in folded if not unicodedata.combining(c))


def _words(text: str) -> list[str]:
    """The content words of a piece of text: folded, letters only, stopwords and single letters dropped."""
    return [w for w in re.findall(r"[a-z]+", _fold(text)) if len(w) > 1 and w not in STOPWORDS]


#: Suffixes stripped to reach a stem, longest first. Deliberately short: over-stemming invents matches, and a
#: wrong stem is worse than a missed one because it is invisible. Nothing is stripped below four characters.
_SUFFIXES = ("ungen", "ation", "ingly", "ies", "ing", "ers", "ed", "er", "es", "en", "ly", "s")


@lru_cache(maxsize=8192)
def stem(word: str) -> str:
    """Reduce a word to a crude stem: "cutting" to "cut", "developers" to "develop", "offers" to "offer"."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            word = word[: -len(suffix)]
            break
    if len(word) >= 4 and word[-1] == word[-2]:  # "cutt" after "cutting"
        word = word[:-1]
    return word


@lru_cache(maxsize=1)
def _concept_index() -> dict[str, tuple[str, ...]]:
    """Stem to the concepts it belongs to, built once from CONCEPTS."""
    index: dict[str, set[str]] = {}
    for concept, words in CONCEPTS.items():
        for word in words.split():
            index.setdefault(stem(_fold(word)), set()).add(concept)
    return {key: tuple(sorted(value)) for key, value in index.items()}


def _trigrams(word: str) -> list[str]:
    """Unpadded character trigrams: unpadded on purpose, so "haircut" and "cut" share one."""
    return [word[i : i + 3] for i in range(len(word) - 2)] if len(word) >= 3 else []


@lru_cache(maxsize=8192)
def features(word: str) -> tuple[tuple[str, float], ...]:
    """One word's features and their weights: its stem, the concepts it belongs to, its trigrams."""
    root = stem(word)
    bag: list[tuple[str, float]] = [(f"w:{root}", WORD_WEIGHT)]
    bag += [(f"c:{concept}", CONCEPT_WEIGHT) for concept in _concept_index().get(root, ())]
    bag += [(f"g:{gram}", TRIGRAM_WEIGHT) for gram in _trigrams(word)]
    return tuple(bag)


def _bag(text: str) -> Vector:
    """The un-normalised feature bag of a piece of text."""
    vector: Vector = {}
    for word in _words(text):
        for key, weight in features(word):
            vector[key] = vector.get(key, 0.0) + weight
    return vector


def _unit(vector: Vector) -> Vector:
    """Scale a bag to unit length, so a cosine is a plain dot product and length stops mattering."""
    norm = math.sqrt(sum(value * value for value in vector.values()))
    return {key: value / norm for key, value in vector.items()} if norm else {}


@dataclass(frozen=True)
class Hit:
    """One semantic match: how close, which line of the card, and the query words that carried it.

    `terms` and `snippet` exist so a result can explain itself. "Open ranking" means a person reads why
    something matched, and a bare number is not a reason.
    """

    score: float
    text: str
    terms: tuple[str, ...]

    @property
    def snippet(self) -> str:
        """The matched line, clipped to something a reason can quote: the owner's words, no price tail."""
        plain = re.split(r"\s+[—–-]\s+", " ".join(self.text.split()))[0].strip(" .,:;")
        if len(plain) > SNIPPET_CHARS:
            plain = plain[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"
        return plain


class Provider:
    """A source of semantic similarity: turn text into a vector, and compare two vectors.

    The interface every provider implements, offline or key-using, so `hive.discover()` never knows which one
    answered. A new key-using service slots in beside `EmbeddingProvider` by subclassing this: give it a name,
    an `available()` that reads its key through `config` at call time, and an `encode()`.
    """

    name = OFFLINE

    def available(self) -> bool:
        """Whether this provider can answer right now. The offline one always can."""
        return True

    def encode(self, text: str) -> Vector:
        """Turn a piece of text into a unit-length vector."""
        raise NotImplementedError

    def similarity(self, left: Vector, right: Vector) -> float:
        """Cosine similarity of two unit vectors: 0 for nothing in common, 1 for the same text."""
        if not left or not right:
            return 0.0
        small, large = (left, right) if len(left) <= len(right) else (right, left)
        dot = sum(weight * large.get(key, 0.0) for key, weight in small.items())
        return max(0.0, min(1.0, dot))

    def terms(self, query: str, vector: Vector) -> tuple[str, ...]:
        """The query words that contributed most to a match, for the reason a result gives.

        The default is honest about what a provider cannot see: the query's own content words, best first by
        whatever the provider's vector can attribute. A provider that cannot attribute anything says so by
        returning the words in the order they were typed.
        """
        return tuple(dict.fromkeys(_words(query)))[:3]


class OfflineProvider(Provider):
    """The provider the demo runs on: stems, a concept table and character trigrams, compared with cosine.

    Always available, no key, no network, no new dependency, deterministic. Vectors are cached per distinct
    piece of text, so a second search over the same corpus costs almost nothing.
    """

    name = OFFLINE

    def encode(self, text: str) -> Vector:
        """Vector of one piece of text. Cached per text: the corpus is encoded once, not once per query."""
        return _encode_offline(text)

    def terms(self, query: str, vector: Vector) -> tuple[str, ...]:
        """The query words with the largest overlap with `vector`, best first."""
        scored = []
        for word in dict.fromkeys(_words(query)):
            share = sum(weight * vector.get(key, 0.0) for key, weight in features(word))
            if share > 0:
                scored.append((share, word))
        return tuple(word for _, word in sorted(scored, reverse=True))[:3]


@lru_cache(maxsize=4096)
def _encode_offline(text: str) -> Vector:
    """Cached offline vector. A module-level cache, so every provider instance shares one corpus."""
    return _unit(_bag(text))


def cache_info() -> dict[str, int]:
    """Hits and misses of the text-vector cache, for the eval harness and the cache test."""
    info = _encode_offline.cache_info()
    return {"hits": info.hits, "misses": info.misses, "size": info.currsize}


_provider: Provider | None = None


def _wanted() -> str:
    """Which provider the configuration asks for right now, read fresh so a runtime key takes effect."""
    pinned = (getattr(config, "SEMANTIC_PROVIDER", "") or "").strip().lower()
    if pinned:
        return pinned
    return EMBEDDINGS if getattr(config, "OPENAI_API_KEY", "") else OFFLINE


def _build(name: str) -> Provider:
    """Make the named provider, or the offline one when the named one cannot answer."""
    if name == EMBEDDINGS:
        candidate = _embedding_provider()
        if candidate is not None and candidate.available():
            return candidate
    return OfflineProvider()


def _embedding_provider() -> Provider | None:
    """The optional key-using provider, or None while it is not built yet."""
    return None


def provider() -> Provider:
    """The provider in use, rebuilt when the configuration changes under it.

    Selection follows `config.LLM_PROVIDER`: by which key is set, overridable with `SEMANTIC_PROVIDER`. A
    provider that cannot answer is never returned — the offline one answers instead, which is a first-class
    state and not a degraded one.
    """
    global _provider
    wanted = _wanted()
    if _provider is None or (_provider.name != wanted and wanted in (OFFLINE, EMBEDDINGS)):
        _provider = _build(wanted)
    return _provider


def reset() -> None:
    """Forget the selected provider, so the next call re-reads the configuration. Used by tests and admin."""
    global _provider
    _provider = None


def status() -> dict[str, Any]:
    """What `/api/health` reports: which provider is in use and the floor it matches at. Never the key."""
    chosen = provider()
    return {"provider": chosen.name, "floor": SIMILARITY_FLOOR}


def best(query: str, texts: list[str], using: Provider | None = None) -> Hit | None:
    """The closest of `texts` to `query`, or None when nothing clears the floor.

    None rather than the least bad line: an honest "nobody offers this" is a promise the hub already keeps
    elsewhere, and a nearest-card answer would quietly break it.
    """
    engine = using or provider()
    query_vector = engine.encode(query)
    if not query_vector or not texts:
        return None
    hit: Hit | None = None
    for text in texts:
        score = engine.similarity(query_vector, engine.encode(text))
        if score >= SIMILARITY_FLOOR and (hit is None or score > hit.score):
            hit = Hit(score=score, text=text, terms=engine.terms(query, engine.encode(text)))
    return hit
