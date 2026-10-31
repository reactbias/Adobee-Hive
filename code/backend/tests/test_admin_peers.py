"""Managing the connected hubs while the hub is running.

"I cannot edit the connected hubs" was the first sentence of the complaint, and it was true:
`HIVE_PEER_URLS` is read from the environment, so a neighbour could only be added by editing a
deployment and restarting. These tests are about the two things that make the stored list real —
federation asks what is stored, and a removal sticks — plus the rule that an unreachable peer must
never make an admin page slow.

Every peer here is in-process. No sockets, so the suite still runs with no network.
"""

from __future__ import annotations

import pytest

from app import audit, config, db, federation, peers, reputation

TOKEN = "s3cret-for-tests"
ADMIN = {"X-Admin-Token": TOKEN}
ZURICH = "https://hive-zurich.example"
BERN = "https://hive-bern.example"


class Net:
    """A peer network that records who was asked. Keyed loosely, so a trailing slash is not a miss."""

    def __init__(self, *urls: str, dead: tuple[str, ...] = ()) -> None:
        self.live = {u.rstrip("/") for u in urls}
        self.dead = {u.rstrip("/") for u in dead}
        self.profiled: list[str] = []
        self.asked: list[str] = []

    async def profile(self, base_url: str) -> dict:
        """What a peer publishes about itself. A dead peer raises, as an unreachable one would."""
        url = base_url.rstrip("/")
        self.profiled.append(url)
        if url in self.dead or url not in self.live:
            raise ConnectionError("no answer")
        return {
            "hub_id": url.split("//")[-1],
            "name": f"Adobee Hive ({url.split('//')[-1].split('.')[0]})",
            "description": "A fictional neighbour.",
            "verification": "signed",
            "paid_placement": False,
            "ranking_policy": "No paid placement.",
            "owner_keys": {},
        }

    async def search(self, base_url: str, ask: dict, radius: int, budget_ms: float, seen: list[str]) -> dict:
        """Answer a forwarded query. The answer is empty; what is being tested is who was asked."""
        self.asked.append(base_url.rstrip("/"))
        return {"matches": [], "excluded": [], "ranking_policy": "No paid placement."}


@pytest.fixture
def admin(monkeypatch):
    """A hub with an admin token configured, and no peers stored or seeded."""
    monkeypatch.setattr(config, "ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    monkeypatch.setattr(config, "HIVE_HUB_ID", "basel")


@pytest.fixture(autouse=True)
def clean_peers(client):
    """An empty peer table before and after, so one test's neighbour is not another's."""
    peers.init()
    audit.init()
    with db.write() as cur:
        cur.execute("DELETE FROM hub_peers")
        cur.execute("DELETE FROM hub_admin_log")
    federation.forget()
    reputation.forget()
    yield
    with db.write() as cur:
        cur.execute("DELETE FROM hub_peers")
        cur.execute("DELETE FROM hub_admin_log")
    federation.forget()
    reputation.forget()


def _wire(monkeypatch, net: Net) -> Net:
    monkeypatch.setattr(federation, "DEFAULT_TRANSPORT", net)
    return net


# ---------------------------------------------------------------- the point of the whole thing


def test_a_peer_added_at_runtime_is_asked_during_a_federated_search(client, admin, monkeypatch):
    """No restart, no redeploy: federation reads the stored list, so the next search asks it."""
    net = _wire(monkeypatch, Net(ZURICH))
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])

    res = client.post(
        "/api/admin/peers", json={"url": ZURICH, "reason": "we share the tri-border region"}, headers=ADMIN
    )
    assert res.status_code == 200

    out = federation.run({"query": "dog-friendly"}, radius=1)
    assert net.asked == [ZURICH], "a peer an operator added was never asked"
    assert [p["hub"] for p in out["federation"]["asked"]] == ["hive-zurich.example"]


def test_a_removed_peer_is_not_asked(client, admin, monkeypatch):
    net = _wire(monkeypatch, Net(ZURICH, BERN))
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    for url in (ZURICH, BERN):
        client.post("/api/admin/peers", json={"url": url, "reason": "neighbour"}, headers=ADMIN)

    res = client.post(
        "/api/admin/peers/remove", json={"url": BERN, "reason": "they stopped answering weeks ago"}, headers=ADMIN
    )
    assert res.status_code == 200 and res.json()["state"] == peers.REMOVED

    federation.forget()
    federation.run({"query": "dog-friendly"}, radius=1)
    assert net.asked == [ZURICH], "a peer an operator removed is still being asked"


def test_a_peer_removed_at_runtime_does_not_come_back_from_the_environment(client, admin, monkeypatch):
    """The trap in seeding from env: the next restart would hand back the peer that was dropped."""
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [ZURICH])
    peers.init()  # a fresh hub seeds its environment list

    assert peers.urls() == [ZURICH]
    peers.remove(ZURICH, "they sell placement")

    assert peers.urls() == [], "the environment put a removed peer back"
    peers.init()  # and a restart must not either
    assert peers.urls() == []


def test_the_environment_is_still_the_seed_for_a_fresh_hub(client, admin, monkeypatch):
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [ZURICH, BERN])
    peers.init()

    rows = {r["url"]: r for r in peers.listing()}
    assert set(rows) == {ZURICH, BERN}
    assert all(r["state"] == peers.ACTIVE for r in rows.values())
    assert all("HIVE_PEER_URLS" in row["reason"] for row in audit.entries(action_prefix="peer.add"))


# ---------------------------------------------------------------- what an operator sees and does


def test_the_peer_table_carries_what_an_operator_acts_on(client, admin, monkeypatch):
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    client.post(
        "/api/admin/peers",
        json={"url": ZURICH, "reason": "regional partner", "name": "Adobee Hive (Zurich)"},
        headers=ADMIN,
    )

    row = client.get("/api/admin/peers", headers=ADMIN).json()["peers"][0]
    assert row["url"] == ZURICH
    assert row["hub"] == "hive-zurich.example"
    assert row["name"] == "Adobee Hive (Zurich)"
    assert row["answers"] is None, "nobody has asked yet, which is not the same as a refusal"
    assert {"verdict", "error", "evidence", "blocked", "state"} <= set(row)


def test_a_peer_can_be_edited(client, admin, monkeypatch):
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    client.post("/api/admin/peers", json={"url": ZURICH, "reason": "neighbour"}, headers=ADMIN)

    res = client.put(
        "/api/admin/peers",
        json={"url": ZURICH, "reason": "they renamed themselves", "name": "Hive Zürich", "hub_id": "zurich.swiss"},
        headers=ADMIN,
    )
    assert res.status_code == 200
    row = client.get("/api/admin/peers", headers=ADMIN).json()["peers"][0]
    assert row["name"] == "Hive Zürich" and row["hub"] == "zurich.swiss"


@pytest.mark.parametrize("path", ["/api/admin/peers", "/api/admin/peers/remove"])
def test_a_peer_change_with_an_empty_reason_is_refused_at_the_door(client, admin, path):
    assert client.post(path, json={"url": ZURICH, "reason": ""}, headers=ADMIN).status_code == 422


@pytest.mark.parametrize("path", ["/api/admin/peers", "/api/admin/peers/remove"])
def test_a_peer_change_with_a_blank_reason_is_refused_by_the_rule_not_only_the_schema(client, admin, path):
    """A reason of spaces passes `min_length=1` and is not a reason. The module has to refuse it too."""
    res = client.post(path, json={"url": ZURICH, "reason": "   "}, headers=ADMIN)

    assert res.status_code == 400 and "reason" in res.json()["detail"]
    assert peers.listing() == [], "a refused change left a row behind"


def test_the_rule_is_in_the_module_so_mcp_and_curl_get_the_same_answer(client, admin):
    """Checked against `peers` directly: a caller that skips the REST schema must still be refused."""
    with pytest.raises(peers.PeerError):
        peers.add(ZURICH, reason=" ")
    with pytest.raises(peers.PeerError):
        peers.edit(ZURICH, reason="", name="x")
    assert peers.listing() == []


def test_a_peer_url_that_is_not_an_http_address_is_refused(client, admin, monkeypatch):
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    res = client.post("/api/admin/peers", json={"url": "file:///etc/passwd", "reason": "oops"}, headers=ADMIN)
    assert res.status_code == 400 and "http" in res.json()["detail"]
    assert peers.listing() == []


def test_adding_the_same_peer_twice_is_told_rather_than_ignored(client, admin, monkeypatch):
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    client.post("/api/admin/peers", json={"url": ZURICH, "reason": "neighbour"}, headers=ADMIN)
    res = client.post("/api/admin/peers", json={"url": ZURICH, "reason": "neighbour"}, headers=ADMIN)
    assert res.status_code == 400 and "already" in res.json()["detail"]


def test_every_peer_change_is_in_the_ledger_with_its_reason(client, admin, monkeypatch):
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    client.post("/api/admin/peers", json={"url": ZURICH, "reason": "regional partner"}, headers=ADMIN)
    client.post("/api/admin/peers/remove", json={"url": ZURICH, "reason": "they sell placement"}, headers=ADMIN)

    rows = client.get("/api/admin/audit", params={"action": "peer."}, headers=ADMIN).json()["entries"]
    assert {r["action"] for r in rows} == {"peer.add", "peer.remove"}
    assert {r["reason"] for r in rows} == {"regional partner", "they sell placement"}
    assert all(r["subject"] == ZURICH and r["actor"] == "admin" for r in rows)


# ---------------------------------------------------------------- an unreachable peer


def test_the_peer_page_never_fetches_from_a_peer(client, admin, monkeypatch):
    """The rule: one dead neighbour must not make an admin page slow or blank. So no page fetches."""
    net = _wire(monkeypatch, Net(dead=(ZURICH,)))
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    client.post("/api/admin/peers", json={"url": ZURICH, "reason": "neighbour"}, headers=ADMIN)

    for path in ("/api/admin/peers", "/api/admin/overview", "/api/admin/neighbours"):
        assert client.get(path, headers=ADMIN).status_code == 200
    assert net.profiled == [], "an admin page reached out to a peer while rendering"


def test_a_peer_that_does_not_answer_is_recorded_as_such_rather_than_raising(client, admin, monkeypatch):
    net = _wire(monkeypatch, Net(ZURICH, dead=(BERN,)))
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    for url in (ZURICH, BERN):
        client.post("/api/admin/peers", json={"url": url, "reason": "neighbour"}, headers=ADMIN)

    out = client.post("/api/admin/peers/check", headers=ADMIN).json()
    rows = {r["url"]: r for r in out["peers"]}

    assert rows[ZURICH]["answers"] is True and rows[ZURICH]["last_checked_at"]
    assert rows[BERN]["answers"] is False
    assert rows[BERN]["last_error"], "an operator needs to know what went wrong, not only that it did"
    assert set(net.profiled) == {ZURICH, BERN}


def test_a_probe_fills_in_the_name_a_peer_tells_us_and_never_overwrites_the_operator_s(client, admin, monkeypatch):
    _wire(monkeypatch, Net(ZURICH, BERN))
    monkeypatch.setattr(config, "HIVE_PEER_URLS", [])
    client.post("/api/admin/peers", json={"url": ZURICH, "reason": "neighbour"}, headers=ADMIN)
    client.post(
        "/api/admin/peers", json={"url": BERN, "reason": "neighbour", "name": "Our Bern friends"}, headers=ADMIN
    )

    rows = {r["url"]: r for r in client.post("/api/admin/peers/check", headers=ADMIN).json()["peers"]}
    assert rows[ZURICH]["name"] == "Adobee Hive (hive-zurich)"
    assert rows[BERN]["name"] == "Our Bern friends", "what the operator typed wins over what a peer claims"


# ---------------------------------------------------------------- the door


READS = ["/api/admin/peers"]
WRITES = [
    ("post", "/api/admin/peers", {"url": ZURICH, "reason": "x"}),
    ("put", "/api/admin/peers", {"url": ZURICH, "reason": "x", "name": "x"}),
    ("post", "/api/admin/peers/remove", {"url": ZURICH, "reason": "x"}),
    ("post", "/api/admin/peers/check", None),
]


@pytest.mark.parametrize("path", READS)
def test_every_new_read_refuses_without_the_admin_token(client, admin, path):
    assert client.get(path).status_code == 403
    assert client.get(path, headers={"X-Admin-Token": "wrong"}).status_code == 403


@pytest.mark.parametrize("method,path,body", WRITES)
def test_every_new_write_refuses_without_the_admin_token(client, admin, method, path, body):
    call = getattr(client, method)
    assert call(path, json=body).status_code == 403
    assert call(path, json=body, headers={"X-Admin-Token": "wrong"}).status_code == 403
    assert peers.listing() == [], "a refused write changes nothing"


@pytest.mark.parametrize("method,path,body", WRITES)
def test_a_peer_write_fails_closed_when_this_hub_has_no_credential(client, monkeypatch, method, path, body):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    monkeypatch.setattr(config, "ADMIN_PASSWORD", "")
    assert getattr(client, method)(path, json=body).status_code == 503
