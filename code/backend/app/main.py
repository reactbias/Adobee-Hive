"""FastAPI entry point: REST for the web app, MCP for agents.

/api/...           JSON API used by the React frontend
/mcp/              the Hive MCP server (Streamable HTTP) for any AI agent
/.well-known/hive.json   discovery document pointing agents to the MCP endpoint
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import agent, config, db, guard, hive, hive_seed, mcp_server, owner, simulate

logging.basicConfig(level=logging.INFO)

mcp_app = mcp_server.http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Open the database, seed it if empty, and run the MCP session manager for the app's lifetime."""
    db.init()
    hive.init()
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
        "signature": "Ed25519 over canonical JSON; public key in each card's trust block",
        "ranking_policy": hive.RANKING_POLICY,
    }


# ---------------------------------------------------------------- Hive (businesses)


class Message(BaseModel):
    """One chat turn."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class AgentRequest(BaseModel):
    """A conversation with the traveller agent; the last message is the traveller's."""

    messages: list[Message] = Field(min_length=1, max_length=20)


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
    """Check a card against its own signature, as any agent would. Used by the tamper demo."""
    card = dict(body.card)
    trust = card.pop("trust", {}) or {}
    return {"signature_valid": hive.verify(card, trust.get("signature", ""), trust.get("public_key", ""))}


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
    if config.LLM_ENABLED:
        guard.llm_calls.check(request)
    try:
        return await agent.run([m.model_dump() for m in body.messages])
    except Exception as err:  # log the details, show the UI a plain message
        logging.exception("agent run failed")
        raise HTTPException(502, "The agent could not finish this request. Try again.") from err


@app.post("/api/agent/approve")
async def approve_booking(body: ApproveRequest) -> dict[str, Any]:
    """The human's yes: the agent sends the booking it held back."""
    try:
        return await agent.approve(body.pending)
    except (ValueError, KeyError) as err:
        raise HTTPException(400, str(err)) from err


@app.get("/api/owner/{card_id}")
def owner_overview(card_id: str, request: Request) -> dict[str, Any]:
    """Return the owner studio data for one card. Without the owner token, guest names show as initials."""
    overview = _hive_call(hive.owner_overview, card_id)
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
