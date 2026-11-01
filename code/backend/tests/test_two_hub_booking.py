"""A booking is sent to the Hive that proposed it, proved against two real hubs over HTTP.

The bug in #105: discovery picked a hotel from MCP server B, approval sent `hive_book` to server A,
which had never heard of that card, and the hold was consumed for nothing. `approve()` built a fresh
`HiveConnections`, losing discovery's `origin` map, and `call()` fell back to the first server
advertising the tool.

`tests/test_hive.py` already pins the honest refusal when the held source is gone. What it cannot
pin is the half that needs two hubs that actually answer: that the booking lands on the selected one
and the other is left alone, and that re-ordering `HIVE_MCP_URLS` between the hold and the approval
does not redirect it. A fake second transport would have passed before the fix as easily as after,
because the fake never makes the routing matter.

The shape is the issue's own reproduction: `HIVE_MCP_URLS` is ordered alpha, beta; alpha carries no
cards at all and beta carries the hotels. So the hub that is **first**, and that the old fallback
would have picked, is exactly the one that has never heard of the held card. Alpha still advertises
`hive_book` — tools are registered whether or not a hub has data — so nothing but the stored source
can route this correctly.
"""

import asyncio
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

from app import agent, config

BACKEND = Path(__file__).resolve().parents[1]
GUEST = "Fictional Approver"
ASK = f"Book a dog-friendly hotel in Basel from 2027-03-08 to 2027-03-10 for {GUEST}."


def _free_port() -> int:
    """A port the OS picked, so a second stack on this machine is never in the way."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _get(url: str, timeout: float = 10) -> dict:
    """Fetch JSON from one of our own loopback hubs."""
    with urllib.request.urlopen(url, timeout=timeout) as answer:  # noqa: S310 - our own subprocess
        return json.loads(answer.read())


def _cards(base: str) -> list[dict]:
    """The cards one hub carries. `/api/hive/cards` answers with a bare list on some versions."""
    answer = _get(f"{base}/api/hive/cards")
    return answer if isinstance(answer, list) else answer.get("cards", [])


def _bookings(base: str, guest: str) -> list[dict]:
    """Every booking on that hub under `guest`, read back over its own REST surface.

    Read from the hub rather than from a shared database handle: the point of this test is that two
    separate processes with separate stores disagree about what happened, so asking each one is the
    only question worth putting.
    """
    found = []
    for card in _cards(base):
        overview = _get(f"{base}/api/owner/{card['id']}")
        found += [b for b in overview.get("bookings", []) if guest in str(b.get("guest_name", ""))]
    return found


@pytest.fixture(scope="module")
def two_hubs(tmp_path_factory):
    """Two seeded hubs in subprocesses, each with its own store, both serving MCP at /mcp/.

    Skipped rather than failed when either will not come up: a port this machine refuses is not a
    bug in the hub, and a flaky red on main the night before a pitch costs more than this is worth.
    """
    ports = {"alpha": _free_port(), "beta": _free_port()}
    data = tmp_path_factory.mktemp("twohubs")
    procs, logs = {}, {}
    env = {
        **os.environ,
        "ADMISSION_POLICY": "open",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "LLM_PROVIDER": "offline",
        "HIVE_PEER_URLS": "",
    }
    for name, port in ports.items():
        logs[name] = (data / f"{name}.log").open("w")
        procs[name] = subprocess.Popen(  # noqa: S603 - our own interpreter and module
            [sys.executable, "-m", "uvicorn", "app.main:app", "--app-dir", str(BACKEND), "--port", str(port)],
            env={
                **env,
                "HIVE_HUB_ID": name,
                "DUCKDB_PATH": str(data / f"{name}.duckdb"),
                # Only beta carries anything. Alpha is the first configured source and the one the
                # old fallback reached for, so it has to be the one that cannot serve the booking.
                "SEED_ON_EMPTY": "true" if name == "beta" else "false",
            },
            stdout=logs[name],
            stderr=subprocess.STDOUT,
            cwd=str(BACKEND),
        )
    try:
        for name, port in ports.items():
            for _ in range(150):
                try:
                    if _get(f"http://127.0.0.1:{port}/api/health", timeout=1):
                        break
                except Exception:  # noqa: BLE001 - still starting, or never will
                    time.sleep(0.2)
            else:
                pytest.skip(f"the {name} hub did not come up on port {port}")
        if not _cards(f"http://127.0.0.1:{ports['beta']}"):
            pytest.skip("the beta hub came up with an empty index, so there is nothing to book")
        if _cards(f"http://127.0.0.1:{ports['alpha']}"):
            pytest.skip("the alpha hub seeded itself, so it is no longer the hub that cannot serve the booking")
        yield {name: f"http://127.0.0.1:{port}" for name, port in ports.items()}
    finally:
        for proc in procs.values():
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:  # pragma: no cover - a hub that will not stop
                proc.kill()
        for handle in logs.values():
            handle.close()


def test_two_real_hubs_the_booking_lands_on_the_selected_source_and_the_other_is_untouched(
    client, two_hubs, monkeypatch
):
    """Hold a booking selected on the second source, then approve it with the first source still first."""
    alpha, beta = two_hubs["alpha"], two_hubs["beta"]
    monkeypatch.setattr(config, "HIVE_MCP_URLS", [f"{alpha}/mcp/", f"{beta}/mcp/"])

    run = asyncio.run(agent.run([{"role": "user", "content": ASK}]))
    pending = run["pending"]
    assert pending is not None, f"the agent held nothing to approve: {run.get('reply')}"

    assert (
        agent._HELD[pending["id"]][1]["_source"] == f"{beta}/mcp/"
    ), "the hold must carry the source that listed the card, not the first configured one"

    # Approved with alpha still first in the configuration: the old code took labels[0] and asked a
    # hub that has never heard of this card, which consumed the hold and booked nothing anywhere.
    done = asyncio.run(agent.approve(pending))

    assert done["booking"] is not None, f"the approval did not go through: {done['reply']}"
    assert len(_bookings(beta, GUEST)) == 1, "the booking did not land on the hub that proposed it"
    assert _bookings(alpha, GUEST) == [], "the first configured hub took a booking it never proposed"
