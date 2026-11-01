"""Request guards for the public demo: shared-secret headers, admin sign-in and rate limits on paid Claude calls.

The Hive's read and booking APIs are public by design (agents need them). What is guarded is what costs money
(Claude runs) or changes a business without its owner (card edits, reset), and who may run the hub itself.

Administration takes two kinds of credential, both in `X-Admin-Token`: the static `ADMIN_TOKEN` for curl and CI,
and a short-lived session token a person gets by posting the `ADMIN_PASSWORD` to `/api/admin/login`. Neither is
ever logged. With neither configured, administration is refused rather than left open.

## One budget per costly operation, whichever transport asks

This hub is reachable two ways: REST, and MCP at `/mcp`. The same costly work sits behind both, so a budget
that only one of them spends is not a budget — a caller refused at the REST door used to walk in through the
MCP one and run the same peer fan-out and the same paid search. Every `RateLimiter` below is one object with
one hub-global window, so REST and MCP spending it are spending the same thing; what the transports differ in
is only how the principal is found.

This is the whole of the client-attribution policy, written out rather than implied:

| operation | REST door | MCP door | in-process agent |
| --- | --- | --- | --- |
| `hive_discover`, `radius > 0` | `federated`, per address | `federated`, per address | `federated`, as one principal |
| `hub_connect` | `federated`, per address | `federated`, per address | `federated`, as one principal |
| `hub_register` | `federated`, per address | `federated`, per address | `federated`, as one principal |
| `hive_scout` (web search, paid) | `llm_calls`, per address | `llm_calls`, per address | spent by `POST /api/agent` |
| `explore_ask` | `llm_calls`, per address | not charged: cannot reach a model | n/a |
| `hive_owner_propose` | `llm_calls`, per address | `llm_calls`, per card | refused: no owner token there |

`explore_ask` is the row to check rather than assume. Its REST twin passes `judge=config.LLM_ENABLED` and so
can reach a model; the MCP tool never passes `judge` at all and cannot, on any configuration. Charging it
would be inventing a cost, so it is left free and said so here.

The last column is the one worth reading twice. `POST /api/agent` spends `llm_calls` for the run before the
agent starts, so charging the agent's own `hive_scout` call again would bill one admission twice. It never
spends `federated`, so the agent's federated discovery is charged here or nowhere — and a hub with no model
key does not spend `llm_calls` at that door at all, which would otherwise leave peer fan-out free. In-process
calls share one principal because there is one agent behind them and no address to tell them apart by.
"""

import hmac
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import HTTPException, Request

from . import config

# A session token is signed with the password *and* a secret this process made at start. So tokens do not survive
# a restart, and changing the password ends every session that is out. Nothing is stored server-side to read.
_SESSION_SALT = secrets.token_bytes(32)
_SESSION_VERSION = "v1"
# Logout has to mean something, and a signed token cannot be un-signed: the macs of signed-out tokens are kept
# until they would have expired anyway. Bounded by the number of sign-outs in one session lifetime.
_signed_out: dict[str, int] = {}
_signed_out_lock = threading.Lock()


def secret_matches(given: str, expected: str) -> bool:
    """True when `given` is `expected`, compared in constant time. An unset `expected` matches nothing.

    The strict half of the pair: a caller that has no `Request` to raise an `HTTPException` at asks
    this instead. An MCP tool reads its credential off the transport rather than off a FastAPI
    request, and a write that can arrive from anywhere wants the unset secret to refuse everybody —
    the line `require_admin` draws for the blocklist, for the same reason.
    """
    return bool(expected) and hmac.compare_digest(given, expected)


def secret_ok(given: str, expected: str) -> bool:
    """True when `given` matches `expected`, or when no `expected` is configured: the check is off.

    What `require_secret` decides, as a value rather than an exception, so a caller without a
    `Request` makes the same decision from the same code.
    """
    return not expected or secret_matches(given, expected)


def require_secret(request: Request, header: str, expected: str) -> None:
    """Reject the request unless `header` matches `expected`. An empty `expected` means the check is off."""
    if not secret_ok(request.headers.get(header, ""), expected):
        raise HTTPException(403, f"Missing or wrong {header}.")


def admin_configured(token: str, password: str) -> bool:
    """True when this hub has any way of proving an operator: a static token, a password, or both."""
    return bool(token or password)


def require_admin(token: str | None, expected: str, password: str = "") -> None:
    """Admin writes fail closed: no configured credential means refused, not open.

    `require_secret` treats an empty secret as "the check is off", which is right for an owner
    editing their own card and wrong for the blocklist. A hub whose blocklist anyone can edit has
    no blocklist, so an unset ADMIN_TOKEN *and* ADMIN_PASSWORD locks the door instead of removing it.

    `token` is whatever arrived in `X-Admin-Token`: either the static secret, or a session token from
    `/api/admin/login`. Both are compared in constant time.
    """
    if not admin_configured(expected, password):
        raise HTTPException(503, "This hub has no ADMIN_TOKEN or ADMIN_PASSWORD set, so administration is disabled.")
    token = token or ""
    if expected and hmac.compare_digest(token, expected):
        return
    if valid_admin_session(token, password):
        return
    raise HTTPException(403, "Missing, wrong or expired X-Admin-Token.")


def credential_kind(token: str | None, static_token: str) -> str:
    """Which credential an accepted admin request used, for the ledger. Never the credential itself.

    Called only after `require_admin` has already accepted the request, so anything that is not the
    static token is a session token it minted. Compared in constant time like every other use.
    """
    if static_token and hmac.compare_digest(token or "", static_token):
        return "static token"
    return "session"


def check_admin_password(given: str, expected: str) -> bool:
    """Compare a typed password with the configured one in constant time. Never `==`, never logged."""
    if not expected:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


def _sign(payload: str, password: str) -> str:
    """The mac over a session token's payload, keyed by this process's salt and the configured password."""
    return hmac.new(_SESSION_SALT + password.encode(), payload.encode(), "sha256").hexdigest()


def mint_admin_session(password: str, ttl_s: int) -> str:
    """Return an opaque session token that stops working after `ttl_s` seconds.

    The token is `v1.<expiry>.<mac>` and carries nothing else: no identity, no permissions, nothing an
    attacker learns by decoding it. A negative `ttl_s` mints an already-expired token, which the tests use.
    """
    expiry = int(time.time()) + int(ttl_s)
    payload = f"{_SESSION_VERSION}.{expiry}"
    return f"{payload}.{_sign(payload, password)}"


def valid_admin_session(token: str, password: str) -> bool:
    """True when `token` is one of our own session tokens, still inside its lifetime and not signed out."""
    if not password or not token:
        return False
    version, _, rest = token.partition(".")
    expiry_s, _, mac = rest.partition(".")
    if version != _SESSION_VERSION or not mac or not expiry_s.lstrip("-").isdigit():
        return False
    if not hmac.compare_digest(mac, _sign(f"{version}.{expiry_s}", password)):
        return False
    if int(expiry_s) <= int(time.time()):
        return False
    with _signed_out_lock:
        return mac not in _signed_out


def end_admin_session(token: str) -> None:
    """Sign a session token out. Entries that would have expired anyway are dropped at the same time."""
    now = int(time.time())
    version, _, rest = token.partition(".")
    expiry_s, _, mac = rest.partition(".")
    if not mac:
        return
    with _signed_out_lock:
        for old, expiry in [*_signed_out.items()]:
            if expiry <= now:
                del _signed_out[old]
        _signed_out[mac] = int(expiry_s) if expiry_s.isdigit() else now


class RateLimiter:
    """Sliding-window limit per client plus one global cap, kept in memory (one backend instance)."""

    def __init__(self, per_client: int, total: int, window_s: int = 3600, what: str = "requests") -> None:
        self.per_client, self.total, self.window = per_client, total, window_s
        self.what = what
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, request: Request | None = None, key: str = "") -> None:
        """Count one call, or raise 429 when the client or the backend is over. The 429 says when to try again.

        `key` counts against something other than the caller's IP. A folder read is limited per
        *link*, because the link is what the hub granted and an IP is not: one agent behind a
        shared address must not spend another's budget, and moving address must not refill it.
        An MCP tool has no `Request` at all and always brings its own `key`.
        """
        now = time.monotonic()
        client = key or (request.client.host if request and request.client else "unknown")
        with self.lock:
            for key in (client, "*"):
                hits = self.hits[key]
                while hits and now - hits[0] > self.window:
                    hits.popleft()
            over = [k for k, cap in ((client, self.per_client), ("*", self.total)) if len(self.hits[k]) >= cap]
            if over:
                wait = self._retry_after(over, now)
                raise HTTPException(
                    429,
                    f"Too many {self.what}. Try again in {wait} s.",
                    headers={"Retry-After": str(wait)},
                )
            self.hits[client].append(now)
            self.hits["*"].append(now)

    def _retry_after(self, over: list[str], now: float) -> int:
        """Whole seconds until every over-budget window has room again. Called with the lock held."""
        waits = [self.window - (now - self.hits[k][0]) if self.hits[k] else self.window for k in over]
        return max(1, int(max(waits)) + 1)

    def forget(self, request: Request, key: str = "") -> None:
        """Drop this client's counted attempts, so a password typed right costs nothing lasting."""
        client = key or (request.client.host if request.client else "unknown")
        with self.lock:
            self.hits.pop(client, None)


def over_budget(limiter: RateLimiter, key: str) -> str:
    """Count one call against `limiter` and return why it is refused, or "" when it may run.

    The same budget the REST routes spend, for a caller with nowhere to raise an `HTTPException`:
    an MCP tool answers with an `error` its agent can read instead of a status code.
    """
    try:
        limiter.check(key=key)
    except HTTPException as err:
        return str(err.detail)
    return ""


# ---------------------------------------------------------------- who an MCP call is charged to
#
# An MCP tool has no `Request`, so the principal whose budget it spends has to come from somewhere. It comes
# off the **transport** and never off a tool argument: an argument is written by the caller, and a caller who
# gets to name their own principal has no budget at all. `mcp==2.3.0` hands a tool its originating request
# through `Context.request_context.request` — a Starlette `Request` over Streamable HTTP, and `None` on a
# transport that has no request at all (stdio, and this repo's own in-process agent).
#
# The address is `request.client.host`, which is the peer the ASGI server itself observed. `X-Forwarded-For`
# is a client-supplied string and is deliberately not read: behind a proxy that rewrote it this limits per
# proxy rather than per client, which undercounts callers and never miscounts one caller as another.

#: The principal every in-process MCP call is charged to. There is one agent behind them and no address to
#: tell them apart by, so they share one bucket rather than being quietly exempt.
IN_PROCESS = "mcp:in-process"


def mcp_client(ctx: Any) -> str:
    """Which caller an MCP tool call is charged to, read off the transport. `IN_PROCESS` when it has none.

    Never raises: a transport that turns out to carry no request, or a request with no peer address,
    is charged as one unknown caller rather than going uncounted.
    """
    request = getattr(getattr(ctx, "request_context", None), "request", None)
    client = getattr(request, "client", None)
    host = getattr(client, "host", "") or ""
    return f"mcp:{host}" if host else IN_PROCESS


def admit_mcp(limiter: RateLimiter, ctx: Any, *, charge_in_process: bool) -> str:
    """Spend one MCP call's budget and return why it is refused, or "" when the costly work may run.

    The admission boundary the REST routes reach through `RateLimiter.check` and the MCP tools reach
    through here: one `limiter` object, so the hub-global window either transport fills is the same
    window, and exhausting a budget through one of them refuses the other.

    `charge_in_process` is the deliberate half of the policy in this module's docstring. True for a
    budget no REST door spends on the agent's behalf (`federated`), so the agent's own calls are
    counted. False for one `POST /api/agent` has already spent for the whole run (`llm_calls`), where
    charging again would bill a single admission twice.
    """
    client = mcp_client(ctx)
    if client == IN_PROCESS and not charge_in_process:
        return ""
    return over_budget(limiter, client)


# One budget for everything that may call Claude: agent runs and owner edit proposals.
llm_calls = RateLimiter(per_client=config.LLM_CALLS_PER_CLIENT_HOUR, total=config.LLM_CALLS_TOTAL_HOUR)
# A search with a radius above 0 makes this hub fetch from its peers, so a stranger must not be able to use it
# as an amplifier. Peer URLs come from config only, never from the request.
federated = RateLimiter(per_client=30, total=300)
# Folder reads, counted per *link* and not per IP: the link is what was granted. Generous enough for
# an agent pulling a folder of CVs in one go, low enough that one link cannot hold the hub's workers.
folder_reads = RateLimiter(
    per_client=config.FOLDER_READS_PER_LINK_HOUR,
    total=config.FOLDER_READS_TOTAL_HOUR,
    what="folder reads",
)
# Simulated traffic writes demand events; keep it to demo use.
simulations = RateLimiter(per_client=20, total=200)
# The admin password. A few tries per client is more than a person who mistypes needs, and the global cap is what
# an attacker with a fresh IP per attempt runs into: a per-client limit alone counts for nothing against a botnet.
admin_logins = RateLimiter(
    per_client=config.ADMIN_LOGIN_PER_CLIENT,
    total=config.ADMIN_LOGIN_TOTAL,
    window_s=config.ADMIN_LOGIN_WINDOW_S,
    what="sign-in attempts",
)
