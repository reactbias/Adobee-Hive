"""Register the folders in testdata/vaults/ through the real signup endpoint.

Not a seeder that reaches into the database. It builds a Card from each folder and posts it to
`POST /api/hub/register` like any applicant, so **seeding is itself a test of signup**: if
admission is broken the hubs come up empty and we find out immediately rather than on stage.

Each vault is a folder of markdown. `about.md` gives the name and description, `contact.md` the
channels, and every file becomes a row in `structure` — paths and digests, never contents.

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
    "hotel-krafft": "basel",
    "cafe-rhein": "basel",
    "lena-hofmann": "zurich",
    "grid-ops": "zurich",
    # A stay on the far hub, so a federated search has something to actually return.
    # Without one, radius 1 looks broken: the peer is asked and answers with nothing,
    # because discover() searches stay kinds and the other two vaults are people.
    "pension-limmat": "zurich",
}
#: Must be one of hive.STAY_KINDS ("hotel", "cafe") to be discoverable, or "person", which
#: discover() deliberately skips — people are found through the hr tools, not a room search.
KIND = {
    "hotel-krafft": "hotel",
    "cafe-rhein": "cafe",
    "pension-limmat": "hotel",
    "lena-hofmann": "person",
    "grid-ops": "person",
}

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
        m = re.match(
            r"(?P<name>[^—\-]+)[—\-]+\s*(?P<guests>\d+)\s*guests?,\s*CHF\s*(?P<price>\d+)" r"(?:,\s*(?P<qty>\d+))?",
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
        "structure": structure,
    }
    units = read_units(vault)
    if units:
        card["units"] = units
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
