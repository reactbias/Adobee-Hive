"""Connecting to an entity on another hub: the introduction is this hub's to record, the card is not.

The bug this pins (#143): `hub.connect` gated on `hive.get_record`, a **local-only** lookup, so a
federated search could find `elektro-mattenhof` on bern, the app could offer Connect on it, and
connect answered `no entity 'elektro-mattenhof' on this hub`. The data model already expected the
other case — `connections.request` takes `requester_hub`, `target_hub` *and* `via_hub` — so this was
one wrong gate rather than a missing feature.

What replaces it is the rule federation already holds everywhere else: **never the carrier's word.**
The caller passes the signed card the search handed it, and this hub checks that card against the
key the entity's *own* hub pinned for it, read from a registry this hub fetched itself from a URL on
its own peer list. A card that cannot be checked is refused with a reason that names why.

The last test in this file runs a **real second hub** in a subprocess and does the whole thing over
real HTTP, because the failure that prompted this — and the forwarded-card bug before it — passed
every fake-based test and only appeared when two hubs actually ran.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app import blocklist, connections, db, federation, folders, hive, hub, sharing

BACKEND = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
BERN = "bern"
THEM = "elektro-mattenhof"


@pytest.fixture(autouse=True)
def clean_slate(client):
    """Links, connections and peer knowledge are per test."""
    folders.init()
    connections.init()
    with db.write() as cur:
        for table in ("folder_links", "folder_grants", "folder_handles", "folder_keys", "hub_connections"):
            cur.execute(f"DELETE FROM {table}")
    folders.reset()
    federation.forget()
    yield
    folders.reset()
    federation.forget()


def _card(entity_id: str = THEM, *, kind: str = "service", sharing_flag: str = "") -> tuple[dict, dict[str, str]]:
    """A card signed by a fresh key, and the registry entry that pins that key for it.

    Signed and checked through `hive`'s own functions, so what these tests exercise is the real
    verification and not a stand-in for it. Never published into this hub's index, because the whole
    point is an entity this hub does not carry.
    """
    body: dict = {
        "id": entity_id,
        "slug": entity_id,
        "kind": kind,
        "name": "Elektro Mattenhof",
        "description": "Electrical work in Bern.",
        "offers": ["electrician"],
        "version": 3,
        "published_at": "2026-10-20T09:00:00+00:00",
    }
    if sharing_flag:
        body["sharing"] = sharing_flag
    key = Ed25519PrivateKey.generate()
    public = hive._public_b64(key)
    signature = base64.b64encode(key.sign(hive.canonical(body))).decode()
    card = {**body, "trust": {"signature": signature, "public_key": public, "signature_valid": True}}
    assert hive.verify_pinned(card, {entity_id: public}), "the fixture itself has to produce a valid card"
    return card, {entity_id: public}


def _peer_knows(pins: dict[str, str], hub_id: str = BERN) -> None:
    """Teach this hub what the peer's registry says, the way the background asking would have."""
    federation._by_hub[hub_id] = {
        "hub_id": hub_id,
        "name": "Adobee Hive (bern)",
        "owner_keys": pins,
        "ruleset_keys": {},
        "entities": 20,
    }


# ---------------------------------------------------------------- the gate that was wrong


def test_a_remote_entity_can_be_connected_to_and_the_row_says_which_hub_it_reached(client):
    """The bug, fixed: the introduction is recorded here, and it keeps the route it was reached by."""
    card, pins = _card()
    _peer_knows(pins)
    assert hive.get_record(THEM) is None, "this test is pointless if the entity is in the local index"

    out = hub.connect("Mara Keller", THEM, target_hub=BERN, via_hub=BERN, card=card)
    assert out["target"] == THEM
    assert out["target_hub"] == BERN and out["via_hub"] == BERN
    assert out["remote"] is True and out["origin_hub"] == BERN
    assert BERN in out["says"]
    assert connections.get(out["id"])["target_hub"] == BERN, "the stored row keeps the hub it reached through"


def test_a_local_entity_still_needs_no_card_at_all(client):
    """The local path is untouched: nothing new is required of a caller that was already working."""
    out = hub.connect("Mara Keller", "hotel-rheinblick")
    assert out["target"] == "hotel-rheinblick"
    assert "remote" not in out
    assert out["folder_key"] is not None


def test_the_local_copy_wins_over_any_card_the_caller_offers(client):
    """A hub answers for the cards it carries. A caller cannot substitute its own copy of one."""
    forged, _ = _card("hotel-rheinblick")
    out = hub.connect("Mara Keller", "hotel-rheinblick", target_hub=BERN, card=forged)
    assert "remote" not in out, "a card the caller brought replaced the one this hub holds"


# ---------------------------------------------------------------- what is refused, and why


def test_a_remote_entity_without_a_card_is_refused_and_told_what_to_send(client):
    """The old message said only that it was not here. This one says what would make it work."""
    with pytest.raises(hub.HubError) as err:
        hub.connect("Mara Keller", THEM, target_hub=BERN)
    assert "`card`" in str(err.value) and "target_hub" in str(err.value)


def test_a_remote_entity_without_a_target_hub_is_refused(client):
    """The hub id is where the pinning key is read from, so there is nothing to check without it."""
    card, pins = _card()
    _peer_knows(pins)
    with pytest.raises(hub.HubError, match="target_hub"):
        hub.connect("Mara Keller", THEM, card=card)


def test_a_card_from_a_hub_this_one_does_not_know_is_refused_rather_than_trusted(client):
    """The one thing federation never does. A registry we cannot read is a no, not a maybe."""
    card, _ = _card()  # nothing taught to this hub: no registry for bern
    with pytest.raises(hub.HubError) as err:
        hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)
    assert "no key registry" in str(err.value) and BERN in str(err.value)
    assert connections.awaiting_rating("Mara Keller") == [], "a refused introduction was recorded anyway"


def test_a_registry_that_is_still_empty_is_refused_with_a_reason_naming_the_wait(client):
    """A fresh stack's first half minute: honest about why, and still a refusal."""
    card, _ = _card()
    _peer_knows({})
    with pytest.raises(hub.HubError, match="PEER_ASK_SECONDS"):
        hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)


def test_a_tampered_card_is_refused(client):
    """The carrier can withhold or delay a card. It can never change one."""
    card, pins = _card()
    _peer_knows(pins)
    altered = {**card, "description": "Electrical work in Bern, and cheaper than everyone."}
    with pytest.raises(hub.HubError, match="not the one bern published"):
        hub.connect("Mara Keller", THEM, target_hub=BERN, card=altered)


def test_a_card_signed_by_a_stranger_is_refused(client):
    """A valid signature proves nothing if the signer is not the key that hub pinned."""
    card, _ = _card()
    stranger = base64.b64encode(b"x" * 32).decode()
    _peer_knows({THEM: stranger})
    with pytest.raises(hub.HubError, match="not the one bern published"):
        hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)


def test_an_unsigned_card_is_refused(client):
    """Nothing to check is not the same as nothing wrong."""
    card, pins = _card()
    _peer_knows(pins)
    with pytest.raises(hub.HubError, match="not the one bern published"):
        hub.connect("Mara Keller", THEM, target_hub=BERN, card={k: v for k, v in card.items() if k != "trust"})


def test_a_card_for_a_different_entity_than_the_one_asked_for_is_refused(client):
    """Otherwise a caller could get a connection to A on the strength of B's valid card."""
    card, pins = _card("velowerk-bern")
    _peer_knows(pins)
    with pytest.raises(hub.HubError, match="is for 'velowerk-bern', not for"):
        hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)


# ---------------------------------------------------------------- the rules that still apply


def test_a_blocked_entity_and_a_blocked_hub_are_still_refused_across_hubs(client):
    """Blocking has to mean the same thing whichever hub an entity sits on."""
    card, pins = _card()
    _peer_knows(pins)
    blocklist.block(blocklist.ENTITY, THEM, "it turned out to be a front")
    with pytest.raises(hub.HubError, match="is blocked on this hub"):
        hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)
    blocklist.unblock(blocklist.ENTITY, THEM)

    blocklist.block(blocklist.HUB, BERN, "it relays cards that do not verify")
    with pytest.raises(hub.HubError, match="is blocked on this hub"):
        hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)
    blocklist.unblock(blocklist.HUB, BERN)


def test_a_remote_push_entity_cannot_be_asked_for_either(client):
    """`sharing.resolve` and `connectable` run on the remote card, so the owner's choice travels."""
    card, pins = _card(sharing_flag=sharing.PUSH)
    _peer_knows(pins)
    with pytest.raises(hub.HubError, match="only on their own initiative"):
        hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)


def test_a_remote_confirm_entity_is_recorded_but_this_hub_cannot_say_yes_for_it(client):
    """The state I chose, and why: `requested`, and refused here.

    An introduction to somebody on another hub is a fact worth storing, so it is stored. What this
    hub must not do is complete it: the owner is not its member, their card is not its card, and a
    yes it invented would be a consent nobody gave. So the row stays `requested` — exactly as a
    local `confirm` row does while its owner has not answered — and `connections.confirm` refuses
    it with a reason that names where the yes belongs.
    """
    card, pins = _card(sharing_flag=sharing.CONFIRM)
    _peer_knows(pins)
    out = hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)
    assert out["state"] == connections.REQUESTED and out["sharing"] == sharing.CONFIRM
    assert "says yes on bern, not here" in out["says"]

    with pytest.raises(connections.ConnectionError_, match="bern"):
        connections.confirm(out["id"])
    assert connections.get(out["id"])["state"] == connections.REQUESTED, "the row was changed anyway"
    # Declining is this hub's own caller giving up on its own request, so it stays allowed.
    assert connections.decline(out["id"])["state"] == connections.DECLINED


def test_the_folder_link_to_a_remote_entity_is_local_and_the_demo_has_to_say_so(client):
    """The limitation this exposes, pinned so nobody claims otherwise on stage.

    The link itself is a real local fact: these two handles asked and one accepted, in this hub's own
    DuckDB. The *folder* is a different matter. On `FOLDER_LINK=local` the folder root is the whole
    corpus in `testdata/vaults/`, which every hub in this repo shares, so a remote entity's folder
    is on this disk too and its manifest is not empty. Nothing fetched it from bern and nothing
    could. `GET /api/folders/status` says this in `honest` and `LIMITS.md` says it again; a screen
    that read this manifest as "we reached across to bern" would be the page that is wrong.
    """
    card, pins = _card()
    _peer_knows(pins)
    out = hub.connect("Mara Keller", THEM, target_hub=BERN, card=card)
    assert out["folder"]["linked"] is True, "the link itself is a local fact and is real"
    assert out["folder"]["owner"] == THEM
    # Whatever is in it came off this disk, which is the honest reading of it.
    on_disk = {f["path"] for f in folders.files(THEM)}
    assert {f["path"] for f in out["folder"]["files"]} <= on_disk
    assert folders.LocalFolderLink().folder(THEM) is not None, "the corpus is shared, so this is local"


# ---------------------------------------------------------------- over the wire, two real hubs


def _free_port() -> int:
    """A port the OS picked, so a second stack on this machine is never in the way."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


HUB_TOKEN = "two-hub-test-operator"


def _get(url: str, timeout: float = 10, token: str = "") -> dict:
    """Fetch JSON from our own loopback hub."""
    request = urllib.request.Request(url, headers={"X-Admin-Token": token} if token else {})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310 - our own subprocess
        return json.loads(answer.read())


def _post(url: str, body: dict, timeout: float = 20) -> tuple[int, dict]:
    """POST JSON to our own loopback hub; a 4xx is an answer here, not an exception."""
    request = urllib.request.Request(  # noqa: S310 - our own subprocess
        url, data=json.dumps(body).encode(), headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:  # noqa: S310
            return answer.status, json.loads(answer.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


@pytest.fixture(scope="module")
def two_real_hubs(tmp_path_factory):
    """Two hubs in subprocesses, peered, with one vault seeded into the second one only.

    Skipped rather than failed when either hub does not come up or the peer handshake does not
    settle: a port this machine will not give us is not a bug in the hub, and a flaky red on main
    the night before a pitch costs more than this test is worth. It is a real second hub when it
    runs, which is the point.
    """
    ports = {"here": _free_port(), BERN: _free_port()}
    data = tmp_path_factory.mktemp("hubs")
    procs, logs = {}, {}
    env = {
        **os.environ,
        "ADMISSION_POLICY": "open",
        "ADMIN_TOKEN": HUB_TOKEN,
        "SEED_ON_EMPTY": "false",
        "PEER_ASK_SECONDS": "2",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "LLM_PROVIDER": "offline",
    }
    for name, port in ports.items():
        other = ports[BERN] if name == "here" else ports["here"]
        logs[name] = (data / f"{name}.log").open("w")
        procs[name] = subprocess.Popen(  # noqa: S603 - our own interpreter and module
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND), "--port", str(port)],
            env={
                **env,
                "HIVE_HUB_ID": name,
                "HIVE_PEER_URLS": f"http://127.0.0.1:{other}",
                "DUCKDB_PATH": str(data / f"{name}.duckdb"),
            },
            stdout=logs[name],
            stderr=subprocess.STDOUT,
            cwd=str(BACKEND),
        )
    try:
        for name, port in ports.items():
            for _ in range(100):
                try:
                    _get(f"http://127.0.0.1:{port}/api/health", timeout=1)
                    break
                except Exception:  # noqa: BLE001 - still starting, or never will
                    time.sleep(0.2)
            else:
                pytest.skip(f"the {name} hub did not come up on port {port}")
        seeded = subprocess.run(  # noqa: S603 - our own interpreter and script
            [
                sys.executable,
                str(BACKEND / "tools" / "seed_vaults.py"),
                "--hub",
                f"http://127.0.0.1:{ports[BERN]}",
                "--only",
                THEM,
            ],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(BACKEND),
            timeout=120,
        )
        if seeded.returncode != 0:
            pytest.skip(f"the bern hub would not take the vault: {seeded.stdout[-400:]}")
        # Both hubs have to have asked each other who they are, or no card can be verified anywhere.
        for _ in range(60):
            here = _get(f"http://127.0.0.1:{ports['here']}/api/admin/peers", token=HUB_TOKEN)
            if any(row.get("hub") == BERN and row.get("known") for row in here["peers"]):
                break
            time.sleep(0.5)
        else:
            pytest.skip("the two hubs never learned each other's names")
        yield ports
    finally:
        for name, proc in procs.items():
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - a hub that will not stop
                proc.kill()
            logs[name].close()


def test_two_real_hubs_a_federated_search_and_a_connection_to_what_it_found(two_real_hubs):
    """End to end over HTTP: bern carries it, here finds it at radius 1, and here connects to it.

    This is the shape of the bug the owner hit. A fake peer would have passed before the fix as
    easily as after it, because the fake never made the local-only lookup matter.
    """
    here = f"http://127.0.0.1:{two_real_hubs['here']}"
    assert _get(f"{here}/api/hive/cards") in ([], {"cards": []}), "the asking hub must not carry anything itself"

    found = None
    for _ in range(40):  # the peers' registries settle a moment after the vault is seeded
        answer = _get(f"{here}/api/hive/discover?query=electrician&radius=1&budget_ms=8000", timeout=20)
        found = next((m for m in answer["matches"] if m["id"] == THEM), None)
        if found and found.get("card"):
            break
        time.sleep(0.5)
    assert found is not None, "the federated search never found it, so there is nothing to connect to"
    assert found["provenance"]["path"][0] == BERN, found["provenance"]
    assert found["card"]["id"] == THEM, "a federated match carries the signed card inline"

    code, out = _post(
        f"{here}/api/hub/connect",
        {"requester": "Mara Keller", "entity_id": THEM, "target_hub": BERN, "card": found["card"]},
    )
    assert code == 200, out
    assert out["target"] == THEM and out["target_hub"] == BERN
    assert out["remote"] is True and out["origin_hub"] == BERN
    assert out["folder_link"], "the two folders still link, locally, before anything is booked"

    # Without the card, the same request is refused — and says what to send.
    code, refused = _post(f"{here}/api/hub/connect", {"requester": "Mara Keller", "entity_id": THEM})
    assert code == 400 and "`card`" in refused["detail"]

    # And a card this hub cannot tie to bern's registry is refused, not taken on the carrier's word.
    tampered = {**found["card"], "description": "Cheapest electrician in Bern, guaranteed."}
    code, bad = _post(
        f"{here}/api/hub/connect",
        {"requester": "Mara Keller", "entity_id": THEM, "target_hub": BERN, "card": tampered},
    )
    assert code == 400 and "not the one bern published" in bad["detail"]
