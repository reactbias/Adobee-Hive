"""FastAPI entry point: REST for the web app, MCP for agents.

  /api/...           JSON API used by the React frontend
  /mcp/              the Hive MCP server (Streamable HTTP) for any AI agent
  /.well-known/hive.json   discovery document pointing agents to the MCP endpoint
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import agent, config, db, hive, hive_seed, mcp_server, owner, simulate

logging.basicConfig(level=logging.INFO)

mcp_app = mcp_server.http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    hive.init()
    if config.SEED_ON_EMPTY:
        hive_seed.seed_if_empty()
    async with mcp_app.router.lifespan_context(mcp_app):
        yield
    db.close()


app = FastAPI(title="AdoBee Hive", version="0.1.0", lifespan=lifespan)
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
    return {
        "status": "ok",
        "llm": "claude" if config.LLM_ENABLED else "mock",
        "model": config.CLAUDE_MODEL,
        "fast_model": config.CLAUDE_FAST_MODEL,
        "hives": config.HIVE_MCP_URLS or ["local"],
    }


@app.get("/.well-known/hive.json")
def well_known(request: Request) -> dict[str, Any]:
    base = str(request.base_url).rstrip("/")
    return {
        "name": "AdoBee Hive (Basel)",
        "mcp": {"url": f"{base}/mcp/", "transport": "streamable-http"},
        "signature": "Ed25519 over canonical JSON; public key in each card's trust block",
        "ranking_policy": "Constraints first, then relevance, proximity, verified reviews, attestations. No paid placement.",
    }


# ---------------------------------------------------------------- Hive (businesses)

class AgentRequest(BaseModel):
    messages: list[dict[str, str]] = Field(min_length=1)


class BookRequest(BaseModel):
    unit_id: str
    check_in: str
    check_out: str
    guest_name: str
    guests: int = 1
    notes: str = ""


class ReviewRequest(BaseModel):
    receipt: str
    rating: int
    text: str = ""


class OwnerEdit(BaseModel):
    instruction: str


class OwnerApply(BaseModel):
    proposed: dict[str, Any]


@app.get("/api/hive/cards")
def hive_cards(kind: str | None = None) -> list[dict[str, Any]]:
    return hive.list_cards(kind)


@app.get("/api/hive/cards/{card_id}")
def hive_card(card_id: str) -> dict[str, Any]:
    return _hive_call(hive.get_card, card_id)


@app.get("/api/hive/cards/{card_id}/availability")
def hive_availability(card_id: str, check_in: str, check_out: str, guests: int = 1) -> dict[str, Any]:
    return _hive_call(hive.check_availability, card_id, check_in, check_out, guests)


@app.post("/api/hive/cards/{card_id}/book")
def hive_book(card_id: str, body: BookRequest) -> dict[str, Any]:
    """Human fallback: the same booking a person can make from the card page."""
    return _hive_call(hive.book, card_id, body.unit_id, body.check_in, body.check_out, body.guest_name,
                      body.guests, body.notes, "human via card page")


@app.post("/api/hive/reviews")
def hive_review(body: ReviewRequest) -> dict[str, Any]:
    return _hive_call(hive.review, body.receipt, body.rating, body.text)


class VerifyRequest(BaseModel):
    card: dict[str, Any]


@app.post("/api/hive/verify")
def hive_verify(body: VerifyRequest) -> dict[str, Any]:
    """Check a card against its own signature, as any agent would. Used by the tamper demo."""
    card = dict(body.card)
    trust = card.pop("trust", {}) or {}
    return {"signature_valid": hive.verify(card, trust.get("signature", ""), trust.get("public_key", ""))}


@app.get("/api/hive/demand")
def hive_demand(days: int = 7) -> dict[str, Any]:
    return hive.demand_map(days)


@app.post("/api/demo/simulate")
def demo_simulate(n: int = 40) -> dict[str, Any]:
    return simulate.run(min(n, 200))


@app.post("/api/agent")
async def run_agent(body: AgentRequest) -> dict[str, Any]:
    try:
        return await agent.run(body.messages)
    except Exception as err:  # surface agent failures to the demo UI instead of a bare 500
        logging.exception("agent run failed")
        raise HTTPException(502, f"Agent failed: {err}") from err


@app.get("/api/owner/{card_id}")
def owner_overview(card_id: str) -> dict[str, Any]:
    return _hive_call(hive.owner_overview, card_id)


@app.post("/api/owner/{card_id}/propose")
async def owner_propose(card_id: str, body: OwnerEdit) -> dict[str, Any]:
    return await asyncio.to_thread(_hive_call, owner.propose, card_id, body.instruction)


@app.post("/api/owner/{card_id}/publish")
def owner_publish(card_id: str, body: OwnerApply) -> dict[str, Any]:
    return _hive_call(owner.apply, card_id, body.proposed)
