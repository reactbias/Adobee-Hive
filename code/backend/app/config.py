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
# Optional: s3://bucket/key.duckdb. Restored on boot, uploaded after each write.
DUCKDB_S3_URI = os.getenv("DUCKDB_S3_URI", "")

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
SEED_ON_EMPTY = os.getenv("SEED_ON_EMPTY", "true").lower() == "true"
DEMO_RESET_TOKEN = os.getenv("DEMO_RESET_TOKEN", "")  # when set, /api/demo/reset needs it as X-Demo-Token
OWNER_EDIT_TOKEN = os.getenv("OWNER_EDIT_TOKEN", "")  # when set, owner edits need it as X-Owner-Token

# Cost guard for the demo key: calls that may reach Claude, per client IP and in total, per hour.
LLM_CALLS_PER_CLIENT_HOUR = int(os.getenv("LLM_CALLS_PER_CLIENT_HOUR", "30"))
LLM_CALLS_TOTAL_HOUR = int(os.getenv("LLM_CALLS_TOTAL_HOUR", "300"))

LLM_ENABLED = bool(ANTHROPIC_API_KEY)

# MCP endpoints the booking agent searches. Empty = this server's own Hive, in-process.
# Comma-separated URLs federate several Hives, e.g. another team's https://.../mcp/
HIVE_MCP_URLS = [u.strip() for u in os.getenv("HIVE_MCP_URLS", "").split(",") if u.strip()]
AGENT_MAX_TURNS = int(os.getenv("AGENT_MAX_TURNS", "10"))
