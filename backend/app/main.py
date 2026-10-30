"""FastAPI entry point: REST for the web app, MCP for agents.

  /api/...           JSON API used by the React frontend
  /mcp/              the Hive MCP server (Streamable HTTP) for any AI agent
  /.well-known/hive.json   discovery document pointing agents to the MCP endpoint
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import agent, config, db, extraction, hive, hive_seed, mcp_server, nl_query, owner, profiles, seed

logging.basicConfig(level=logging.INFO)

mcp_app = mcp_server.http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init()
    hive.init()
    if config.SEED_ON_EMPTY:
        seed.seed_if_empty()
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


# ---------------------------------------------------------------- HR (companies hiring people)

class QueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class StageUpdate(BaseModel):
    stage: str


class TextCV(BaseModel):
    text: str = Field(min_length=20)
    job_id: str | None = None
    filename: str = "pasted.txt"


@app.get("/api/jobs")
def jobs() -> list[dict[str, Any]]:
    return db.list_jobs()


@app.get("/api/candidates")
def candidates(job_id: str | None = None, stage: str | None = None) -> list[dict[str, Any]]:
    return db.list_candidates(job_id, stage)


@app.get("/api/candidates/{cid}")
def candidate(cid: str) -> dict[str, Any]:
    found = db.get_candidate(cid)
    if not found:
        raise HTTPException(404, "Candidate not found")
    return found


@app.patch("/api/candidates/{cid}")
def update_candidate(cid: str, body: StageUpdate) -> dict[str, Any]:
    if body.stage not in db.STAGES:
        raise HTTPException(400, f"stage must be one of {db.STAGES}")
    db.set_stage(cid, body.stage)
    return candidate(cid)


@app.get("/api/funnel")
def funnel(job_id: str | None = None) -> list[dict[str, Any]]:
    return db.funnel(job_id)


def _ingest(text: str, filename: str, job_id: str | None) -> dict[str, Any]:
    parsed = extraction.parse_cv(text)
    cid = db.insert_candidate(parsed, job_id=job_id, raw_text=text, filename=filename,
                              source="claude" if config.LLM_ENABLED else "mock")
    return db.get_candidate(cid)


@app.post("/api/cvs")
async def upload_cvs(files: list[UploadFile] = File(...), job_id: str | None = Form(None)) -> list[dict[str, Any]]:
    docs = [(f.filename or "cv", extraction.read_upload(f.filename or "", await f.read())) for f in files]
    sem = asyncio.Semaphore(4)

    async def one(name: str, text: str) -> dict[str, Any]:
        async with sem:
            try:
                return await asyncio.to_thread(_ingest, text, name, job_id)
            except Exception as err:
                return {"filename": name, "error": str(err)}

    return await asyncio.gather(*(one(n, t) for n, t in docs))


@app.post("/api/cvs/text")
async def upload_text(body: TextCV) -> dict[str, Any]:
    return await asyncio.to_thread(_ingest, body.text, body.filename, body.job_id)


@app.get("/api/schema")
def schema() -> dict[str, str]:
    return {"schema": db.schema_description()}


@app.post("/api/query")
async def query(body: QueryRequest) -> dict[str, Any]:
    try:
        return await asyncio.to_thread(nl_query.ask, body.question)
    except nl_query.UnsafeQuery as err:
        raise HTTPException(400, str(err)) from err
    except Exception as err:
        raise HTTPException(400, f"Query failed: {err}") from err


# ---------------------------------------------------------------- applicants (people as Hive cards)

class PitchRequest(BaseModel):
    job_id: str


@app.get("/api/profiles/{pid}")
def get_profile(pid: str) -> dict[str, Any]:
    return profiles.get(pid)


@app.put("/api/profiles/{pid}")
def put_profile(pid: str, body: dict[str, Any]) -> dict[str, Any]:
    return profiles.save(pid, body)


@app.get("/api/connectors")
def connectors() -> dict[str, Any]:
    return {k: {"label": v["label"], "description": v["description"]} for k, v in profiles.CONNECTORS.items()}


@app.post("/api/profiles/{pid}/connectors/{connector}")
def connect(pid: str, connector: str) -> dict[str, Any]:
    try:
        return profiles.connect(pid, connector)
    except KeyError as err:
        raise HTTPException(404, f"Unknown connector {connector}") from err


@app.post("/api/profiles/{pid}/pitch")
async def pitch(pid: str, body: PitchRequest) -> dict[str, Any]:
    job = db.get_job(body.job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return await asyncio.to_thread(profiles.pitch, pid, job)


@app.post("/api/profiles/{pid}/publish")
def publish_profile(pid: str) -> dict[str, Any]:
    """Publish the applicant's shared fields as a signed person card in the Hive."""
    return profiles.publish_card(pid)
