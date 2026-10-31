"""FastAPI entry point: REST for the web app, MCP for agents.

/api/...           JSON API used by the React frontend
/mcp/              the Hive MCP server (Streamable HTTP) for any AI agent
/.well-known/hive.json   discovery document pointing agents to the MCP endpoint
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import (
    activity,
    admin,
    agent,
    audit,
    blocklist,
    config,
    connections,
    db,
    federation,
    guard,
    hive,
    hive_seed,
    hub,
    limits,
    mcp_server,
    owner,
    peers,
    registration,
    removals,
    replies,
    rulesets,
    services,
    simulate,
    waiting,
)
from .domains import explore, scout

logging.basicConfig(level=logging.INFO)

mcp_app = mcp_server.http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Open the database, seed it if empty, and run the MCP session manager for the app's lifetime."""
    db.init()
    hive.init()
    waiting.init()
    activity.init()
    blocklist.init()
    connections.init()
    registration.init()
    audit.init()
    removals.init()
    peers.init()
    services.init()
    if config.SEED_ON_EMPTY:
        hive_seed.seed_if_empty()
    # A hub with peers configured asks them who they are straight away and then on a timer, so the directory
    # knows their names without waiting for somebody to run a federated search. Reads never fan out.
    asking = None
    if config.HIVE_PEER_URLS and config.PEER_ASK_SECONDS > 0:
        asking = asyncio.create_task(federation.keep_peers_fresh())
    async with mcp_app.router.lifespan_context(mcp_app):
        yield
    if asking is not None:
        asking.cancel()
    db.close()


app = FastAPI(title="Adobee Hive", version="0.1.0", lifespan=lifespan)


# Nothing in FastAPI or uvicorn bounds a request body: a 20 MB application was read into memory,
# parsed into objects and stored before any check of ours ran. This refuses by size first.
app.add_middleware(limits.BodyLimit)


app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    # Chrome's Private Network Access: a page on a private address calling another private
    # address preflights with `Access-Control-Request-Private-Network` and refuses unless the
    # server answers it. Without this a LAN demo works in Safari, which never asks, and fails in
    # Chrome — intermittently, because the preflight is cached for ten minutes. Starlette rejects
    # it outright ("Disallowed CORS private-network") until this is set.
    allow_private_network=True,
    expose_headers=["mcp-session-id"],
)
app.mount("/mcp", mcp_app)


def _hive_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (
        hive.HiveError,
        hub.HubError,
        connections.ConnectionError_,
        blocklist.BlockError,
        registration.RegistrationError,
        removals.RemovalError,
        peers.PeerError,
        services.ServiceError,
    ) as err:
        raise HTTPException(400, str(err)) from err


# ---------------------------------------------------------------- meta


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Report whether the backend is up and which model vendor the agents use."""
    claude = services.provider() == "claude"
    return {
        "status": "ok",
        # The vendor in use, never a key and never a fingerprint: /api/health is public.
        "llm": services.provider() if services.enabled() else "mock",
        "model": config.CLAUDE_MODEL if claude else config.OPENAI_MODEL,
        "fast_model": config.CLAUDE_FAST_MODEL if claude else config.OPENAI_MODEL,
        "hives": config.HIVE_MCP_URLS or ["local"],
    }


@app.get("/.well-known/hive.json")
def well_known(request: Request) -> dict[str, Any]:
    """Discovery document so agents can find this Hive's MCP endpoint and policies."""
    base = str(request.base_url).rstrip("/")
    return {
        "name": config.HIVE_NAME,
        "description": config.HIVE_DESCRIPTION,
        "mcp": {"url": f"{base}/mcp/", "transport": "streamable-http"},
        "signature": "Ed25519 over canonical JSON; a card is valid only if signed by the key pinned for its id below",
        "owner_keys": hive.owner_keys(),
        "ruleset_keys": rulesets.keys(),
        "ranking_policy": hive.RANKING_POLICY,
        # What peer Hives judge this hub by when a query reaches them over it (see reputation.py), and what a
        # person choosing a hub decides by: its name, what it asks of a member, and how much it carries. A peer
        # reads this one document rather than interrogating four endpoints, and a peer that cannot reach it says
        # so rather than guessing.
        "federation": {
            "hub_id": config.HIVE_HUB_ID,
            "name": config.HIVE_NAME,
            "description": config.HIVE_DESCRIPTION,
            "verification": config.HIVE_VERIFICATION,
            "admission": config.ADMISSION_POLICY,
            "entities": len(hive.list_cards()),
            "paid_placement": False,
            "max_radius": federation.MAX_RADIUS,
        },
    }


# ---------------------------------------------------------------- Hive (businesses)


class Message(BaseModel):
    """One chat turn."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AgentRequest(BaseModel):
    """A conversation with the traveller agent; the last message is the traveller's."""

    messages: list[Message] = Field(min_length=1, max_length=20)
    # Demo only. "injection" adds an unverified mirror whose listing carries hidden instructions to agents.
    scenario: Literal["injection"] | None = None
    # Demo only. "off" runs an unguarded agent offline to show what it would do; it never books.
    rules: Literal["on", "off"] = "on"


class ApproveRequest(BaseModel):
    """The held hive_book call the traveller approves."""

    pending: dict[str, Any]


class BookRequest(BaseModel):
    """A direct booking from the human card page."""

    unit_id: str
    check_in: str
    check_out: str
    guest_name: str = Field(min_length=1, max_length=hive.MAX_NAME)
    guests: int = Field(1, ge=1, le=hive.MAX_GUESTS)
    notes: str = Field("", max_length=hive.MAX_TEXT)


class ReviewRequest(BaseModel):
    """A review, valid only with a signed booking receipt."""

    receipt: str = Field(max_length=4000)
    rating: int = Field(ge=1, le=5)
    text: str = Field("", max_length=hive.MAX_TEXT)


class OwnerEdit(BaseModel):
    """The owner's change, in plain words."""

    instruction: str = Field(min_length=1, max_length=1000)


class OwnerApply(BaseModel):
    """The card the owner reviewed and wants signed and published."""

    proposed: dict[str, Any]


@app.get("/api/hive/cards")
def hive_cards(kind: str | None = None) -> list[dict[str, Any]]:
    """List all cards, optionally one kind."""
    return hive.list_cards(kind)


# A repeated query parameter needs Query(); module-level, so it is not a call in a default (ruff B008).
FEATURES_QUERY = Query(None, description="Exact tags, repeated: features=quiet&features=dog-friendly")
SEEN_QUERY = Query(None, description="Hub ids this query already visited, so a hop never doubles back")


@app.get("/api/hive/discover")
async def hive_discover(
    request: Request,
    query: str = "",
    kind: str | None = None,
    near: str | None = None,
    max_price_chf: float | None = None,
    features: list[str] | None = FEATURES_QUERY,
    check_in: str | None = None,
    check_out: str | None = None,
    guests: int = Query(1, ge=1, le=hive.MAX_GUESTS),
    radius: int = Query(0, ge=0, le=federation.MAX_RADIUS),
    budget_ms: float = Query(federation.DEFAULT_BUDGET_MS, ge=0, le=20_000),
    seen: list[str] | None = SEEN_QUERY,
    looking_for: str = "offers",
) -> dict[str, Any]:
    """Search the Hive, and with radius above 0 its peer Hives too; radius 0 is this Hive only, as before.

    looking_for is which side of the market the caller is on: "offers" (the default) finds whoever provides the
    thing asked for, "needs" whoever wants what the caller provides, "any" both.

    This is also how one Hive forwards a query to another: a hop passes the radius it has left, the time budget
    left and the hubs the query has already visited (seen), which is how loops in the peer graph are cut.
    """
    if radius:
        guard.federated.check(request)  # a far search costs this hub outbound calls to its peers
    return await asyncio.to_thread(
        _hive_call,
        hive.discover,
        query,
        kind,
        near,
        max_price_chf,
        features,
        check_in,
        check_out,
        guests,
        radius,
        budget_ms,
        seen,
        looking_for,
    )


@app.get("/api/hive/cards/{card_id}")
def hive_card(card_id: str) -> dict[str, Any]:
    """Return one card by id or slug."""
    return _hive_call(hive.get_card, card_id)


@app.get("/api/hive/cards/{card_id}/availability")
def hive_availability(card_id: str, check_in: str, check_out: str, guests: int = 1) -> dict[str, Any]:
    """Return free units for the dates."""
    return _hive_call(hive.check_availability, card_id, check_in, check_out, guests)


@app.post("/api/hive/cards/{card_id}/book")
def hive_book(card_id: str, body: BookRequest) -> dict[str, Any]:
    """Human fallback: the same booking a person can make from the card page."""
    return _hive_call(
        hive.book,
        card_id,
        body.unit_id,
        body.check_in,
        body.check_out,
        body.guest_name,
        body.guests,
        body.notes,
        "human via card page",
    )


@app.post("/api/hive/reviews")
def hive_review(body: ReviewRequest) -> dict[str, Any]:
    """Leave a proof-of-stay review."""
    return _hive_call(hive.review, body.receipt, body.rating, body.text)


class VerifyRequest(BaseModel):
    """Any card, as an agent received it."""

    card: dict[str, Any]


@app.post("/api/hive/verify")
def hive_verify(body: VerifyRequest) -> dict[str, Any]:
    """Check a card as any agent would: a valid signature by the owner's pinned key. Used by the tamper demo."""
    return {"signature_valid": hive.verify_pinned(body.card, hive.owner_keys())}


@app.post("/api/hive/demo/forge/{card_id}")
def hive_forge_demo(card_id: str, request: Request) -> dict[str, Any]:
    """Tamper demo: a changed copy re-signed by a stranger's key, which must fail verification."""
    guard.simulations.check(request)
    return _hive_call(hive.forge_demo, card_id)


@app.get("/api/hive/demand")
def hive_demand(days: int = 7) -> dict[str, Any]:
    """Return the city demand map: what agents asked for and how often nobody could serve it."""
    return hive.demand_map(days)


@app.post("/api/demo/simulate")
def demo_simulate(request: Request, n: int = 40) -> dict[str, Any]:
    """Run up to 200 simulated traveller searches to fill the demand map."""
    guard.simulations.check(request)
    return simulate.run(min(n, 200))


@app.post("/api/demo/reset")
def demo_reset(request: Request) -> dict[str, Any]:
    """Clean slate before going on stage: the seed cards, no bookings, no demand history."""
    guard.require_secret(request, "X-Demo-Token", config.DEMO_RESET_TOKEN)
    hive_seed.reset()
    return {"cards": len(hive.list_cards())}


@app.post("/api/agent")
async def run_agent(body: AgentRequest, request: Request) -> dict[str, Any]:
    """Run the traveller agent over MCP. A booking comes back held, as pending."""
    if services.enabled() and body.rules == "on":  # the rules-off run is scripted and never reaches a model
        guard.llm_calls.check(request)
    try:
        locale = replies.locale_from(request.headers.get("accept-language", ""))
        result = await agent.run([m.model_dump() for m in body.messages], body.scenario, body.rules, locale)
    except Exception as err:  # log the details, show the UI a plain message
        logging.exception("agent run failed")
        raise HTTPException(502, "The agent could not finish this request. Try again.") from err
    return await asyncio.to_thread(activity.track, activity.from_agent_run, result)


@app.post("/api/agent/approve")
async def approve_booking(body: ApproveRequest, request: Request) -> dict[str, Any]:
    """The human's yes: the agent sends the booking it held back."""
    try:
        result = await agent.approve(body.pending, replies.locale_from(request.headers.get("accept-language", "")))
    except (ValueError, KeyError) as err:
        raise HTTPException(400, str(err)) from err
    return await asyncio.to_thread(activity.track, activity.from_approve, result)


class AskRequest(BaseModel):
    """A question for the Hive and, only if the person picked one, their mood."""

    question: str = Field(min_length=1, max_length=explore.MAX_QUESTION)
    mood: Literal["curious", "stressed", "planning", "celebrating"] | None = None
    pick: bool = False  # the person named one business from the last answer: hold its hand-off for a yes


class AskApprove(BaseModel):
    """The held action the person approves."""

    id: str = Field(min_length=1, max_length=64)


@app.post("/api/ask")
async def ask_hive(body: AskRequest, request: Request) -> dict[str, Any]:
    """Answer a question from the example cards. Anything transactional comes back held, as pending."""
    if config.LLM_ENABLED:
        guard.llm_calls.check(request)
    # With a key the model judges which cards cover the request; it runs off the event loop and falls back offline.
    result = await asyncio.to_thread(
        _hive_call, explore.ask, body.question, body.mood, judge=config.LLM_ENABLED, pick=body.pick
    )
    if config.LLM_ENABLED and result["replies"]:
        result = await asyncio.to_thread(explore.phrase, result)
    return await asyncio.to_thread(activity.track, activity.from_ask, result)


@app.post("/api/ask/approve")
def ask_approve(body: AskApprove) -> dict[str, Any]:
    """The person's yes: hand the held action off to the business."""
    return activity.track(activity.from_ask_approve, _hive_call(explore.approve, body.id))


class ScoutRequest(BaseModel):
    """A question no card answered: the scout looks for real businesses on the public web."""

    question: str = Field(min_length=1, max_length=explore.MAX_QUESTION)


@app.post("/api/ask/scout")
async def ask_scout(body: ScoutRequest, request: Request) -> dict[str, Any]:
    """Find, verify and add unclaimed cards from the public web when nothing in the Hive answers."""
    guard.llm_calls.check(request)  # web search and page fetches cost money and other sites' bandwidth
    result = await asyncio.to_thread(_hive_call, scout.find, body.question)
    return await asyncio.to_thread(activity.track, activity.from_scout, result)


@app.get("/api/activity")
def activity_feed(
    after: int = Query(0, ge=0), limit: int = Query(activity.PAGE, ge=1, le=activity.MAX_EVENTS)
) -> dict[str, Any]:
    """The live feed of what the agents do: one line per step, newer than `after`. No person, no question text."""
    return activity.recent(after, limit)


@app.get("/api/owner/{card_id}")
def owner_overview(card_id: str, request: Request) -> dict[str, Any]:
    """Return the owner studio data for one card. Without the owner token, guest names show as initials."""
    overview = _hive_call(hive.owner_overview, card_id)
    overview["waiting"] = waiting.owner_view(card_id)
    try:
        guard.require_secret(request, "X-Owner-Token", config.OWNER_EDIT_TOKEN)
    except HTTPException:
        for booking in overview["bookings"]:
            booking["guest_name"] = hive.mask_name(booking["guest_name"] or "")
    return overview


@app.post("/api/owner/{card_id}/propose")
async def owner_propose(card_id: str, body: OwnerEdit, request: Request) -> dict[str, Any]:
    """Turn the owner's words into a proposed card and a diff. Nothing is published yet."""
    guard.require_secret(request, "X-Owner-Token", config.OWNER_EDIT_TOKEN)
    if config.LLM_ENABLED:
        guard.llm_calls.check(request)
    return await asyncio.to_thread(_hive_call, owner.propose, card_id, body.instruction)


@app.post("/api/owner/{card_id}/publish")
def owner_publish(card_id: str, body: OwnerApply, request: Request) -> dict[str, Any]:
    """Sign and publish the card the owner approved."""
    guard.require_secret(request, "X-Owner-Token", config.OWNER_EDIT_TOKEN)
    return _hive_call(owner.apply, card_id, body.proposed)


# ---------------------------------------------------------------- the hub itself


class ConnectBody(BaseModel):
    """An agent asking to be introduced to something it found."""

    requester: str = Field(..., min_length=1, max_length=200, description="Who is asking, as their hub knows them")
    entity_id: str = Field(..., min_length=1, max_length=200, description="What they want to be connected to")
    target_hub: str = Field("", max_length=200)
    via_hub: str = Field("", max_length=200)


class ScoreBody(BaseModel):
    """A person scoring a real meeting, afterwards."""

    rating: int = Field(
        ...,
        ge=connections.MIN_STARS,
        le=connections.MAX_STARS,
        description="Tenths of a star: 43 is 4.3 stars out of 5",
    )
    note: str = Field("", max_length=500)


class BlockBody(BaseModel):
    """An operator shutting out a peer hub or a single entity."""

    kind: str = Field(..., pattern="^(hub|entity)$")
    subject: str = Field(..., min_length=1, max_length=200)
    reason: str = Field(..., min_length=1, max_length=500, description="Readable six months from now")


@app.post("/api/hub/connect")
def hub_connect(body: ConnectBody, request: Request) -> dict[str, Any]:
    """Ask to be introduced, and log it. A public item opens at once; one marked `confirm` waits."""
    guard.federated.check(request)
    return _hive_call(hub.connect, body.requester, body.entity_id, target_hub=body.target_hub, via_hub=body.via_hub)


@app.post("/api/hub/connections/{connection_id}/score")
def hub_score(connection_id: str, body: ScoreBody) -> dict[str, Any]:
    """Score an introduction after the real meeting. Once, and only while it is still open."""
    return _hive_call(hub.score, connection_id, body.rating, body.note)


@app.post("/api/hub/connections/{connection_id}/confirm")
def hub_confirm(connection_id: str) -> dict[str, Any]:
    """The owner says yes to an introduction."""
    return _hive_call(connections.confirm, connection_id)


@app.post("/api/hub/connections/{connection_id}/decline")
def hub_decline(connection_id: str) -> dict[str, Any]:
    """The owner says no. It never becomes a rating."""
    return _hive_call(connections.decline, connection_id)


@app.get("/api/hub/connections")
def hub_connections(requester: str = "", target: str = "") -> dict[str, Any]:
    """Introductions still waiting on somebody: on the owner's yes, or on a human's score."""
    return {
        "awaiting_rating": connections.awaiting_rating(requester),
        "awaiting_confirmation": connections.pending_confirmation(target),
    }


@app.get("/api/hub/standing")
def hub_standing() -> dict[str, Any]:
    """What this hub makes of its neighbours, best calibrated first. Lower error is better."""
    return hub.standing()


# ---------------------------------------------------------------- administration (GUI-ready)

# Declared as a real Header parameter, not read off the raw Request, so /docs renders an input box for it and an
# admin write can be tried from there. It carries either the static ADMIN_TOKEN or a session token from
# /api/admin/login.
AdminToken = Annotated[
    str | None,
    Header(
        alias="X-Admin-Token",
        description="The hub's ADMIN_TOKEN, or a session token from POST /api/admin/login.",
    ),
]


def admin_only(x_admin_token: AdminToken = None) -> str:
    """Dependency for every admin write: fails closed, accepts either credential, and names which.

    Returns the *kind* of credential, never the credential: `"static token"` for the ADMIN_TOKEN
    that curl and CI use, `"session"` for one minted from the password in a browser. That is the
    most the ledger can honestly record about who acted — the hub has one shared password, so there
    is no person to name (see `audit.py`).
    """
    guard.require_admin(x_admin_token, config.ADMIN_TOKEN, config.ADMIN_PASSWORD)
    return guard.credential_kind(x_admin_token, config.ADMIN_TOKEN)


class LoginBody(BaseModel):
    """An operator signing in to the hub's administration."""

    password: str = Field(..., min_length=1, max_length=200, description="The hub's ADMIN_PASSWORD. Never logged")


@app.post("/api/admin/login")
def admin_login(body: LoginBody, request: Request) -> dict[str, Any]:
    """Exchange the hub's password for a short-lived session token, so a browser can administer the hub.

    Hard-limited per client IP and for the whole backend: a password endpoint without a limit is an oracle
    anyone can question all day. A locked-out answer says how many seconds to wait, in the body and in
    `Retry-After`. The password is compared in constant time and never written anywhere.
    """
    if not guard.admin_configured(config.ADMIN_TOKEN, config.ADMIN_PASSWORD):
        raise HTTPException(503, "This hub has no ADMIN_PASSWORD set, so there is nothing to sign in to.")
    guard.admin_logins.check(request)
    if not guard.check_admin_password(body.password, config.ADMIN_PASSWORD):
        raise HTTPException(403, "Wrong password.")
    guard.admin_logins.forget(request)  # getting it right clears the typos that came before it
    ttl = config.ADMIN_SESSION_MINUTES * 60
    return {
        "token": guard.mint_admin_session(config.ADMIN_PASSWORD, ttl),
        "expires_in": ttl,
        "header": "X-Admin-Token",
    }


@app.post("/api/admin/logout")
def admin_logout(x_admin_token: AdminToken = None) -> dict[str, bool]:
    """End this session token. A token already expired or never ours is accepted quietly: nothing to say."""
    guard.end_admin_session(x_admin_token or "")
    return {"signed_out": True}


@app.get("/api/hub/directory")
def hub_directory() -> dict[str, Any]:
    """Every Hive we know of, for a person choosing which one to join.

    Like instances.social for Mastodon: whether it is taking members, what it asks, what it carries, and
    — which a Mastodon directory cannot offer — how honest its ratings have turned out to be."""
    return admin.directory()


@app.get("/api/admin/overview")
def admin_overview() -> dict[str, Any]:
    """The three stores, counted, plus peer standing. What an admin front page renders."""
    return admin.overview()


@app.get("/api/admin/settings")
def admin_settings() -> dict[str, Any]:
    """Hub settings as fields a form can render: value, help text, and options where closed."""
    return admin.settings()


@app.get("/api/admin/neighbours")
def admin_neighbours() -> dict[str, Any]:
    """The peer list with each one's calibration, for the neighbours table."""
    return admin.neighbours()


@app.get("/api/admin/blocklist")
def admin_blocklist(kind: str | None = None) -> dict[str, Any]:
    """Everything this hub has shut out, newest first. Readable without a token, on purpose."""
    return {"entries": _hive_call(blocklist.entries, kind), "kinds": list(blocklist.KINDS)}


@app.post("/api/admin/blocklist")
def admin_block(body: BlockBody, _: str = Depends(admin_only)) -> dict[str, Any]:
    """Block a peer hub or an entity, in both directions."""
    return _hive_call(blocklist.block, body.kind, body.subject, body.reason)


@app.delete("/api/admin/blocklist/{kind}/{subject}")
def admin_unblock(kind: str, subject: str, _: str = Depends(admin_only)) -> dict[str, Any]:
    """Lift a block."""
    return {"lifted": _hive_call(blocklist.unblock, kind, subject)}


# ---------------------------------------------------------------- optional services and their keys


class ServiceKeyBody(BaseModel):
    """A key an operator is storing. Write-only: no endpoint ever gives it back."""

    secret: str = Field(..., min_length=1, max_length=500, description="The key. Never returned, never logged")


@app.get("/api/admin/services")
def admin_services(_: str = Depends(admin_only)) -> dict[str, Any]:
    """Every optional integration: what it is for, whether a key is set and where from, how it tested.

    Never a key. The only things about a stored key that leave this hub are its fingerprint and its
    last four characters, which is enough to tell two keys apart and no use to anyone else.
    """
    return services.listing()


@app.post("/api/admin/services/{name}")
def admin_set_service_key(name: str, body: ServiceKeyBody, credential: str = Depends(admin_only)) -> dict[str, Any]:
    """Store a key for one optional service. The next call that needs it uses it: no restart.

    The answer is the service's status, so the key cannot come back even by accident.
    """
    return _hive_call(services.set_key, name, body.secret, stored_by=credential)


@app.delete("/api/admin/services/{name}")
def admin_clear_service_key(name: str, credential: str = Depends(admin_only)) -> dict[str, Any]:
    """Forget the stored key. The hub falls back to the environment, or to working without one."""
    return _hive_call(services.clear_key, name, cleared_by=credential)


@app.post("/api/admin/services/{name}/check")
def admin_check_service(name: str, _: str = Depends(admin_only)) -> dict[str, Any]:
    """Make one cheap authenticated call with the key in use and say whether it worked.

    So an operator finds out before a demo rather than during it. A key that does not work is a
    200 with `working: false` — an answer, not a server error — and the message is scrubbed of the
    key first, because vendors do echo a bad key back.
    """
    return _hive_call(services.check, name)


# ---------------------------------------------------------------- the connected hubs


class PeerBody(BaseModel):
    """A peer hub an operator is adding or editing. The reason goes in the ledger, not in the row."""

    url: str = Field(..., min_length=1, max_length=300, description="The peer's base URL, http(s)")
    reason: str = Field(..., min_length=1, max_length=500, description="Why, readable six months from now")
    hub_id: str = Field("", max_length=200, description="Its id, if you know it before asking")
    name: str = Field("", max_length=200, description="What to call it here; a probe fills this in if empty")
    note: str = Field("", max_length=500)


class PeerRemovalBody(BaseModel):
    """A peer an operator is dropping. Not a block: see `peers.py` and the blocklist."""

    url: str = Field(..., min_length=1, max_length=300)
    reason: str = Field(..., min_length=1, max_length=500, description="Readable six months from now")


@app.get("/api/admin/peers")
def admin_peers(_: str = Depends(admin_only)) -> dict[str, Any]:
    """The peers this hub asks: URL, hub id, name, whether it answers, its calibration, its state.

    A database read. Reachability is the stored result of the last `POST /api/admin/peers/check`,
    never a fetch made while rendering, so an unreachable peer cannot make this page slow or blank.
    """
    return admin.peer_table()


@app.post("/api/admin/peers")
def admin_add_peer(body: PeerBody, credential: str = Depends(admin_only)) -> dict[str, Any]:
    """Add a peer hub. The next federated search asks it: no restart, no redeploy."""
    return _hive_call(
        peers.add, body.url, body.reason, hub_id=body.hub_id, name=body.name, note=body.note, added_by=credential
    )


@app.put("/api/admin/peers")
def admin_edit_peer(body: PeerBody, credential: str = Depends(admin_only)) -> dict[str, Any]:
    """Change what this hub records about a peer: its id, the name shown here, a note."""
    return _hive_call(
        peers.edit,
        body.url,
        body.reason,
        hub_id=body.hub_id or None,
        name=body.name or None,
        note=body.note or None,
        changed_by=credential,
    )


@app.post("/api/admin/peers/remove")
def admin_remove_peer(body: PeerRemovalBody, credential: str = Depends(admin_only)) -> dict[str, Any]:
    """Stop asking a peer. Not a block: use the blocklist to refuse it in both directions."""
    return _hive_call(peers.remove, body.url, body.reason, removed_by=credential)


@app.post("/api/admin/peers/check")
async def admin_check_peers(_: str = Depends(admin_only)) -> dict[str, Any]:
    """Ask every peer who it is, now rather than at the next background round, and return the table.

    The same `federation.ask_peers` the hub runs on a timer: all peers at once, each capped at
    `PEER_ASK_TIMEOUT_S`, nothing raised. This is the button for an operator who has just added a
    neighbour and does not want to wait `PEER_ASK_SECONDS` to see whether it answers.
    """
    await federation.ask_peers()
    return admin.peer_table()


# ---------------------------------------------------------------- what this hub carries


@app.get("/api/admin/entities")
def admin_entities(_: str = Depends(admin_only)) -> dict[str, Any]:
    """Every entity this hub carries: id, name, kind, claimed, rating and count, when it was published.

    Behind the admin token although every field is also on the public card, because the list itself
    — the whole membership of a hub in one call — is an operator's view rather than a visitor's.
    """
    return admin.entities()


@app.get("/api/admin/entities/{entity_id}")
def admin_entity(entity_id: str, _: str = Depends(admin_only)) -> dict[str, Any]:
    """One entity in full: the signed card, its offers and needs, contact with the sharing flags,
    its trust block and its signature state, and whether this hub has blocked it."""
    return _hive_call(admin.entity, entity_id)


class RemovalBody(BaseModel):
    """An operator taking an entity off this hub, or putting it back. The reason is not optional."""

    reason: str = Field(..., min_length=1, max_length=500, description="Readable six months from now")


@app.post("/api/admin/entities/{entity_id}/remove")
def admin_remove_entity(entity_id: str, body: RemovalBody, credential: str = Depends(admin_only)) -> dict[str, Any]:
    """Stop carrying an entity: out of discovery, not bookable, signed history kept.

    A withdrawal rather than a delete, because `hive_card_history` is what lets a receipt prove
    what a card said on the day it was booked (see `removals.py` and `SECURITY.md`). Removing is
    not blocking: use the blocklist to refuse an entity wherever it comes from.
    """
    return _hive_call(removals.withdraw, entity_id, body.reason, removed_by=credential)


@app.post("/api/admin/entities/{entity_id}/restore")
def admin_restore_entity(entity_id: str, body: RemovalBody, credential: str = Depends(admin_only)) -> dict[str, Any]:
    """Carry an entity again. The withdrawal goes; the ledger keeps both decisions."""
    return _hive_call(removals.restore, entity_id, body.reason, restored_by=credential)


@app.get("/api/admin/audit")
def admin_audit(subject: str = "", action: str = "", limit: int = 200, _: str = Depends(admin_only)) -> dict[str, Any]:
    """The admin ledger: what was changed, when, why, and with which credential.

    `who_limit` comes back with it, because this hub has one shared password and a ledger that
    implied otherwise would be worse than none.
    """
    return {
        "entries": audit.entries(subject=subject, action_prefix=action, limit=limit),
        "who_limit": audit.WHO_LIMIT,
    }


# ---------------------------------------------------------------- joining this hub


class RegisterBody(BaseModel):
    """One signed application to join. See GET /api/hub/registration for the shape and the rules."""

    entity: dict[str, Any] = Field(..., description="The card being registered: id, kind, name, description")
    public_key: str = Field("", max_length=200, description="Base64 Ed25519. Bring one and you keep the private half")
    proofs: list[dict[str, Any]] = Field(
        default_factory=list, description="Claims about the world, recorded unverified"
    )
    invite: str = Field("", max_length=200)
    signature: str = Field(
        "", max_length=400, description="Base64, over the canonical JSON of this without `signature`"
    )


class DecisionBody(BaseModel):
    """An operator admitting or refusing a pending application."""

    admit: bool
    reason: str = Field("", max_length=500, description="Required to refuse; the applicant is told it")


@app.get("/api/hub/registration")
def hub_registration_policy() -> dict[str, Any]:
    """What this hub asks of someone who wants to join, and the exact document to send.

    Published so an applicant can read the rules before spending effort on an application."""
    return registration.policy()


@app.post("/api/hub/register")
def hub_register(body: RegisterBody, request: Request) -> dict[str, Any]:
    """Apply to join this hub. Returns the decision, the checks that led to it, and what to do next.

    A refusal is an answer, not an error, so this returns 200 with `state: rejected` rather than a 4xx."""
    guard.federated.check(request)
    return _hive_call(registration.apply, body.model_dump())


@app.get("/api/hub/register/{application_id}")
def hub_application(application_id: str) -> dict[str, Any]:
    """Check on an application."""
    return _hive_call(registration.get, application_id)


@app.post("/api/hub/register/{application_id}/withdraw")
def hub_withdraw(application_id: str) -> dict[str, Any]:
    """Withdraw an application before it has been decided."""
    return _hive_call(registration.withdraw, application_id)


@app.get("/api/admin/applications")
def admin_applications(state: str = "") -> dict[str, Any]:
    """The admission queue. Pass state=pending for what is waiting on a person."""
    return {"applications": _hive_call(registration.listing, state), "policy": registration.policy()}


@app.post("/api/admin/applications/{application_id}")
def admin_decide(application_id: str, body: DecisionBody, _: str = Depends(admin_only)) -> dict[str, Any]:
    """Admit or refuse a pending application. A refusal needs a reason, and the applicant is told it."""
    return _hive_call(registration.decide, application_id, body.admit, reason=body.reason)
