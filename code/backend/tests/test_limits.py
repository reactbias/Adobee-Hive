"""What a hub accepts in the first place: the published ceilings, and the whole real corpus under them.

Two doors have to agree — `registration.apply` for a new entity and `hive.publish` for every version
after — or an entity registers politely and grows unbounded on its next update. The regression net is
the last test in the file: every entity in `testdata/vaults/` plus every seeded and example card has
to pass unchanged. If a real entity trips a limit, the limit is wrong.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import config, db, hive, hive_seed, limits, registration
from app.domains import examples

ROOT = Path(__file__).resolve().parents[1]
CARDS_README = ROOT.parents[1] / "documentation" / "cards" / "README.md"


def _seed_vaults():
    """Load tools/seed_vaults.py as a module; it is a script, not part of the app package."""
    if "seed_vaults" in sys.modules:
        return sys.modules["seed_vaults"]
    spec = importlib.util.spec_from_file_location("seed_vaults", ROOT / "tools" / "seed_vaults.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_vaults"] = module
    spec.loader.exec_module(module)
    return module


def _card(**extra) -> dict:
    """A card that is comfortably inside every limit, for one field at a time to be pushed over."""
    return {
        "id": "limit-probe",
        "slug": "limit-probe",
        "kind": "cafe",
        "name": "Limit Probe (fictional)",
        "description": "A fictional café that exists to be measured.",
        "sharing": "public",
        **extra,
    }


# ---------------------------------------------------------------- one field at a time


#: Each row pushes exactly one field to the ceiling and then one character (or entry) past it.
#: `field` is what the refusal must name, `cap` the published number, `under`/`over` build the card.
AT_THE_EDGE = [
    ("description", limits.MAX_DESCRIPTION, lambda n: _card(description="d" * n)),
    ("name", limits.MAX_NAME, lambda n: _card(name="n" * n)),
    ("tagline", limits.MAX_TAGLINE, lambda n: _card(tagline="t" * n)),
    ("kind", limits.MAX_KIND, lambda n: _card(kind="k" * n)),
    ("id", limits.MAX_ID, lambda n: _card(id="i" * n)),
    ("offers.title", limits.MAX_ENTRY_TITLE, lambda n: _card(offers=[{"title": "o" * n, "summary": "s"}])),
    ("offers.summary", limits.MAX_ENTRY_SUMMARY, lambda n: _card(offers=[{"title": "o", "summary": "s" * n}])),
    ("needs.title", limits.MAX_ENTRY_TITLE, lambda n: _card(needs=[{"title": "o" * n, "summary": "s"}])),
    ("offers", limits.MAX_OFFERS, lambda n: _card(offers=[{"title": f"o{i}", "summary": "s"} for i in range(n)])),
    ("needs", limits.MAX_NEEDS, lambda n: _card(needs=[{"title": f"o{i}", "summary": "s"} for i in range(n)])),
    ("features", limits.MAX_FEATURES, lambda n: _card(features=[f"f{i}" for i in range(n)])),
    ("units", limits.MAX_UNITS, lambda n: _card(units=[{"id": f"u{i}", "name": "Room"} for i in range(n)])),
    ("structure", limits.MAX_STRUCTURE, lambda n: _card(structure=[{"path": f"{i}.md"} for i in range(n)])),
    ("structure.path", limits.MAX_PATH, lambda n: _card(structure=[{"path": "p" * n}])),
    ("contact", limits.MAX_CONTACT_CHANNELS, lambda n: _card(contact={f"ch{i}": "x" for i in range(n)})),
    ("contact.email", limits.MAX_CONTACT_VALUE, lambda n: _card(contact={"email": "e" * n})),
    ("offers.tags", limits.MAX_TAGS, lambda n: _card(offers=[{"title": "o", "tags": [f"t{i}" for i in range(n)]}])),
    ("provenance.note", limits.MAX_TEXT, lambda n: _card(provenance={"note": "x" * n})),
]


@pytest.mark.parametrize(("field", "cap", "build"), AT_THE_EDGE, ids=[row[0] for row in AT_THE_EDGE])
def test_just_under_is_accepted_and_just_over_is_refused(field, cap, build):
    """Both sides of every published ceiling, so a limit is a line and not a mood."""
    assert limits.refusal(build(cap)) == "", f"{field} at exactly {cap} must be accepted"
    over = limits.refusal(build(cap + 1))
    assert over, f"{field} at {cap + 1} must be refused"
    assert field.split(".")[-1] in over, f"the refusal must name the field: {over!r}"


@pytest.mark.parametrize(("field", "cap", "build"), AT_THE_EDGE, ids=[row[0] for row in AT_THE_EDGE])
def test_a_refusal_names_the_limit_and_the_actual_size(field, cap, build):
    """ "Too long" is not something anybody can act on. The sentence carries both numbers."""
    reason = limits.refusal(build(cap + 7))
    assert str(cap) in reason, f"the published limit is missing from {reason!r}"
    assert str(cap + 7) in reason, f"the actual size is missing from {reason!r}"
    assert reason == reason.strip() and not reason.endswith("."), "the style is a sentence fragment, like the others"


def _application(**entity) -> dict:
    """An application a hub would accept, for one part of it at a time to be pushed over."""
    return {"entity": _card(**entity), "public_key": "", "proofs": [], "invite": "", "signature": ""}


def test_a_proof_is_bounded_by_how_many_and_by_what_each_one_says():
    """Proofs are recorded unverified, which is a reason to bound them rather than not to."""
    ok = _application()
    ok["proofs"] = [{"type": "dns-txt", "subject": "s" * limits.MAX_PROOF_TEXT}] * limits.MAX_PROOFS
    assert limits.application_refusal(ok) == ""

    too_many = _application()
    too_many["proofs"] = [{"type": "dns-txt", "subject": "x"}] * (limits.MAX_PROOFS + 1)
    assert str(limits.MAX_PROOFS) in limits.application_refusal(too_many)

    too_long = _application()
    over = limits.MAX_PROOF_TEXT + 1
    too_long["proofs"] = [{"type": "dns-txt", "subject": "s" * over}]
    reason = limits.application_refusal(too_long)
    assert "subject" in reason and str(limits.MAX_PROOF_TEXT) in reason and str(over) in reason, reason


def test_the_whole_application_has_a_ceiling_of_its_own():
    """The card plus its key, proofs and signature, measured as the one document that was signed."""
    app = _application()
    app["proofs"] = [{"type": "dns-txt", "subject": "s" * limits.MAX_PROOF_TEXT}] * limits.MAX_PROOFS
    app["entity"]["structure"] = [{"path": f"{i}/" + "p" * limits.MAX_PATH} for i in range(limits.MAX_STRUCTURE)]
    reason = limits.application_refusal(app)
    assert "an application" in reason and str(limits.MAX_APPLICATION_BYTES) in reason, reason


def test_the_whole_card_has_a_ceiling_even_when_every_field_is_inside_its_own():
    """A thousand legal `structure` rows of legal length is every field inside its own and the card absurd."""
    rows = [{"path": f"{i}/" + "p" * limits.MAX_PATH} for i in range(limits.MAX_STRUCTURE)]
    reason = limits.refusal(_card(structure=rows))
    assert str(limits.MAX_CARD_BYTES) in reason and "bytes" in reason, reason


def test_a_deeply_nested_card_is_refused_without_recursing_over_it():
    """A 2000-level body parsed fine and then took the response down. Nothing here may recurse."""
    deep: dict | list = {"id": "deep"}
    for _ in range(2000):
        deep = {"nested": deep}
    reason = limits.refusal({**_card(), "extra": deep})
    assert str(limits.MAX_DEPTH) in reason and "nests" in reason, reason
    assert limits.depth({"a": {"b": [{"c": 1}]}}) == 4


# ---------------------------------------------------------------- normalising


def test_whitespace_is_collapsed_and_trimmed_rather_than_refused():
    """A card's text fields are one line each, and tidying is not a refusal."""
    assert limits.clean("  Hotel   Krafft \n\n on the   Rhine\t ") == "Hotel Krafft on the Rhine"
    assert limits.clean("\u00a0Café\u00a0") == "Café", "a non-breaking space is a space"


def test_zero_width_and_control_characters_are_stripped():
    """Invisible to a reader, and they change a signature over the canonical JSON for no visible reason."""
    stuffed = "quiet\u200brooms\u200c\u200dnear\u2060the\ufeffriver\u00adbank\u202eflip"
    assert limits.clean(stuffed) == "quietroomsnearthe riverbankflip".replace(" ", "")
    assert limits.clean("a\u0000b\u0007c") == "abc"
    # NFC, so two spellings of the same character are one string and one digest.
    assert limits.clean("Cafe\u0301") == "Café"


def test_normalising_reaches_every_string_in_a_card_including_the_keys():
    """One pass over the document, keys included: a channel named with a zero-width space is a channel."""
    card = _card(
        description="  spaced   out  ",
        offers=[{"title": "  Sauna \u200b session ", "tags": ["  wellness  "]}],
        contact={" e\u200bmail ": " hallo@example.test "},
    )
    clean = limits.normalise(card)
    assert clean["description"] == "spaced out"
    assert clean["offers"][0] == {"title": "Sauna session", "tags": ["wellness"]}
    assert clean["contact"] == {"email": "hallo@example.test"}
    assert limits.normalise(clean) == clean, "normalising is idempotent"


def test_a_description_of_invisible_characters_is_tidied_away_not_refused():
    """Length is counted on what a reader can see, so an invisible pad never buys a refusal either."""
    padded = _card(description="x" * 20 + "\u200b" * (limits.MAX_DESCRIPTION * 3))
    assert limits.vet(padded)["description"] == "x" * 20


def test_vet_returns_the_clean_card_and_raises_with_the_sentence():
    """One function both doors call."""
    assert limits.vet(_card(name="  Probe  "))["name"] == "Probe"
    with pytest.raises(limits.LimitError, match=str(limits.MAX_DESCRIPTION)):
        limits.vet(_card(description="d" * (limits.MAX_DESCRIPTION + 1)))


# ---------------------------------------------------------------- the two doors


@pytest.fixture
def clean_index(client):
    """Whatever this test publishes or applies for leaves the shared index again afterwards."""
    yield
    with db.write() as cur:
        cur.execute("DELETE FROM hub_applications")
        for table, column in (("hive_cards", "id"), ("hive_card_history", "card_id"), ("hive_keys", "card_id")):
            cur.execute(f"DELETE FROM {table} WHERE {column} LIKE 'limit-probe%'")


def test_registration_refuses_an_oversized_application_with_a_reason_and_a_next_step(client, clean_index, monkeypatch):
    """A refusal is a 200 with `state: rejected` — the shape an applicant already handles."""
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.OPEN)
    over = limits.MAX_DESCRIPTION + 500
    out = registration.apply({"entity": _card(description="d" * over), "public_key": "", "proofs": []})

    assert out["state"] == registration.REJECTED
    assert str(limits.MAX_DESCRIPTION) in out["reason"] and str(over) in out["reason"], out["reason"]
    assert [c["check"] for c in out["checks"]] == ["shape", "size"], "size is checked before the signature"
    assert out["next"], "a refusal with no next step is a dead end"
    assert hive.get_record("limit-probe") is None, "nothing was published"


def test_an_oversized_application_is_recorded_as_its_size_and_never_as_its_text(client, clean_index, monkeypatch):
    """Keeping the refusal must not itself be the way the database gets filled."""
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.OPEN)
    out = registration.apply({"entity": _card(description="d" * 500_000), "public_key": "", "proofs": []})
    assert out["entity"] == {"id": "limit-probe", "kind": "cafe", "name": "Limit Probe (fictional)", "oversized": True}


def test_the_hub_publishes_the_limits_so_an_applicant_can_read_them_first(client):
    """The policy endpoint carries the whole table; nobody should learn a ceiling from a refusal."""
    published = {row["field"]: row["cap"] for row in registration.policy()["limits"]}
    assert published["description"] == limits.MAX_DESCRIPTION
    assert "size" in registration.policy()["checks"]


def test_an_oversized_update_to_an_existing_card_is_refused_by_publish(client, clean_index):
    """The second door. Without it an entity joins politely and grows unbounded on its next version."""
    first = hive.publish(_card(description="An honest line."))
    assert first["version"] == 1

    with pytest.raises(hive.HiveError, match=str(limits.MAX_DESCRIPTION)):
        hive.publish(_card(description="d" * (limits.MAX_DESCRIPTION + 1)))

    assert hive.get_card("limit-probe")["version"] == 1, "the refused version was never signed"


def test_publish_normalises_what_it_signs(client, clean_index):
    """Tidying happens before the signature, or the stored card and the signed bytes disagree."""
    card = hive.publish(_card(description="  two   lines\nin   one  ", name="Probe\u200b Café"))
    assert card["description"] == "two lines in one"
    assert card["name"] == "Probe Café"
    assert card["trust"]["signature_valid"] is True


# ---------------------------------------------------------------- the request door


def test_a_body_over_the_limit_is_refused_by_size_before_it_is_parsed(client):
    """Neither FastAPI nor uvicorn bounds a body: a 20 MB application used to be parsed and stored."""
    head = b'{"entity":{"id":"too-big","kind":"cafe","name":"x","description":"'
    body = head + b"d" * limits.MAX_BODY_BYTES + b'"}}'
    res = client.post("/api/hub/register", content=body, headers={"Content-Type": "application/json"})
    assert res.status_code == 413
    assert str(limits.MAX_BODY_BYTES) in res.json()["detail"], res.json()
    assert str(len(body)) in res.json()["detail"], "the refusal says what actually arrived"
    assert hive.get_record("too-big") is None


def test_a_declared_oversize_is_refused_without_one_byte_of_it_being_read():
    """The fast path, at the ASGI level: `Content-Length` over the ceiling and nothing is received.

    Without this the guard could lean entirely on counting the bytes as they arrive, which answers
    413 just the same and reads the whole body to get there.
    """
    sent: list[dict] = []

    async def receive() -> dict:
        raise AssertionError("the body must not be read once Content-Length says it is too big")

    async def send(message: dict) -> None:
        sent.append(message)

    async def never(*_args: object) -> None:
        raise AssertionError("the app must not be reached")

    declared = limits.MAX_BODY_BYTES + 1
    scope = {"type": "http", "method": "POST", "headers": [(b"content-length", str(declared).encode())]}
    asyncio.run(limits.BodyLimit(never)(scope, receive, send))

    assert sent[0]["status"] == 413
    assert str(declared) in sent[1]["body"].decode()
    assert str(limits.MAX_BODY_BYTES) in sent[1]["body"].decode()


def test_a_chunked_body_that_declares_no_length_is_counted_as_it_arrives(client):
    """A caller who declares nothing cannot talk their way past the ceiling either."""

    def chunks():
        for _ in range(12):
            yield b"x" * 100_000

    res = client.post("/api/hub/register", content=chunks(), headers={"Content-Type": "application/json"})
    assert res.status_code == 413
    assert str(limits.MAX_BODY_BYTES) in res.json()["detail"], res.json()


def test_a_body_under_the_limit_still_gets_through(client):
    """The guard has to be invisible to every honest caller, including the whole existing demo."""
    assert client.get("/api/health").status_code == 200
    res = client.post("/api/hub/register", json={"entity": {"id": "", "kind": "", "name": ""}})
    assert res.status_code == 200 and res.json()["state"] == registration.REJECTED


# ---------------------------------------------------------------- the published table


def _room_table() -> list[str]:
    """The rows of the published table, between the markers in documentation/cards/README.md."""
    readme = CARDS_README.read_text(encoding="utf-8")
    block = readme.split("<!-- room -->", 1)[1].split("<!-- /room -->", 1)[0]
    return [line for line in block.splitlines() if line.startswith("|")]


def _written(cap: int) -> str:
    """The number as a reader might see it written: 2000, 2,000 or 2'000."""
    return r"\b" + r"[,’']?".join(f"{cap:,}".split(",")) + r"\b"


def test_every_published_limit_is_in_the_cards_readme():
    """An applicant should read what will be accepted before they write it, so the table cannot drift."""
    rows = _room_table()
    for limit in limits.LIMITS:
        matching = [row for row in rows if f"`{limit.field}`" in row]
        assert len(matching) == 1, f"documentation/cards/README.md needs exactly one row for `{limit.field}`"
        assert re.search(
            _written(limit.cap), matching[0]
        ), f"{limit.field} is documented as something other than {limit.cap}: {matching[0]}"
    labelled = sum(1 for row in rows if row.startswith("| `"))
    assert labelled == len(limits.LIMITS), "the table documents a limit the code does not enforce"


def test_the_readme_says_what_the_description_is_for_and_how_the_real_defence_works():
    """A jury reads this page. It is an invitation with an edge, not a rule with a suspicion behind it."""
    readme = CARDS_README.read_text(encoding="utf-8").lower()
    assert "pitch" in readme, "say plainly that the description is the entity's pitch to an agent"
    assert "calibration" in readme, "name the economic loop, which is the part worth showing off"


# ---------------------------------------------------------------- the regression net


def _corpus() -> dict[str, dict]:
    """Every entity this repo can produce: the vault folders, the seeded hub, and the example cards."""
    seed = _seed_vaults()
    cards = {f"vault:{v.name}": seed.build_card(v) for v in sorted(seed.VAULTS.iterdir()) if v.is_dir()}
    cards |= {f"seed:{c['id']}": c for c in hive_seed.CARDS}
    cards |= {f"example:{c['id']}": c for c in examples.CARDS}
    return cards


def test_every_entity_in_the_corpus_is_inside_every_limit():
    """The net. A real entity that trips a limit means the limit is wrong, not the entity."""
    corpus = _corpus()
    assert len(corpus) >= 61, f"the corpus shrank to {len(corpus)} entities"
    refused = {name: limits.refusal(card) for name, card in corpus.items()}
    assert {name: why for name, why in refused.items() if why} == {}


def test_normalising_the_corpus_changes_nothing_a_reader_would_notice():
    """Tidying is for invisibles. It must not quietly rewrite the demo's own words."""
    for name, card in _corpus().items():
        clean = limits.normalise(card)
        assert clean["name"] == card["name"].strip(), name
        assert limits.clean(card.get("description", "")) == clean.get("description", ""), name
        assert len(json.dumps(clean, default=str)) <= len(json.dumps(card, default=str)) + 2, name


def test_every_vault_still_registers_through_the_real_door(client, monkeypatch):
    """Every folder in testdata/vaults, signed and applied for exactly as tools/seed_vaults.py does."""
    monkeypatch.setattr(config, "ADMISSION_POLICY", registration.OPEN)
    seed = _seed_vaults()
    folders = sorted(v for v in seed.VAULTS.iterdir() if v.is_dir())
    names = [v.name for v in folders]
    assert len(names) >= 61, f"the vault corpus shrank to {len(names)} folders"
    with db.write() as cur:
        cur.execute("DELETE FROM hub_applications")
        for table, column in (("hive_cards", "id"), ("hive_card_history", "card_id"), ("hive_keys", "card_id")):
            cur.execute(f"DELETE FROM {table} WHERE {column} IN ({','.join('?' * len(names))})", names)
    try:
        refused = {}
        for vault in folders:
            key = Ed25519PrivateKey.generate()
            application = {
                "entity": seed.build_card(vault),
                "public_key": base64.b64encode(key.public_key().public_bytes_raw()).decode(),
                "proofs": [],
                "invite": "",
            }
            signature = key.sign(hive.canonical(registration.unsigned(application)))
            application["signature"] = base64.b64encode(signature).decode()
            out = registration.apply(application)
            if out["state"] != registration.ADMITTED:
                refused[vault.name] = out["reason"]
        assert refused == {}, "a real entity that cannot register means a limit is wrong"
    finally:
        with db.write() as cur:
            cur.execute("DELETE FROM hub_applications")
            for table, column in (("hive_cards", "id"), ("hive_card_history", "card_id"), ("hive_keys", "card_id")):
                cur.execute(f"DELETE FROM {table} WHERE {column} IN ({','.join('?' * len(names))})", names)
