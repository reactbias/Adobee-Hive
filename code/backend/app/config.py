"""Runtime settings, all read from environment variables (see .env.example)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Main model: the booking agent.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
# Cheap model for owner edits. The demo key has a fixed budget.
CLAUDE_FAST_MODEL = os.getenv("CLAUDE_FAST_MODEL", "claude-haiku-5-5")
# Server-side refusal fallbacks (beta). Set to "off" to disable.
CLAUDE_FALLBACKS = os.getenv("CLAUDE_FALLBACKS", "default")

DUCKDB_PATH = Path(os.getenv("DUCKDB_PATH", str(BASE_DIR / "data" / "abh.duckdb")))
# Optional Postgres (postgresql://...): the DuckDB file is restored from it on boot and saved after each write,
# so data survives redeploys on hosts without a persistent disk. Empty = local file only.
DATABASE_URL = os.getenv("DATABASE_URL", "")

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
SEED_ON_EMPTY = os.getenv("SEED_ON_EMPTY", "true").lower() == "true"
DEMO_RESET_TOKEN = os.getenv("DEMO_RESET_TOKEN", "")  # when set, /api/demo/reset needs it as X-Demo-Token
OWNER_EDIT_TOKEN = os.getenv("OWNER_EDIT_TOKEN", "")  # when set, owner edits need it as X-Owner-Token

# Cost guard for the demo key: calls that may reach Claude, per client IP and in total, per hour.
LLM_CALLS_PER_CLIENT_HOUR = int(os.getenv("LLM_CALLS_PER_CLIENT_HOUR", "30"))
LLM_CALLS_TOTAL_HOUR = int(os.getenv("LLM_CALLS_TOTAL_HOUR", "300"))

# OpenAI runs the booking agent, owner edits and the second opinion when its key is set. One small, tool-capable
# model keeps the demo budget predictable.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

# Which model vendor the agents use: "openai", "claude" or "offline". By default OpenAI when its key is set, then
# Claude, then the offline planner and rule-based edits.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "") or (
    "openai" if OPENAI_API_KEY else "claude" if ANTHROPIC_API_KEY else "offline"
)
if {"openai": OPENAI_API_KEY, "claude": ANTHROPIC_API_KEY}.get(LLM_PROVIDER, "") == "":
    LLM_PROVIDER = "offline"  # unknown name, or the chosen vendor has no key
LLM_ENABLED = LLM_PROVIDER != "offline"

# MCP endpoints the booking agent searches. Empty = this server's own Hive, in-process.
# Comma-separated URLs federate several Hives, e.g. another team's https://.../mcp/
HIVE_MCP_URLS = [u.strip() for u in os.getenv("HIVE_MCP_URLS", "").split(",") if u.strip()]
AGENT_MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "10"))

# Peer Hives for hop-limited ("node radius") federated search, same shape as HIVE_MCP_URLS: comma-separated base
# URLs, e.g. https://hive-zurich.example. Empty = no peers, so every search stays local whatever the radius.
HIVE_PEER_URLS = [u.strip() for u in os.getenv("HIVE_PEER_URLS", "").split(",") if u.strip()]
# This hub's id: it names this Hive in a result's provenance chain and in a query's loop-prevention list.
HIVE_HUB_ID = os.getenv("HIVE_HUB_ID", "local")
# What this hub declares about how it vets its members: "signed" (every card signed by its owner's pinned key),
# "attested" (plus third-party attestations) or "none". Peers judge the declaration against what they observe.
HIVE_VERIFICATION = os.getenv("HIVE_VERIFICATION", "signed")
# A model call that hangs must not leave the chat "thinking": one call gives up after LLM_TIMEOUT_S, a whole agent
# run after AGENT_TIMEOUT_S, and the offline planner answers instead.
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "25"))
AGENT_TIMEOUT_S = float(os.getenv("AGENT_TIMEOUT_S", "60"))
