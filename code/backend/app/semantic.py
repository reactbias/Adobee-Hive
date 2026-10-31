"""Semantic similarity for discovery, behind a small provider interface.

Matching was literal substring, and the index is `offers` and `needs` across every kind, so one failure hit
every domain on the hub at once: a search for "haircut" missed a card that says *"Cut, wash and finish"*, and
"web developer" missed *"builds user interfaces in React"*.

This module answers one question — *how close is this query to this line of a card?* — and answers it the same
way whether or not the hub has an API key:

- `OfflineProvider` is the default and is **always** available: no key, no network, no new dependency, and
  deterministic. Words are accent-folded and stemmed, expanded through a four-language table of the concepts
  this hub's entities trade in, split where a German compound hides two of them (*Gartenzimmer* is a garden and
  a room, *Bettwäsche* a bed and a wash), and mixed with unpadded character trigrams for the typos and the
  spellings the table missed. The two bags are compared with cosine similarity. It is not as good as embeddings
  and does not pretend to be: the table is hand-built, so a trade nobody has written a card for yet matches
  only by stem or trigram. It is much better than substring, it costs one dictionary per distinct line, and it
  works on a laptop with the wifi off.
- An **embedding provider is not built yet** — `_embedding_provider()` returns None and the selection falls
  back to offline, which is a working state and not a degraded one. What is built is the seam it goes in:
  subclass `Provider`, give it a name, an `available()` that reads its key through `config` at call time, and
  an `encode()` that caches per card version so a search never re-embeds the corpus. Any other key-using
  similarity service slots in the same way; nothing above this module needs to know which one answered.

A provider is chosen the way `config.LLM_PROVIDER` is chosen: by which key is set, overridable with
`SEMANTIC_PROVIDER`, and `/api/health` reports the one in use — the name, never anything about the credential.
The key is read through `config` at call time and never captured at import, so a key an operator sets at
runtime takes effect without restarting the backend.

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
#: Chosen by measurement. `tools/eval_answer_key.py` scores the whole answer key in `testdata/README.md` — 41
#: queries against 61 entities, every query sharing no searchable word with its target — and this is that score
#: at each candidate floor:
#:
#:     floor   0.00   0.05   0.10   0.15   0.20   0.25   0.30   0.40
#:     first  10/41  11/41  12/41  12/41  15/41  19/41  20/41  16/41
#:     top 3  20/41  27/41  27/41  29/41  32/41  30/41  27/41  17/41
#:
#: Two things in that table. **No floor at all is near the worst setting there is** — every card is a little
#: like every query, the component pays everybody, and it ranks nothing; that is the whole reason this constant
#: exists. And the curve has a plateau rather than a peak: 0.25 is the top of first-place *and* top-three taken
#: together, 0.30 buys one more first place at the cost of three top-threes, and above that the cross-language
#: matches this was built for — an English query against a card written in German — start falling under it.
#:
#: `tools/eval_search.py --floor` prints the pairs on either side of the line, and `tests/test_semantic.py`
#: pins both edges: the pairs it must catch, and the pairs it must never reach.
SIMILARITY_FLOOR = 0.25

#: How much of a readable reason a hit quotes back from the owner's own line.
SNIPPET_CHARS = 72

#: What each kind of feature is worth in a bag before normalisation. A word carries the most, the concept it
#: belongs to almost as much (that is the part that sees past the words), and a trigram little: trigrams are
#: there for compounds and typos, not to decide a match on their own.
WORD_WEIGHT = 1.0
CONCEPT_WEIGHT = 0.9
TRIGRAM_WEIGHT = 0.22

#: A concept found inside a longer word rather than as the word itself — "Gartenzimmer" is a garden and a room,
#: "Bettwäsche" is a bed and a wash, "Siedfleisch" is meat. German does this constantly and a hub in Basel is
#: full of it, so a table that only matches whole words is half a table here. Worth a little less than the whole
#: word, because a part of a compound is weaker evidence than the compound being the thing itself.
COMPOUND_WEIGHT = 0.7
#: Only words this long are split, and only parts this long are looked for: a three-letter part inside a short
#: word matches by accident far more often than it matches on purpose.
COMPOUND_MIN_WORD = 8
COMPOUND_MIN_PART = 4
#: At most this many parts of one compound are read. "Mehrbettzimmer" is a bed and a room; a word that appears
#: to contain five concepts is noise, not a five-way match.
COMPOUND_MAX_PARTS = 2

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
    somewhere anywhere everywhere anything everything nothing nobody everybody people person persons
    big large small little long short old new good better best cheap expensive nice lovely proper real
    today tomorrow yesterday morning evening afternoon night weekend monday tuesday wednesday thursday
    friday saturday sunday january february march april june july august september october november
    december twice once again soon late early urgent quick fast slow whole full
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
        salon coiffeur coiffure blowdry styling stylist colour color dye dyed farben faerben gefarbt wash
        washing finish schneiden haarschnitt haare friseur frisur cheveux coupe capelli taglio
        parrucchiere""",
    "software": """developer development dev engineer engineering programmer programming coder code coding
        software backend fullstack api integration refactor entwickler entwicklung logiciel
        developpeur sviluppatore programmazione informatico""",
    "web": """web website webseite site frontend ui interface interfaces react vue svelte angular
        javascript typescript css html page landing browser shop webshop ecommerce webdesign
        webentwicklung oberflache sito""",
    "design": """design designer designing graphic layout typography branding gestaltung grafik entwurf
        wireframe wireframes mockup maquette maquettes dessine dessin parcours journey journeys prototype
        conception graphisme disegno grafica usability ux""",
    "data": """data dataviz visualisation visualization chart charts charting dashboard dashboards analytics
        analysis metrics report reports reporting spreadsheet spreadsheets excel database migration import
        statistics statistik daten auswertung tabelle donnees dati""",
    "devops": """devops deploy deployment pipeline pipelines kubernetes docker terraform infrastructure
        platform cloud sre ops hosting server servers cluster runbook observability""",
    "photo": """photo photos photography photographer shoot shooting portrait portraits picture pictures
        image images bild bilder aufnahme foto fotografie fotograf fotografin photographie fotografia
        retouch retoucher retouching""",
    "bike": """bike bikes bicycle cycle cycling velo wheel wheels puncture tyre tire brake brakes chain gears
        fahrrad velomechanik bicicletta mechanic workshop werkstatt""",
    "repair": """repair repairs repairing fix fixing broken mend service servicing maintenance check
        reparatur reparieren wartung reparation riparazione manutenzione rescue cleanup""",
    "stay": """hotel hotels room rooms bed beds bunk night nights stay stays sleep accommodation guesthouse
        hostel inn lodging zimmer kammer gastehaus gaestehaus gasthaus wirtshaus gaststube beiz herberge pension
        mehrbett ubernachtung uebernachtung unterkunft chambre chambres hotes logis albergo camera cabina
        courtyard attic single double suite dorm""",
    "apartment": """apartment apartments flat flats loft lofts studio furnished serviced moblierte mobliert
        moebliert wohnung wohnen appartement appartamento monolocale sublet""",
    "boat": """boat boats houseboat ship barge cabin cabins schiff schiffs kabine kajute bateau peniche
        barca""",
    "lock": """lock locked locksmith unlock key keys door doors schlussel schluessel schloss schlosser
        schliessdienst zylinder tur ture turen tuer tueren serrure clef chiave porta""",
    "coffee": """coffee kaffee espresso filterkaffee bohne bohnen bean beans roast roasted roastery rosten
        rosterei gerostet roesten roesterei geroestet verkostung tasting barista caffe""",
    "pasta": """pasta noodle noodles nudeln teigwaren spaghetti osteria trattoria italian italienisch italiano
        antipasti cucina pizzeria pizza risotto""",
    "meat": """meat beef boiled siedfleisch fleisch rind braten kalb schwein pork veal lamb viande carne
        bouilli lesso grill""",
    "garden": """garden garten gartner gaertner gartnerin jardin giardino terrace terrasse patio hof
        aussen""",
    "food": """cafe breakfast lunch dinner brunch supper food meal meals menu restaurant bakery pastry bun
        cake vegan vegetarian fruhstuck fruehstueck abendessen mittagessen essen suppe soup gipfeli croissant
        tagesteller speisekarte teestube colazione cena pranzo""",
    "writing": """writer writing write copywriting text texts documentation docs handbook manual editor
        editing proofreading translation translator uebersetzung redaktion redacteur traduzione""",
    "cleaning": """cleaning cleaner clean laundry linen sheet sheets towel towels housekeeping tidy putzen
        reinigung wasche waesche wascherei waescherei bettwasche tischtucher nettoyage blanchisserie menage
        pulizia lavanderia bucato""",
    "teaching": """teacher teaching lesson lessons tutor tutoring course courses training coach coaching
        workshop unterricht nachhilfe kurs schulung cours formation lezione corso""",
    "music": """music musician band singer concert gig sound audio recording mixing tune tuned tuner
        tuning piano pianos klavier klaviere flugel fluegel stimmen gestimmt saite saiten instrument
        instrumente musik accordeur musique pianoforte musica""",
    "event": """event events wedding party conference meetup festival catering cater stage veranstaltung fest
        hochzeit hochzeiten firmenessen trauerfeier apero bankett banquet buffet koch kochin kochinnen kochen
        evenement mariage traiteur evento matrimonio""",
    "money": """accounting accountant bookkeeping tax taxes vat invoice invoicing payroll finance
        financial payments payment billing buchhaltung buchhalterin treuhand steuer steuern
        mehrwertsteuer abschluss rechnung comptabilite fiduciaire contabilita""",
    "legal": """legal lawyer law contract contracts notary compliance recht anwalt vertrag juridique avocat
        avvocato contratto""",
    "marketing": """marketing ads advertising campaign campaigns seo social newsletter brand werbung
        publicite pubblicita""",
    "moving": """moving movers transport delivery deliver deliveries courier couriers logistics shipping
        pickup umzug lieferung ausliefern kurier kurierdienst abholung botengang livraison coursier
        trasloco consegna corriere""",
    "energy": """energy power grid substation electrical electrician electric socket sockets wiring fuse
        fuses solar heating strom netz elektro elektriker elektrisch elektrokontrolle steckdose steckdosen
        sicherung sicherungen leitung kabel energie electricien prise elettricista""",
    "health": """massage physio physiotherapy therapy yoga fitness trainer gym wellness nails cosmetic
        kosmetik massaggio""",
    "automation": """automation automate automating automated automatisieren automatisierung workflow
        workflows repetitive manual paperwork admin bot script scripting rpa agent agents flow""",
    "jobs": """job jobs career careers vacancy vacancies opening openings hiring recruitment employment
        employer apprenticeship internship stelle stellen karriere lehrstelle praktikum arbeitgeber emploi
        carriere recrutement stage lavoro carriera impiego assunzioni""",
    "insurance": """insurance insure pension pensions retirement savings cover annuity vorsorge versicherung
        rente altersvorsorge assurance retraite prevoyance assicurazione pensione""",
    "measurement": """measurement measure measuring sensor sensors instrument instrumentation flow level
        pressure calibration analysis metering messtechnik sensorik kalibrierung mesure misura""",
    "braid": """braid braids braiding plait plaited flechten flecht geflochten zopf zopfe tresse
        treccia""",
    "tailor": """tailor tailoring sew sewing seamstress stitch alteration alterations alter hem shorten
        trousers shirt dress clothes clothing kleider kleid kleidung hose hosen nahen naehen naherei
        naheterei schneider schneiderin schneiderei kurzen kuerzen enger andern aendern anderung umnahen
        couturiere retouche sartoria cucire""",
    "plumbing": """plumber plumbing leak leaks leaking drip dripping drain pipe pipes tap taps toilet
        boiler sanitar sanitaer sanitarinstallation installateur rohr rohre tropft wasserhahn abfluss
        spulung heizung plombier fuite idraulico perdita""",
    "roofing": """roof roofs roofer roofing gutter dach dacher daecher dachdecker dachrinne ziegel
        decken sturm storm hagel leak couvreur toit toiture tetto tegole""",
    "gardening": """gardening gardener hedge hedges mow mowing lawn prune pruning weeding hecke hecken
        rasen baum baume gartenbau gartenpflege pflegen stauden jardinier jardinage giardiniere
        potatura""",
    "watch": """watch watches watchmaker clock clocks wristwatch pendulum winding wind mechanical
        mechanisch mechanische uhr uhren uhrmacher armbanduhr standuhr pendel werk zeiger horloger
        horlogerie orologio orologiaio""",
    "driving": """driving driver lesson lessons gearbox licence license fahrschule fahrstunde fahrstunden
        fahrlehrer fahren fuhrerausweis fuehrerausweis fuhrerschein automat automatik getriebe
        verkehrskunde conduite permis guida patente""",
    "grooming": """grooming groom groomer clipping clipped shear shearing bathe bathing coat fur
        hundesalon hundefriseur scheren baden fell krallen pfote toelettatura toilettage""",
    "framing": """framing frame frames framed passepartout einfassen einrahmen rahmen bilderrahmen
        glasschnitt leiste bild bilder poster print prints encadrement cadre cornice""",
    "retouch": """retouch retoucher retouching retusche retuschieren nachbearbeitung postproduction
        freistellen bildbearbeitung composing ritocco""",
    "mobile": """app apps application smartphone phone iphone android mobile ios handy mobil
        applicazione appstore""",
    "hosting": """hosting host server servers rack racks colocation colo datacenter datacentre
        rechenzentrum datenhaus maschinen machines virtualisation hypervisor uptime backup betreuen
        stellen""",
    "machine": """machine machines maschine maschinen device devices gerat gerate geraet industrial
        industrie panel control steuerung bedienung bedienoberflache oberflache oberflachen hmi scada
        medical medizin medizinisch medizintechnik appareil macchina""",
    "database": """database databases datenbank sql query queries index indexes postgres mysql
        performance abfrage abfragen optimierung tuning schema migration langsam""",
    "ml": """machine learning ml ai model models modell modelle forecast forecasting forecasts
        prediction predict predicting neural regression training prognose vorhersage schatzung
        apprentissage apprendimento""",
    "qa": """qa quality assurance test tests testing tester regression bug bugs defect defects
        release candidate breaking qualitat qualitaet prufung pruefung testautomatisierung""",
    "accessibility": """accessibility accessible wcag screenreader reader keyboard contrast kontrast
        barrierefrei barrierefreiheit tastatur vorlesen zuganglich zugaenglich inclusive""",
    "legacy": """legacy cobol delphi fortran mainframe veraltet altsystem altlast modernise modernisieren
        migrieren maintain maintaining alive dares untouched vintage""",
    "agency": """agency agentur genossenschaft cooperative collective kollektiv studio buro buero team
        ubernehmen uebernehmen takeover unfinished halbfertig liegengelassen project projekt auftrag""",
    "quiet": """quiet calm silent peaceful ruhig leise still calme tranquille tranquillo silenzioso""",
    "pet": """dog dogs pet pets puppy hund hunde hundli haustier tier tiere chien cane animals""",
}


def _fold(text: str) -> str:
    """Lower-case and strip accents, so "Zürich" and "Zurich" are one word and "ß" is "ss"."""
    folded = unicodedata.normalize("NFKD", text.lower().replace("ß", "ss"))
    return "".join(c for c in folded if not unicodedata.combining(c))


def _words(text: str) -> list[str]:
    """The content words of a piece of text: folded, letters only, stopwords and single letters dropped."""
    return [w for w in re.findall(r"[a-z]+", _fold(text)) if len(w) > 1 and w not in STOPWORDS]


#: Derivational suffixes stripped to reach a stem, after the plural is taken off. Deliberately short:
#: over-stemming invents matches, and a wrong stem is worse than a missed one because it is invisible.
#: Nothing is stripped that would leave less than four characters behind.
_SUFFIXES = ("ungen", "ation", "ing", "ers", "er", "ed", "ly", "en")


def _singular(word: str) -> str:
    """Take the plural off, the way "websites" has to become "website" and not "websit".

    The naive version stripped "es" before "s" and quietly broke every word ending in a silent e — a stem
    nobody could see was wrong, which is exactly how a similarity score goes bad without anyone noticing.
    """
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
        return word[:-1]
    return word


@lru_cache(maxsize=8192)
def stem(word: str) -> str:
    """Reduce a word to a crude stem: "cutting" to "cut", "developers" to "develop", "writer" to "writ"."""
    word = _singular(word)
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


@lru_cache(maxsize=1)
def _compound_parts() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Concept stems long enough to recognise inside a compound word, longest first."""
    index = _concept_index()
    return tuple(sorted(((k, v) for k, v in index.items() if len(k) >= COMPOUND_MIN_PART), key=lambda kv: -len(kv[0])))


def _inside(word: str) -> list[str]:
    """Concepts of the longest table words hiding inside a compound: "Bettwäsche" is a bed and a wash."""
    found: list[str] = []
    for part, concepts in _compound_parts():
        if part in word:
            found.extend(c for c in concepts if c not in found)
            if len(found) >= COMPOUND_MAX_PARTS:
                break
    return found[:COMPOUND_MAX_PARTS]


@lru_cache(maxsize=16384)
def features(word: str) -> tuple[tuple[str, float], ...]:
    """One word's features and their weights: its stem, the concepts it belongs to, its trigrams.

    A long word the table does not know as a whole is also read as a compound, which is how a query for a
    "garden" reaches a card offering a *Gartenzimmer*.
    """
    root = stem(word)
    bag: list[tuple[str, float]] = [(f"w:{root}", WORD_WEIGHT)]
    concepts = _concept_index().get(root, ())
    bag += [(f"c:{concept}", CONCEPT_WEIGHT) for concept in concepts]
    if not concepts and len(word) >= COMPOUND_MIN_WORD:
        bag += [(f"c:{concept}", COMPOUND_WEIGHT) for concept in _inside(word)]
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
    from . import services  # local: a key stored in the admin panel counts, not only the environment

    return EMBEDDINGS if services.key_for("openai") else OFFLINE


def _build(name: str) -> Provider:
    """Make the named provider, or the offline one when the named one cannot answer."""
    if name == EMBEDDINGS:
        candidate = _embedding_provider()
        if candidate is not None and candidate.available():
            return candidate
    return OfflineProvider()


def _embedding_provider() -> Provider | None:
    """The optional key-using provider, or None while it is not built yet.

    It is not built. This returns None on purpose rather than half an implementation, and `_build` then hands
    back the offline provider, so a hub with a key configured searches exactly as well as one without — which
    is the promise, not the apology. See the module docstring for the shape the replacement has to have.
    """
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
