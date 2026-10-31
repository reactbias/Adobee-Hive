"""Fictional Basel businesses for the demo. Every name here is invented."""

import copy

from . import db, hive
from .domains import examples

SBB, MESSE, MARKT, BADISCHER = "basel sbb", "messe basel", "marktplatz", "badischer bahnhof"

CARDS = [
    {
        "id": "hotel-rheinblick",
        "slug": "rheinblick",
        "kind": "hotel",
        "name": "Hotel Rheinblick",
        "tagline": "Quiet rooms over the Rhine, 9 minutes from Basel SBB",
        "description": "Family-run 18-room hotel on the Kleinbasel riverside. Quiet courtyard rooms, dogs welcome, "
        "self check-in kiosk for late arrivals.",
        "address": "Unterer Rheinweg 41, 4058 Basel",
        "contact": {"phone": "+41 61 000 00 01", "email": "hello@rheinblick.example"},
        "features": ["dog-friendly", "late check-in", "quiet", "breakfast", "wifi", "river view"],
        "distances_m": {SBB: 1900, MESSE: 900, MARKT: 700, BADISCHER: 1300},
        "units": [
            {"id": "single", "name": "Courtyard single", "max_guests": 1, "price_chf": 128, "quantity": 3},
            {"id": "double", "name": "Courtyard double", "max_guests": 2, "price_chf": 172, "quantity": 4},
            {"id": "river", "name": "River-view double", "max_guests": 2, "price_chf": 238, "quantity": 2},
        ],
        "policies": {
            "check_in": "15:00 to 02:00 (kiosk after 22:00)",
            "check_out": "11:00",
            "pets": "Dogs CHF 15/night, max 1",
            "cancellation": "Free until 48 h before arrival",
            "payment": "Pay at the property; Basel Mobility Ticket included",
        },
    },
    {
        "id": "hotel-gare",
        "slug": "gare-central",
        "kind": "hotel",
        "name": "Gare Central Basel",
        "tagline": "Right at Basel SBB, built for business travellers",
        "description": "120 rooms directly at the station. 24 h reception, meeting rooms, fast wifi.",
        "address": "Centralbahnplatz 9, 4051 Basel",
        "contact": {"phone": "+41 61 000 00 02"},
        "features": ["late check-in", "24h reception", "wifi", "breakfast", "meeting rooms", "accessible"],
        "distances_m": {SBB: 80, MESSE: 2600, MARKT: 1500, BADISCHER: 3000},
        "units": [
            {"id": "std", "name": "Standard double", "max_guests": 2, "price_chf": 189, "quantity": 30},
            {"id": "exec", "name": "Executive room", "max_guests": 2, "price_chf": 265, "quantity": 10},
        ],
        "policies": {
            "check_in": "24 h",
            "check_out": "12:00",
            "pets": "No pets",
            "cancellation": "Free until 18:00 on arrival day",
            "payment": "Card at the property",
        },
    },
    {
        "id": "hotel-dreirosen",
        "slug": "dreirosen-hostel",
        "kind": "hotel",
        "name": "Dreirosen Design Hostel",
        "tagline": "Cheap, social, dog-friendly, next to the Rhine swim",
        "description": "Design hostel with private rooms and dorms. Bar until 1 am, bike rental.",
        "address": "Dreirosenstrasse 3, 4057 Basel",
        "contact": {"email": "hi@dreirosen.example"},
        "features": ["dog-friendly", "bike rental", "wifi", "bar", "late check-in"],
        "distances_m": {SBB: 2800, MESSE: 1500, MARKT: 1600, BADISCHER: 1700},
        "units": [
            {"id": "dorm", "name": "Bed in 6-bed dorm", "max_guests": 1, "price_chf": 42, "quantity": 12},
            {"id": "private", "name": "Private double", "max_guests": 2, "price_chf": 109, "quantity": 5},
        ],
        "policies": {
            "check_in": "14:00 to 01:00",
            "check_out": "10:30",
            "pets": "Dogs free",
            "cancellation": "Free until 24 h before arrival",
            "payment": "Pay at the property",
        },
    },
    {
        "id": "hotel-muenster",
        "slug": "muensterhof",
        "kind": "hotel",
        "name": "Muensterhof Boutique",
        "tagline": "Old Town boutique hotel with a spa",
        "description": "Twelve rooms in a 16th-century house below the Muenster. "
        "Sauna, tasting breakfast. Adults only.",
        "address": "Rittergasse 12, 4051 Basel",
        "contact": {"phone": "+41 61 000 00 04"},
        "features": ["quiet", "sauna", "breakfast", "wifi", "adults only"],
        "distances_m": {SBB: 1100, MESSE: 1700, MARKT: 450, BADISCHER: 2100},
        "units": [
            {"id": "classic", "name": "Classic double", "max_guests": 2, "price_chf": 245, "quantity": 8},
            {"id": "suite", "name": "Muenster suite", "max_guests": 3, "price_chf": 390, "quantity": 2},
        ],
        "policies": {
            "check_in": "15:00 to 21:00",
            "check_out": "11:00",
            "pets": "No pets",
            "cancellation": "Free until 7 days before arrival",
            "payment": "Prepayment by card",
        },
    },
    {
        "id": "hotel-messe",
        "slug": "messe-loft",
        "kind": "hotel",
        "name": "Messe Loft Apartments",
        "tagline": "Apartments with kitchens, 3 minutes to Messe Basel",
        "description": "Serviced apartments for families and longer stays. Underground parking, EV charging.",
        "address": "Riehenring 70, 4058 Basel",
        "contact": {"email": "stay@messeloft.example"},
        "features": ["kitchen", "family rooms", "parking", "ev charging", "wifi", "late check-in", "dog-friendly"],
        "distances_m": {SBB: 2500, MESSE: 200, MARKT: 1400, BADISCHER: 600},
        "units": [
            {"id": "studio", "name": "Studio", "max_guests": 2, "price_chf": 159, "quantity": 6},
            {"id": "family", "name": "Family apartment", "max_guests": 4, "price_chf": 249, "quantity": 3},
        ],
        "policies": {
            "check_in": "Keybox, any time",
            "check_out": "10:00",
            "pets": "Dogs CHF 20/stay",
            "cancellation": "Free until 72 h before arrival",
            "payment": "Pay at the property",
        },
    },
    {
        "id": "cafe-bienli",
        "slug": "cafe-bienli",
        "kind": "cafe",
        "name": "Café Bienli",
        "tagline": "Honey cakes and specialty coffee in St. Johann",
        "description": "Neighbourhood café with local honey from Basel rooftop hives. Walk-ins only.",
        "address": "Elsässerstrasse 20, 4056 Basel",
        "contact": {"phone": "+41 61 000 00 06"},
        "features": ["vegan options", "dog-friendly", "wifi", "outdoor seating"],
        "distances_m": {SBB: 2300, MESSE: 2600, MARKT: 1300, BADISCHER: 2900},
        "opening_hours": {"mon-fri": "07:30-18:00", "sat": "09:00-17:00", "sun": "closed"},
        "units": [],
        "policies": {"reservations": "Walk-ins only"},
    },
]

ATTESTATIONS = [
    ("hotel-rheinblick", "address", "Basel Tourism (fictional registry)"),
    ("hotel-rheinblick", "dog-friendly", "Basel Dog Owners Club (fictional)"),
    ("hotel-gare", "address", "Basel Tourism (fictional registry)"),
    ("hotel-gare", "accessible", "Pro Infirmis audit 2026 (fictional)"),
    ("hotel-muenster", "address", "Basel Tourism (fictional registry)"),
    ("hotel-messe", "ev charging", "Swiss eMobility map (fictional)"),
]


def run() -> None:
    """Publish the fictional Basel cards, their attestations and the unclaimed example cards."""
    for card in CARDS + examples.CARDS:
        hive.publish(copy.deepcopy(card))  # publish stamps the dict; keep the seed pristine for reset()
    for card_id, claim, by in ATTESTATIONS:
        hive.attest(card_id, claim, by)


TABLES = ("hive_events", "hive_reviews", "hive_bookings", "hive_attestations", "hive_keys", "hive_cards")


def reset() -> None:
    """Back to the seeded Basel: drop every booking, review, event and owner edit, then seed again."""
    with db.write() as cur:
        for table in TABLES:
            cur.execute(f"DELETE FROM {table}")
    run()


def seed_if_empty() -> None:
    """Seed only when the Hive has no cards yet, so restarts keep the data."""
    with db.cursor() as cur:
        empty = cur.execute("SELECT count(*) FROM hive_cards").fetchone()[0] == 0
    if empty:
        run()
