"""Write the test corpus in `testdata/vaults/` from one curated table of fictional entities.

Sixty hand-written folders drift: one says "haircut" where the next says "Cut and finish", and
nobody can see the shape of the whole corpus. So the content is curated *here*, as prose written
per entity, and the folders are emitted from it. Both the table and the folders are committed, so
a reviewer reads the table and the seeder reads the folders.

This corpus exists to be searched, and specifically to show where literal matching gives up.
`hive.discover` scores a card by substring: a query term appears in the card's text or it does not.
So the entities below say "Cut, wash and finish" and never "haircut", "builds interfaces" and never
"frontend developer", "Gästehaus" and never "hotel". `testdata/README.md` is the answer key — the
query a person would really type next to the entity it should return — and
`tests/test_seed_vaults.py` pins that those queries share no searchable word with their target, so
the key stays honest as the corpus changes.

    python tools/make_corpus.py                  # write every folder
    python tools/make_corpus.py --hub basel      # one hub's folders
    python tools/make_corpus.py --check          # fail if a folder on disk drifted from the table
    python tools/make_corpus.py --print-maps     # the HOME, KIND and UNCLAIMED blocks for seed_vaults.py

The ten folders that predate this file (`PRE_EXISTING`) are hand-written and stay that way; the
generator refuses to touch them.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VAULTS = ROOT / "testdata" / "vaults"

#: The hand-written folders this generator must never overwrite. They were the first ten and they
#: are what the parser was built against, so they stay the reference.
PRE_EXISTING = frozenset(
    {
        "aylin-dervis",
        "cafe-rhein",
        "grid-ops",
        "hotel-krafft",
        "lena-hofmann",
        "lichtfeld-foto",
        "niko-ferrer",
        "pension-limmat",
        "schnittwerk-bern",
        "velowerk-bern",
    }
)

#: The kinds the backend accepts. `hotel` and `cafe` are the stay kinds (hive.STAY_KINDS), so only
#: those two are bookable; a person is introduced and a service is contacted.
KINDS = ("hotel", "cafe", "person", "service")


@dataclass(frozen=True)
class Entity:
    """One curated member of the corpus: the prose, and which hub and kind it registers as.

    `offers` and `needs` are the bullet lines under the two headings the seeder's parser reads, so
    they are the entity's whole index. `rooms` makes a stay bookable. `contact` lines are written
    verbatim into contact.md, so "ask first" and "never" exercise the sharing flags. `reviews` is
    owner-written prose in a file of its own, under a heading the parser ignores.
    """

    slug: str
    name: str
    hub: str
    kind: str
    about: str
    offers: tuple[str, ...] = ()
    needs: tuple[str, ...] = ()
    rooms: tuple[str, ...] = ()
    contact: tuple[str, ...] = ()
    reviews: tuple[str, ...] = ()
    #: Heading over `offers`. "What we do", "What I do", "What we offer" — the parser takes any of
    #: them, and a corpus where every folder picks the same one tests less than one that varies.
    offer_heading: str = "What we do"
    #: File the offers go in: work.md for a worker, menu.md for somewhere you eat.
    offer_file: str = "work.md"
    #: True for a card compiled from public information rather than written by its subject. The
    #: hub reports it as unclaimed and refuses to treat it as a business that agreed to anything.
    unclaimed: bool = False
    extra: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- basel
# Stays and hospitality. Almost nothing here says "hotel", "guesthouse", "bed and breakfast" or
# "lunch" — that is the point: those are the words a guest types, not the words an owner writes.

BASEL: tuple[Entity, ...] = (
    Entity(
        slug="wirtshaus-anker",
        name="Wirtshaus zum Anker",
        hub="basel",
        kind="hotel",
        about="Sieben Zimmer über der Gaststube in Kleinbasel. Die Küche schliesst um zehn, die "
        "Treppe knarrt, und bis zum Rhein sind es zwei Minuten zu Fuss.",
        rooms=(
            "Kammer unter dem Dach — 1 guest, CHF 95, 2 of them. Steile Treppe, kein Lift.",
            "Doppelkammer — 2 guests, CHF 150, 3 of them.",
            "Familienkammer — 4 guests, CHF 210, 1 of them.",
        ),
        needs=(
            "Ein Sanitär, der am Sonntag abnimmt.",
            "Jemand, der unsere Zimmer fotografiert. Unsere Bilder sehen aus wie vom Makler.",
        ),
        contact=("email: wirt@zum-anker.example", "phone: +41 61 000 01 10", "address: Unterer Rheinweg 8, 4058 Basel"),
    ),
    Entity(
        slug="gaestehaus-sonnenrain",
        name="Gästehaus Sonnenrain",
        hub="basel",
        kind="hotel",
        about="Ein Gästehaus mit neun Zimmern in Riehen, in einem Haus von 1924. Frühstück im "
        "Garten, solange es warm ist. Zwanzig Minuten mit dem Tram ins Zentrum.",
        rooms=(
            "Gartenzimmer — 2 guests, CHF 165, 4 of them.",
            "Einzelzimmer Nord — 1 guest, CHF 110, 3 of them.",
            "Zimmer mit Balkon — 2 guests, CHF 185, 2 of them.",
        ),
        needs=("Eine Gärtnerin für den Frühling, zwei Tage im Monat, CHF 45 die Stunde.",),
        contact=("email: post@sonnenrain.example", "phone: ask first", "address: Baselstrasse 44, 4125 Riehen"),
    ),
    Entity(
        slug="zimmer-ob-der-baeckerei",
        name="Zimmer ob der Bäckerei",
        hub="basel",
        kind="hotel",
        about="Two rooms over a working bakery in the Gundeldingen. You will smell bread at four in "
        "the morning. People either love that or write us a bad note about it.",
        rooms=(
            "Zimmer Ost — 2 guests, CHF 130, 1 of them.",
            "Zimmer West — 2 guests, CHF 130, 1 of them. Quiet side, over the yard.",
        ),
        reviews=(
            "Woke at four to the smell of bread and could not be angry about it.",
            "Small, clean, and the baker gave us a bag for the train.",
        ),
        contact=("email: zimmer@baeckerei-gundeli.example", "phone: never"),
    ),
    Entity(
        slug="herberge-dreiland",
        name="Herberge Dreiland",
        hub="basel",
        kind="hotel",
        about="Mehrbettzimmer und zwei Familienzimmer am Rand von Kleinhüningen. Küche zum "
        "Selberkochen, Waschmaschine im Keller, Gruppen willkommen.",
        rooms=(
            "Mehrbettzimmer A — 6 guests, CHF 38, 2 of them. Preis pro Bett.",
            "Mehrbettzimmer B — 8 guests, CHF 36, 1 of them. Preis pro Bett.",
            "Familienzimmer — 4 guests, CHF 140, 2 of them.",
        ),
        needs=("Eine Nachtaufsicht für die Wochenenden, CHF 30 die Stunde.",),
        contact=("email: anmeldung@herberge-dreiland.example", "phone: +41 61 000 01 44"),
    ),
    Entity(
        slug="logis-vieux-moulin",
        name="Logis du Vieux Moulin",
        hub="basel",
        kind="hotel",
        about="Chambres d'hôtes dans un ancien moulin à Allschwil. Table d'hôte le jeudi, sur "
        "réservation. Trois chambres, un chat, pas d'ascenseur.",
        rooms=(
            "Chambre du meunier — 2 guests, CHF 155, 1 of them.",
            "Chambre jaune — 2 guests, CHF 145, 1 of them.",
            "Petite chambre — 1 guest, CHF 105, 1 of them.",
        ),
        needs=("Un couvreur pour le toit, avant l'hiver.",),
        contact=("email: bonjour@vieux-moulin.example", "phone: +41 61 000 01 77", "mobile: ask first"),
    ),
    Entity(
        slug="kanalhaus-lofts",
        name="Kanalhaus Lofts",
        hub="basel",
        kind="hotel",
        about="Wohnen auf Zeit im Klybeck: fünf möblierte Lofts, Mindestaufenthalt vier Wochen. "
        "Internet, eigene Küche, kein Empfang und keine Reinigung im Preis.",
        rooms=(
            "Loft klein — 2 guests, CHF 95, 2 of them.",
            "Loft gross — 4 guests, CHF 140, 2 of them.",
            "Studio hinten — 1 guest, CHF 75, 1 of them.",
        ),
        needs=("Eine Reinigungsfirma für den Wechseltag, alle zwei Wochen.",),
        contact=("email: mieten@kanalhaus.example", "phone: +41 61 000 02 05", "address: never"),
    ),
    Entity(
        slug="villa-hirzbrunnen",
        name="Pension Villa Hirzbrunnen",
        hub="basel",
        kind="hotel",
        about="Neun Zimmer in einer Villa beim Hirzbrunnen. Nach zwanzig Uhr ist niemand mehr da; "
        "der Türcode kommt per SMS. Eintrag aus öffentlichen Angaben, von der Pension nicht bestätigt.",
        rooms=(
            "Zimmer im Erdgeschoss — 2 guests, CHF 140, 3 of them.",
            "Zimmer erster Stock — 2 guests, CHF 155, 4 of them.",
            "Turmzimmer — 1 guest, CHF 120, 2 of them.",
        ),
        contact=("email: never", "phone: +41 61 000 02 31"),
        unclaimed=True,
    ),
    Entity(
        slug="schiffsquartier-mathilde",
        name="Schiffsquartier Mathilde",
        hub="basel",
        kind="hotel",
        about="Two cabins on a converted freight barge at the St. Johann bank. You sleep on the "
        "water. In March it moves more than some people like, and we say so before you book.",
        rooms=(
            "Kabine vorn — 2 guests, CHF 175, 1 of them.",
            "Kabine hinten — 2 guests, CHF 160, 1 of them.",
        ),
        reviews=("Slept better than at home, and the coffee came to the deck.",),
        contact=("email: ahoi@mathilde.example", "phone: ask first"),
    ),
    Entity(
        slug="beizli-sternen",
        name="Beizli zum Sternen",
        hub="basel",
        kind="cafe",
        about="Eine Quartierbeiz im Matthäus mit zwölf Plätzen. Jeden Tag ein Tagesteller, am "
        "Donnerstag Siedfleisch. Kein Menü auf Papier, es steht auf der Tafel.",
        offer_heading="What we offer",
        offer_file="menu.md",
        offers=(
            "Tagesteller mit Suppe — CHF 22, von zwölf bis zwei.",
            "Siedfleisch am Donnerstag — CHF 28.",
            "Kaffee und Gipfeli am Morgen — CHF 6.",
        ),
        needs=("Jemand, der uns eine Seite baut, die ein Agent lesen kann. Wir haben nichts im Netz.",),
        contact=("email: beizli@zum-sternen.example", "phone: +41 61 000 02 66"),
    ),
    Entity(
        slug="roesterei-vogelsang",
        name="Kaffeerösterei Vogelsang",
        hub="basel",
        kind="cafe",
        about="Wir rösten hinten im Laden, zwei Mal pro Woche, und schenken vorne aus. Acht "
        "Plätze, kein WLAN, absichtlich.",
        offer_heading="What we offer",
        offer_file="menu.md",
        offers=(
            "Filterkaffee, Bohnen vom Dienstag — CHF 5.",
            "Ein Kilo Bohnen, selbst geröstet — CHF 42.",
            "Verkostung für vier Personen — CHF 60, samstags am Morgen.",
        ),
        needs=("Eine Buchhalterin für die Mehrwertsteuer, einmal im Quartal.",),
        contact=("email: laden@roesterei-vogelsang.example", "phone: +41 61 000 02 88"),
    ),
    Entity(
        slug="teestube-amselhof",
        name="Teestube Amselhof",
        hub="basel",
        kind="cafe",
        about="Vierzig offene Tees, Kuchen von der Nachbarin, und eine Regel: keine Laptops nach "
        "vierzehn Uhr. Am Morgen arbeitet hier halb Basel, am Nachmittag redet es.",
        offer_heading="What we offer",
        offer_file="menu.md",
        offers=(
            "Kanne Tee, offene Blätter — CHF 9.",
            "Kuchen vom Tag — CHF 7.",
            "Der kleine Saal für eine Lesung — CHF 120 am Abend, zwanzig Plätze.",
        ),
        contact=("email: hallo@amselhof.example", "phone: +41 61 000 03 02", "address: Amselstrasse 7, 4055 Basel"),
    ),
    Entity(
        slug="imbiss-rheinbord",
        name="Imbiss Rheinbord",
        hub="basel",
        kind="cafe",
        about="Ein Fenster an der Uferstrasse. Wurst, Pommes, im Sommer bis Mitternacht. Keine "
        "Sitzplätze, nur die Mauer.",
        offer_heading="What we offer",
        offer_file="menu.md",
        offers=(
            "Bratwurst im Brot — CHF 8.",
            "Pommes gross — CHF 7.",
            "Heisser Tee im Winter — CHF 4.",
        ),
        contact=("email: imbiss@rheinbord.example", "phone: never"),
        unclaimed=True,
    ),
    Entity(
        slug="trattoria-barcarola",
        name="Trattoria Barcarola",
        hub="basel",
        kind="cafe",
        about="Un'osteria di sei tavoli dietro la Clarastrasse. Pasta fresca ogni giorno, carta "
        "dei vini corta, cucina chiusa alle ventidue.",
        offer_heading="What we offer",
        offer_file="menu.md",
        offers=(
            "Pasta fresca del giorno — CHF 24.",
            "Antipasti per due — CHF 19.",
            "Il tavolo lungo per otto persone — su prenotazione, nessun supplemento.",
        ),
        needs=("Un lavapiatti per il venerdì e il sabato, CHF 26 all'ora.",),
        contact=("email: ciao@barcarola.example", "phone: +41 61 000 03 41"),
    ),
    Entity(
        slug="suppenkueche-dreirosen",
        name="Suppenküche Dreirosen",
        hub="basel",
        kind="cafe",
        about="Jeden Mittag ein Topf, meist vegan, immer unter zehn Franken. Wir sind ein Verein "
        "und kein Restaurant: wer zahlen kann, zahlt für zwei.",
        offer_heading="What we offer",
        offer_file="menu.md",
        offers=(
            "Topf des Tages, vegan — CHF 9, mit Brot.",
            "Topf mit Fleisch, freitags — CHF 11.",
        ),
        needs=("Freiwillige für den Abwasch, Montag bis Freitag ab halb zwei.",),
        contact=("email: verein@dreirosen-suppe.example", "phone: +41 61 000 03 60"),
    ),
    Entity(
        slug="textilpflege-gundeli",
        name="Textilpflege Gundeli",
        hub="basel",
        kind="service",
        about="Wäscherei für Gästehäuser und Beizen. Wir holen am Morgen und bringen am Abend, "
        "sechs Tage die Woche, im ganzen Stadtgebiet.",
        offers=(
            "Bettwäsche pro Kilo — CHF 4.20, Abholung inbegriffen.",
            "Tischtücher und Servietten — CHF 2.80 pro Stück.",
            "Notwäsche am gleichen Tag — Zuschlag CHF 30.",
        ),
        needs=("Eine Fahrerin für die Morgentour, CHF 29 die Stunde, sechs Uhr bis zehn.",),
        contact=("email: auftrag@textilpflege-gundeli.example", "phone: +41 61 000 03 88"),
    ),
    Entity(
        slug="kuechenkollektiv-klybeck",
        name="Küchenkollektiv Klybeck",
        hub="basel",
        kind="service",
        about="Wir kochen in Ihrer Küche: Firmenessen, Hochzeiten, Trauerfeiern. Vier Köchinnen, "
        "ein Transporter, und wir räumen auf, bevor wir gehen.",
        offers=(
            "Essen für zwanzig Personen — CHF 48 pro Person, zwei Gänge.",
            "Apéro riche für fünfzig — CHF 32 pro Person.",
            "Eine Köchin für einen Abend — CHF 420.",
        ),
        needs=("Ein Konditor für Desserts, auf Abruf, CHF 55 die Stunde.",),
        contact=("email: kochen@kuechenkollektiv.example", "phone: ask first", "address: never"),
    ),
    Entity(
        slug="schluesseldienst-spalen",
        name="Schlüsseldienst Spalen",
        hub="basel",
        kind="service",
        about="Türen öffnen, Schlösser wechseln, Tag und Nacht. Zwanzig Minuten im Stadtgebiet, "
        "länger auf dem Land. Wir fahren nicht, ohne den Preis vorher zu sagen.",
        offers=(
            "Tür öffnen ohne Schaden — CHF 180 am Tag, CHF 280 nachts.",
            "Zylinder wechseln — ab CHF 140.",
            "Schlüssel nachmachen — CHF 25.",
        ),
        contact=("email: notfall@schluesseldienst-spalen.example", "phone: +41 61 000 04 11"),
    ),
    Entity(
        slug="mira-luetolf",
        name="Mira Lütolf",
        hub="basel",
        kind="person",
        about="I move data between systems for companies that have outgrown their spreadsheets. "
        "Basel, mostly remote, and I keep two days a week free for the work nobody planned.",
        offer_heading="What I do",
        offers=(
            "Spreadsheet to database migration — CHF 1100/day.",
            "Nightly import jobs that do not fail silently — CHF 2800, one week.",
            "A read-only report your staff can trust — CHF 1600.",
        ),
        needs=("Someone who can make a report look like something, not like a default theme. CHF 90/hour.",),
        contact=("email: mira@luetolf.example", "phone: ask first", "address: never"),
    ),
)

ENTITIES: tuple[Entity, ...] = BASEL


# --------------------------------------------------------------------------- writing it out


def about_md(entity: Entity) -> str:
    """about.md: the name on the first line, then the description the card's tagline comes from."""
    return f"# {entity.name}\n\n{entity.about}\n"


def offers_md(entity: Entity) -> str:
    """The offers and needs file: the two headings the seeder's parser turns into the card's index."""
    out = [f"# {entity.offer_heading}", ""]
    out += [f"- {line}" for line in entity.offers]
    if entity.needs:
        heading = "What I need" if entity.offer_heading.startswith("What I") else "What we need"
        out += ["", f"# {heading}", ""]
        out += [f"- {line}" for line in entity.needs]
    return "\n".join(out) + "\n"


def rooms_md(entity: Entity) -> str:
    """rooms.md: one bookable unit per line, plus the needs of a stay that has any."""
    out = ["# Rooms", ""]
    out += [f"- {line}" for line in entity.rooms]
    if entity.needs:
        out += ["", "# What we need", ""]
        out += [f"- {line}" for line in entity.needs]
    return "\n".join(out) + "\n"


def contact_md(entity: Entity) -> str:
    """contact.md: a bare value is published, "ask first" is gated on consent, "never" is withheld."""
    return "\n".join(["# Contact", "", *(f"- {line}" for line in entity.contact)]) + "\n"


def reviews_md(entity: Entity) -> str:
    """Owner-written praise, under a heading the parser ignores, so it stays out of the index.

    A verified rating comes only from a signed booking receipt, so nothing here becomes one. It is
    here because real folders have a file like this and the parser has to walk past it.
    """
    return "\n".join(["# What people said", "", *(f"- {line}" for line in entity.reviews)]) + "\n"


def files_for(entity: Entity) -> dict[str, str]:
    """Every file this entity's folder holds, as path inside the folder to contents."""
    files = {"about.md": about_md(entity), "contact.md": contact_md(entity)}
    if entity.rooms:
        files["rooms.md"] = rooms_md(entity)
    if entity.offers:
        files[entity.offer_file] = offers_md(entity)
    if entity.reviews:
        files["reviews.md"] = reviews_md(entity)
    files.update(entity.extra)
    return files


def write_entity(entity: Entity, root: Path = VAULTS) -> list[Path]:
    """Write one folder and return the paths written. Refuses the hand-written ten."""
    if entity.slug in PRE_EXISTING:
        raise SystemExit(f"{entity.slug} is hand-written; the generator does not own it")
    folder = root / entity.slug
    folder.mkdir(parents=True, exist_ok=True)
    written = []
    for name, body in files_for(entity).items():
        (folder / name).write_text(body, encoding="utf-8")
        written.append(folder / name)
    return written


def drifted(entity: Entity, root: Path = VAULTS) -> list[str]:
    """File names where the folder on disk no longer says what the table says."""
    folder = root / entity.slug
    out = []
    for name, body in files_for(entity).items():
        path = folder / name
        if not path.exists() or path.read_text(encoding="utf-8") != body:
            out.append(name)
    return out


def maps_source(entities: tuple[Entity, ...] = ENTITIES) -> str:
    """The HOME, KIND and UNCLAIMED entries for seed_vaults.py, so nobody types them by hand."""
    lines = ["# HOME"]
    for hub in ("basel", "zurich", "bern"):
        for e in entities:
            if e.hub == hub:
                lines.append(f'    "{e.slug}": "{e.hub}",')
    lines.append("# KIND")
    lines += [f'    "{e.slug}": "{e.kind}",' for e in entities]
    lines.append("# UNCLAIMED")
    lines += [f'    "{e.slug}",' for e in entities if e.unclaimed]
    return "\n".join(lines)


def main() -> int:
    """Write the corpus, or check that what is on disk still matches the table."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hub", default="", help="only this hub's entities")
    ap.add_argument("--check", action="store_true", help="report drift instead of writing")
    ap.add_argument("--print-maps", action="store_true", help="print the seed_vaults.py entries")
    args = ap.parse_args()

    entities = [e for e in ENTITIES if not args.hub or e.hub == args.hub]
    if args.print_maps:
        print(maps_source(tuple(entities)))
        return 0

    if args.check:
        bad = {e.slug: drifted(e) for e in entities}
        bad = {slug: names for slug, names in bad.items() if names}
        for slug, names in bad.items():
            print(f"  ! {slug}: {', '.join(names)}")
        print(f"\n{len(entities) - len(bad)}/{len(entities)} folders match the table")
        return 1 if bad else 0

    for entity in entities:
        write_entity(entity)
    by_hub = {hub: sum(1 for e in entities if e.hub == hub) for hub in {e.hub for e in entities}}
    print(f"wrote {len(entities)} folders to {VAULTS}: " + ", ".join(f"{v} {k}" for k, v in sorted(by_hub.items())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
