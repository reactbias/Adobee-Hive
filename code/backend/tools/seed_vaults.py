"""Register the folders in testdata/vaults/ through the real signup endpoint.

Not a seeder that reaches into the database. It builds a Card from each folder and posts it to
`POST /api/hub/register` like any applicant, so **seeding is itself a test of signup**: if
admission is broken the hubs come up empty and we find out immediately rather than on stage.

Each vault is a folder of markdown. `about.md` gives the name and description, `contact.md` the
channels, a "What I do" / "What I need" heading anywhere in the folder gives the card its `offers`
and `needs` (which is what discovery indexes), and every file becomes a row in `structure` — paths
and digests, never contents.

    python tools/seed_vaults.py                        # against http://localhost:8000
    python tools/seed_vaults.py --hub http://localhost:8001 --only lena-hofmann grid-ops
    python tools/seed_vaults.py --keys .keys           # keep the keypairs, so re-runs are the same owner
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[3]
VAULTS = ROOT / "testdata" / "vaults"

#: Which vault belongs on which hub, so the two are not mirrors of each other. Federation is
#: invisible when every hub holds the same thing.
HOME = {
    # basel — hospitality
    "hotel-krafft": "basel",
    "cafe-rhein": "basel",
    # basel — the rest of the test corpus (tools/make_corpus.py)
    "wirtshaus-anker": "basel",
    "gaestehaus-sonnenrain": "basel",
    "zimmer-ob-der-baeckerei": "basel",
    "herberge-dreiland": "basel",
    "logis-vieux-moulin": "basel",
    "kanalhaus-lofts": "basel",
    "villa-hirzbrunnen": "basel",
    "schiffsquartier-mathilde": "basel",
    "beizli-sternen": "basel",
    "roesterei-vogelsang": "basel",
    "teestube-amselhof": "basel",
    "imbiss-rheinbord": "basel",
    "trattoria-barcarola": "basel",
    "suppenkueche-dreirosen": "basel",
    "textilpflege-gundeli": "basel",
    "kuechenkollektiv-klybeck": "basel",
    "schluesseldienst-spalen": "basel",
    "mira-luetolf": "basel",
    # zurich — developer and freelance work
    "lena-hofmann": "zurich",
    "grid-ops": "zurich",
    "niko-ferrer": "zurich",
    "aylin-dervis": "zurich",
    # zurich — the rest of the test corpus (tools/make_corpus.py)
    "jonas-brun": "zurich",
    "ilaria-conti": "zurich",
    "tobias-wenger": "zurich",
    "svenja-aebi": "zurich",
    "renzo-balmer": "zurich",
    "fabienne-roulet": "zurich",
    "kuno-steinmann": "zurich",
    "mirjam-oswald": "zurich",
    "anouk-pfister": "zurich",
    "leonie-frei": "zurich",
    "basil-zuercher": "zurich",
    "kaspar-lienhard": "zurich",
    "quellcode-genossenschaft": "zurich",
    "datenhaus-oerlikon": "zurich",
    "bildwerk-retusche": "zurich",
    "kurierdienst-sihlquai": "zurich",
    "gasthof-sihlwald": "zurich",
    # bern — local services. A guesthouse sits here too, because a real hub is mixed: domain is
    # what a hub mostly carries, never a rule it enforces.
    "schnittwerk-bern": "bern",
    "velowerk-bern": "bern",
    "lichtfeld-foto": "bern",
    "pension-limmat": "bern",
}
#: The kind each folder registers as. Only a filter now: discovery indexes what a card offers and
#: needs, so a person is found by their skills in the same search that finds a room.
KIND = {
    "hotel-krafft": "hotel",
    "cafe-rhein": "cafe",
    "pension-limmat": "hotel",
    "lena-hofmann": "person",
    "grid-ops": "person",
    "niko-ferrer": "person",
    "aylin-dervis": "person",
    "schnittwerk-bern": "service",
    "velowerk-bern": "service",
    "lichtfeld-foto": "service",
    # the rest of the test corpus (tools/make_corpus.py)
    "wirtshaus-anker": "hotel",
    "gaestehaus-sonnenrain": "hotel",
    "zimmer-ob-der-baeckerei": "hotel",
    "herberge-dreiland": "hotel",
    "logis-vieux-moulin": "hotel",
    "kanalhaus-lofts": "hotel",
    "villa-hirzbrunnen": "hotel",
    "schiffsquartier-mathilde": "hotel",
    "beizli-sternen": "cafe",
    "roesterei-vogelsang": "cafe",
    "teestube-amselhof": "cafe",
    "imbiss-rheinbord": "cafe",
    "trattoria-barcarola": "cafe",
    "suppenkueche-dreirosen": "cafe",
    "textilpflege-gundeli": "service",
    "kuechenkollektiv-klybeck": "service",
    "schluesseldienst-spalen": "service",
    "mira-luetolf": "person",
    "jonas-brun": "person",
    "ilaria-conti": "person",
    "tobias-wenger": "person",
    "svenja-aebi": "person",
    "renzo-balmer": "person",
    "fabienne-roulet": "person",
    "kuno-steinmann": "person",
    "mirjam-oswald": "person",
    "anouk-pfister": "person",
    "leonie-frei": "person",
    "basil-zuercher": "person",
    "kaspar-lienhard": "person",
    "quellcode-genossenschaft": "service",
    "datenhaus-oerlikon": "service",
    "bildwerk-retusche": "service",
    "kurierdienst-sihlquai": "service",
    "gasthof-sihlwald": "hotel",
}

#: Folders whose card was compiled from public information rather than written by its subject. The
#: hub reports these as unclaimed and no caller may treat one as a business that agreed to anything,
#: which is a trust signal a test corpus needs a few of: in the real directory most cards are leads.
UNCLAIMED = frozenset(
    {
        "villa-hirzbrunnen",
        "imbiss-rheinbord",
    }
)

#: Words that mean something to `fit()`. Pulled out of the prose rather than typed twice, so the
#: folder stays the single source and nobody has to maintain a parallel list of tags.
FEATURE_WORDS = (
    "quiet",
    "dog-friendly",
    "breakfast",
    "wifi",
    "accessible",
    "vegan",
    "late check-in",
    "river view",
    "terrace",
    "remote",
)


def canonical(data: dict) -> bytes:
    """The bytes the hub will verify: sorted keys, no spaces. Must match hive.canonical."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def read_contact(vault: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Parse contact.md into the open map plus the per-channel sharing flags.

    A line with no value is a channel that exists but is not published; "ask first" marks one the
    owner will release on request, and "never" keeps it out of the Card entirely.
    """
    contact: dict[str, str] = {}
    sharing: dict[str, str] = {}
    path = vault / "contact.md"
    if not path.exists():
        return contact, sharing
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("-").strip()
        if ":" not in line or line.startswith("#"):
            continue
        channel, _, value = line.partition(":")
        channel, value = channel.strip().lower(), value.strip()
        if value.lower() == "never":
            sharing[channel] = "never"  # absent from the Card; see hive.with_contact
            continue
        if value.lower().startswith("ask"):
            contact[channel] = ""
            sharing[channel] = "confirm"
            continue
        contact[channel] = value
    return contact, sharing


#: Headings that open the two sides of the market. The needs are checked first, so a folder that
#: says "What I need" is never read as an offer because the word "need" is shorter than the match.
OFFER_HEADINGS = ("what i do", "what we do", "what i offer", "what we offer", "offers", "services", "rooms", "menu")
NEED_HEADINGS = ("what i need", "what we need", "needs", "hiring", "looking for")


def _entry(text: str) -> dict:
    """One offer or need: the title up to the first dash, the line it came from, and a price if stated."""
    entry = {"title": re.split(r"\s+[—–-]\s+", text, maxsplit=1)[0].rstrip(".,")[:120], "summary": text[:300]}
    if price := re.search(r"CHF\s*([\d']+)", text):
        entry["price_chf"] = int(price.group(1).replace("'", ""))
    return entry


def read_offers_needs(vault: Path) -> tuple[list[dict], list[dict]]:
    """Parse what the folder says its owner does and wants: the card's `offers` and `needs`.

    This is what discovery indexes, so it decides whether the entity is findable at all. It is
    read out of the markdown the owner already wrote — a heading that says what they do, then one
    bullet per line — rather than typed here, so the folder stays the single source of truth.
    """
    offers: list[dict] = []
    needs: list[dict] = []
    for path in sorted(vault.rglob("*.md")):
        bucket: list[dict] | None = None
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("#"):
                heading = line.lstrip("#").strip().lower()
                if any(h in heading for h in NEED_HEADINGS):
                    bucket = needs
                elif any(h in heading for h in OFFER_HEADINGS):
                    bucket = offers
                else:
                    bucket = None
            elif bucket is not None and line.startswith("-"):
                bucket.append(_entry(line.lstrip("-").strip()))
    return offers, needs


def read_units(vault: Path) -> list[dict]:
    """Parse rooms.md lines like `- Attic single — 1 guest, CHF 110, 4 of them.` into units.

    A stay with no units is not bookable, and `fit()` will not return it at all — which is how
    the first run of this script produced a hub that answered every query with nothing.
    """
    path = vault / "rooms.md"
    if not path.exists():
        return []
    units = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().lstrip("-").strip()
        if not line or line.startswith("#"):
            continue
        # The separator is an em dash or a *spaced* hyphen, so a hyphen inside the name survives.
        # It did not before: "River-view double" split at the hyphen, found no guest count, and the
        # hotel's most expensive room existed in the markdown and nowhere in the hub.
        m = re.match(
            r"(?P<name>.+?)\s*(?:[—–]|\s-\s)\s*(?P<guests>\d+)\s*guests?,\s*CHF\s*(?P<price>\d+)"
            r"(?:,\s*(?P<qty>\d+))?",
            line,
        )
        if not m:
            continue
        name = m.group("name").strip()
        units.append(
            {
                "id": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or f"unit-{len(units) + 1}",
                "name": name,
                "max_guests": int(m.group("guests")),
                "price_chf": int(m.group("price")),
                "quantity": int(m.group("qty") or 1),
            }
        )
    return units


def read_features(vault: Path) -> list[str]:
    """Features a search can match on, lifted from the prose the owner already wrote."""
    text = " ".join(f.read_text(encoding="utf-8") for f in vault.rglob("*.md")).lower()
    return [w for w in FEATURE_WORDS if w in text]


def build_card(vault: Path) -> dict:
    """Turn a folder of markdown into a Card: the shape of it, never the contents."""
    about = (vault / "about.md").read_text(encoding="utf-8") if (vault / "about.md").exists() else ""
    lines = [ln.strip() for ln in about.splitlines() if ln.strip()]
    name = lines[0].lstrip("# ").strip() if lines else vault.name
    description = next((ln for ln in lines[1:] if not ln.startswith("#")), "")[:300]
    contact, contact_sharing = read_contact(vault)
    offers, needs = read_offers_needs(vault)

    structure = []
    for file in sorted(vault.rglob("*.md")):
        body = file.read_bytes()
        structure.append(
            {
                "path": file.relative_to(vault).as_posix(),
                "bytes": len(body),
                "visibility": "public-summary",
                "digest": "sha256:" + hashlib.sha256(body).hexdigest()[:12],
            }
        )

    card = {
        "id": vault.name,
        "slug": vault.name,
        "kind": KIND.get(vault.name, "person"),
        "name": name,
        "description": description,
        "tagline": description[:90],
        "sharing": "public",
        "contact": contact,
        "contact_sharing": contact_sharing,
        "features": read_features(vault),
        # The index: a hub searches these before it looks at anything else about the entity.
        "offers": offers,
        "needs": needs,
        "structure": structure,
    }
    units = read_units(vault)
    if units:
        card["units"] = units
    if vault.name in UNCLAIMED:
        # Same shape as domains/examples.py: the trust block reads `verified_by_owner` and reports
        # the card as unclaimed, so a lead is never answered as a business that agreed.
        card["provenance"] = {
            "source": "public information",
            "verified_by_owner": False,
            "note": "Fictional test card, nobody claimed it. Hand-off only.",
        }
    return card


def post(hub: str, path: str, body: dict) -> dict:
    """POST JSON and return the answer, including a refusal — which is an answer, not an error."""
    req = urllib.request.Request(
        f"{hub.rstrip('/')}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read())
    except urllib.error.HTTPError as err:
        return {"state": "error", "reason": f"HTTP {err.code}: {err.read().decode()[:200]}"}
    except urllib.error.URLError as err:
        return {"state": "error", "reason": f"cannot reach {hub}: {err.reason}"}


def main() -> int:
    """Register every vault and report what the hub made of each."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hub", default="http://localhost:8000")
    ap.add_argument("--hub-id", default="", help="only seed vaults whose home is this hub")
    ap.add_argument("--only", nargs="*", default=[], help="vault folder names")
    ap.add_argument("--keys", default="", help="directory to keep keypairs in, so re-runs are the same owner")
    args = ap.parse_args()

    if not VAULTS.exists():
        print(f"no vaults at {VAULTS}")
        return 1

    vaults = sorted(v for v in VAULTS.iterdir() if v.is_dir())
    if args.only:
        vaults = [v for v in vaults if v.name in args.only]
    if args.hub_id:
        vaults = [v for v in vaults if HOME.get(v.name) == args.hub_id]
    if not vaults:
        print("nothing to seed")
        return 0

    keydir = Path(args.keys) if args.keys else None
    if keydir:
        keydir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for vault in vaults:
        if keydir and (keydir / f"{vault.name}.key").exists():
            key = Ed25519PrivateKey.from_private_bytes((keydir / f"{vault.name}.key").read_bytes())
        else:
            key = Ed25519PrivateKey.generate()
            if keydir:
                (keydir / f"{vault.name}.key").write_bytes(key.private_bytes_raw())

        application = {
            "entity": build_card(vault),
            "public_key": base64.b64encode(key.public_key().public_bytes_raw()).decode(),
            "proofs": [],
            "invite": "",
        }
        application["signature"] = base64.b64encode(key.sign(canonical(application))).decode()

        out = post(args.hub, "/api/hub/register", application)
        state = out.get("state", "?")
        mark = {"admitted": "✓", "pending": "·", "rejected": "✗", "error": "!"}.get(state, "?")
        files = len(application["entity"]["structure"])
        print(f"  {mark} {vault.name:16} {state:9} {files} files  {out.get('reason', '')[:70]}")
        if state in ("rejected", "error"):
            failures += 1

    print(f"\n{len(vaults) - failures}/{len(vaults)} on {args.hub}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
