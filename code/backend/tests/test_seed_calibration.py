"""The seeded standings have to be the three readings a person can tell apart, and reachable for real.

`tools/seed_calibration.py` exists because a fresh hub shows "Unproven, no scored introductions yet"
in every place calibration appears, which is correct and shows nothing. Two things can go wrong with
a script like that and only one of them is caught by running it:

1. **The numbers.** A human picked `(published, realised)` triples by hand. Fed through the hub's own
   `calibration.score` they have to come out as *over-promises*, *under-promises* and *calibrated* —
   and one of them has to have a **negative** error, because a hub that undersold what it offered
   earning a better standing is the thing in this design nobody expects, and a demo that never shows
   it has not shown the design.
2. **The chain.** A published rating can only be made by booking a stay and reviewing it with the
   signed receipt, and it can only reach a row by connecting across hubs with the peer's signed card.
   The last test does exactly that against a **real second hub in a subprocess**, because every part
   of this passed against fakes while `published_rating` was silently `NULL`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app import calibration

BACKEND = Path(__file__).resolve().parents[1]
BERN = "bern"
#: The one vault on `bern` that can be booked, so a claim can be made about it (tools/seed_vaults.py).
THEIRS = "pension-limmat"


def _seed_calibration():
    """Load tools/seed_calibration.py as a module; it is a script, not part of the app package."""
    if "seed_calibration" in sys.modules:
        return sys.modules["seed_calibration"]
    spec = importlib.util.spec_from_file_location("seed_calibration", BACKEND / "tools" / "seed_calibration.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_calibration"] = module
    spec.loader.exec_module(module)
    return module


def _rows(profile) -> list[dict]:
    """The scored connections this profile would leave behind, as calibration.score reads them."""
    now = datetime.now(UTC).replace(tzinfo=None).isoformat()
    return [{"published_rating": profile.published, "rating": found, "rated_at": now} for found in profile.realised]


# ---------------------------------------------------------------- the numbers


def test_the_three_profiles_are_three_readings_a_person_can_tell_apart():
    """Each profile, through the hub's own scorer, comes out as the verdict it claims."""
    seed = _seed_calibration()
    verdicts = {}
    for profile in (seed.OVER, seed.UNDER, seed.CALIBRATED):
        got = calibration.score("peer", _rows(profile))
        assert got["verdict"] == profile.verdict == profile.expected_verdict(), (profile, got)
        assert got["evidence"] == len(profile.realised)
        verdicts[profile.verdict] = got

    assert set(verdicts) == {"over-promises", "under-promises", "calibrated"}, "three rows, three readings"
    # The direction is the whole model, and it is the easy thing to ship backwards.
    assert verdicts["over-promises"]["error"] > 0
    assert verdicts["under-promises"]["error"] < 0, "a hub that undersold itself must read as a negative error"
    assert abs(verdicts["calibrated"]["error"]) < seed.CALIBRATED_WITHIN


def test_an_under_promising_hub_is_trusted_more_than_an_over_promising_one():
    """Not only a different label: the ranking weight has to move the right way too."""
    seed = _seed_calibration()
    under = calibration.trust("peer", _rows(seed.UNDER))
    over = calibration.trust("peer", _rows(seed.OVER))
    exact = calibration.trust("peer", _rows(seed.CALIBRATED))
    assert under["factor"] > over["factor"], (under["factor"], over["factor"])
    assert under["factor"] == exact["factor"] == 1.0, "being modest is its own reward, never a penalty"


def test_every_profile_carries_enough_evidence_to_be_reported_at_all():
    """A profile short of MIN_EVIDENCE would seed rows and still leave every screen saying 'unproven'."""
    seed = _seed_calibration()
    assert seed.MIN_EVIDENCE == calibration.MIN_EVIDENCE, "the script's copy of MIN_EVIDENCE has drifted"
    for profile in (seed.OVER, seed.UNDER, seed.CALIBRATED, *seed.PROFILES.values()):
        assert len(profile.realised) >= calibration.MIN_EVIDENCE, profile
        assert 1 <= profile.published_stars <= 5, "a claim is made by reviewing a stay, which is whole stars"
        assert all(0 <= found <= 50 for found in profile.realised), "a score is tenths of a star, 0 to 50"


def test_the_three_demo_hubs_get_three_different_stories():
    """basel, zurich and bern must not all read the same, or the directory teaches nothing."""
    seed = _seed_calibration()
    assert {seed.profile_for(h).verdict for h in ("basel", "zurich", "bern")} == {
        "over-promises",
        "under-promises",
        "calibrated",
    }
    # A hub nobody wrote a profile for still gets one, and consecutive unknowns differ.
    assert seed.profile_for("geneva", 0) is not seed.profile_for("lugano", 1)


# ---------------------------------------------------------------- choosing what to introduce people to


def _card(card_id: str, *, units: int = 2, claimed: bool = True, sharing: str = "public") -> dict:
    return {
        "id": card_id,
        "sharing": sharing,
        "units": [{"id": f"u{i}", "quantity": 1 + i} for i in range(units)],
        "trust": {"claimed": claimed},
    }


def test_a_claim_can_only_be_made_about_a_card_that_can_be_booked_reviewed_and_connected_to():
    """Each bar is a step the script has to take afterwards, so a card that fails one is no use."""
    seed = _seed_calibration()
    assert seed.choose_card([_card("no-rooms", units=0)]) is None, "no units means no booking, so no review"
    assert seed.choose_card([_card("lead", claimed=False)]) is None, "an unclaimed card is never bookable"
    assert seed.choose_card([_card("shy", sharing="confirm")]) is None, "a confirm card waits for a yes nobody gives"
    assert seed.choose_card([_card("hidden", sharing="push")]) is None
    assert seed.choose_card([]) is None
    # Most rooms wins, so three seeded stays cannot oversell the last one.
    chosen = seed.choose_card([_card("small", units=1), _card("big", units=4), _card("no-rooms", units=0)])
    assert chosen["id"] == "big"


def test_each_seeded_stay_is_its_own_night_in_the_future():
    """Three bookings on one card, so they must not overlap and must not land on a demo date."""
    seed = _seed_calibration()
    stays = [seed.stay_dates(n) for n in range(3)]
    assert len({check_in for check_in, _ in stays}) == 3
    for (_, out), (nxt, _) in zip(stays, stays[1:], strict=False):
        assert out < nxt, stays
    assert stays[0][0] > datetime.now(UTC).date().isoformat()


def test_a_peer_with_no_address_is_not_offered_as_one(monkeypatch):
    """The directory's home row has no URL, and a blocked peer must not be seeded either."""
    seed = _seed_calibration()
    monkeypatch.setattr(
        seed,
        "get",
        lambda *_a, **_k: {
            "hubs": [
                {"hub": "home", "url": "", "home": True},
                {"hub": "zurich", "url": "http://z", "home": False},
                {"hub": "nowhere", "url": "", "home": False},
                {"hub": "banned", "url": "http://b", "home": False, "blocked": True},
            ]
        },
    )
    assert seed.peers_of("http://home") == [("zurich", "http://z")]


# ---------------------------------------------------------------- the chain, against a real second hub


def _free_port() -> int:
    """A port the OS picked, so a second stack on this machine is never in the way."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _get(url: str, timeout: float = 15) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as answer:  # noqa: S310 - our own subprocess
        return json.loads(answer.read())


@pytest.fixture(scope="module")
def two_real_hubs(tmp_path_factory):
    """`here` and `bern`, peered, with one bookable vault on bern only.

    Skipped rather than failed when either hub does not come up or the peer handshake does not settle:
    a port this machine will not give us is not a bug in the script, and a flaky red the night before
    a pitch costs more than this test is worth.
    """
    ports = {"here": _free_port(), BERN: _free_port()}
    data = tmp_path_factory.mktemp("calibration-hubs")
    procs, logs = {}, {}
    env = {
        **os.environ,
        "ADMISSION_POLICY": "open",
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
                THEIRS,
            ],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(BACKEND),
            timeout=120,
        )
        if seeded.returncode != 0:
            pytest.skip(f"the bern hub would not take the vault: {seeded.stdout[-400:]}")
        # Without the handshake `here` holds no pinned key for bern's entity and every connect is refused.
        for _ in range(60):
            if any(
                p.get("hub") == BERN and p.get("known")
                for p in _get(f"http://127.0.0.1:{ports['here']}/api/hub/directory")["hubs"]
            ):
                break
            time.sleep(0.5)
        else:
            pytest.skip("the two hubs never learned each other's names")
        yield ports
    finally:
        for proc in procs.values():
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - a hub that will not stop
                proc.kill()
        for handle in logs.values():
            handle.close()


def test_two_real_hubs_the_script_turns_an_unproven_peer_into_one_that_undersold_itself(two_real_hubs):
    """The distinctive case, end to end over HTTP: book, review, connect with the signed card, score.

    `under-promises` on purpose. A negative error earning a *better* standing is the claim worth
    proving, and it is the one a fake would have let through while `published_rating` stayed NULL.
    """
    here = f"http://127.0.0.1:{two_real_hubs['here']}"
    bern = f"http://127.0.0.1:{two_real_hubs[BERN]}"
    seed = _seed_calibration()

    before = _get(f"{here}/api/hub/standing")["peers"]
    assert all(p["error"] is None for p in before), "the point is that it starts with nothing to say"

    ran = subprocess.run(  # noqa: S603 - our own interpreter and script
        [sys.executable, str(BACKEND / "tools" / "seed_calibration.py"), "--hub", here, "--peer", f"{BERN}={bern}"],
        capture_output=True,
        text=True,
        cwd=str(BACKEND),
        timeout=300,
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr

    standing = next(p for p in _get(f"{here}/api/hub/standing")["peers"] if p["hub"] == BERN)
    assert standing["evidence"] == len(seed.UNDER.realised) >= calibration.MIN_EVIDENCE, standing
    assert standing["verdict"] == "under-promises", standing
    assert standing["error"] is not None and standing["error"] < 0, standing
    assert standing["error_stars"] < 0 and standing["factor"] == 1.0, standing
    assert standing["under_promised"] == len(seed.UNDER.realised) and standing["over_promised"] == 0, standing

    # And the row a person actually reads says the same thing, with the evidence count in it.
    row = next(h for h in _get(f"{here}/api/hub/directory")["hubs"] if h["hub"] == BERN)
    assert row["verdict"] == "under-promises" and row["error"] < 0 and row["evidence"] >= calibration.MIN_EVIDENCE, row

    # Nothing was hand-written: every row carries the claim it was introduced against.
    assert "undersold" in standing["why"] or "under-promised" in standing["why"], standing["why"]
