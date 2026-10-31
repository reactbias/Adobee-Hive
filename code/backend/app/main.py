"""FastAPI entry point: REST for the web app, MCP for agents.

/api/...           JSON API used by the React frontend
/mcp/              the Hive MCP server (Streamable HTTP) for any AI agent
/.well-known/hive.json   discovery document pointing agents to the MCP endpoint
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import (
    activity,
    agent,
    config,
    db,
    federation,
    guard,
    hive,
    hive_seed,
    mcp_server,
    owner,
    replies,
    rulesets,
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
    if config.SEED_ON_EMPTY:
        hive_seed.seed_if_empty()
    async with mcp_app.router.lifespan_context(mcp_app):
        yield
    db.close()


app = FastAPI(title="Adobee Hive", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["mcp-session-id"],
)
app.mount("/mcp", mcp_app)


def _hive_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except hive.HiveError as err:
        raise HTTPException(400, str(err)) from err


# ---------------------------------------------------------------- meta


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Report whether the backend is up and which model vendor the agents use."""
    claude = config.LLM_PROVIDER == "claude"
    return {
        "status": "ok",
        "llm": config.LLM_PROVIDER if config.LLM_ENABLED else "mock",
        "model": config.CLAUDE_MODEL if claude else config.OPENAI_MODEL,
        "fast_model": config.CLAUDE_FAST_MODEL if claude else config.OPENAI_MODEL,
        "hives": config.HIVE_MCP_URLS or ["local"],
    }


@app.get("/.well-known/hive.json")
def well_known(request: Request) -> dict[str, Any]:
    """Discovery document so agents can find this Hive's MCP endpoint and policies."""
    base = str(request.base_url).rstrip("/")
    return {
        "name": "Adobee Hive (Basel)",
        "mcp": {"url": f"{base}/mcp/", "transport": "streamable-http"},
        "signature": "Ed25519 over canonical JSON; a card is valid only if signed by the key pinned for its id below",
        "owner_keys": hive.owner_keys(),
        "ruleset_keys": rulesets.keys(),
        "ranking_policy": hive.RANKING_POLICY,
        # What peer Hives judge this hub by when a query reaches them over it (see reputation.py).
        "federation": {
            "hub_id": config.HIVE_HUB_ID,
            "verification": config.HIVE_VERIFICATION,
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
) -> dict[str, Any]:
    """Search the Hive, and with radius above 0 its peer Hives too; radius 0 is this Hive only, as before.

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
    if config.LLM_ENABLED and body.rules == "on":  # the rules-off run is scripted and never reaches a model
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
