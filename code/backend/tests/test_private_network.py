"""Chrome's Private Network Access preflight, which decides whether a LAN demo works at all."""

from __future__ import annotations

PREFLIGHT = {
    "Origin": "http://172.20.10.7:8440",
    "Access-Control-Request-Method": "GET",
    "Access-Control-Request-Private-Network": "true",
}


def test_a_private_network_preflight_is_answered_not_refused(client):
    """Issue #75: Safari opened the LAN hub and Chrome did not.

    A page on a private address calling another private address makes Chrome preflight with
    `Access-Control-Request-Private-Network` and refuse unless the server answers. Starlette
    rejects it outright — 400, "Disallowed CORS private-network" — until `allow_private_network`
    is set, so Chrome failed where Safari, which never asks, succeeded. The ten-minute preflight
    cache made it look intermittent rather than broken.
    """
    res = client.options("/api/health", headers=PREFLIGHT)

    assert res.status_code != 400, f"preflight refused: {res.text}"
    assert res.headers.get("access-control-allow-private-network") == "true"
    assert res.headers.get("access-control-allow-origin")


def test_an_ordinary_preflight_still_works(client):
    """The fix must not change anything for a caller that never asks about private networks."""
    res = client.options(
        "/api/health", headers={"Origin": "https://example.test", "Access-Control-Request-Method": "GET"}
    )

    assert res.status_code != 400
    assert "access-control-allow-private-network" not in res.headers, "only answered when asked"
