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

# The folder link (folders.py): how two agents connect their private folders before a booking is made.
# "local" links the folders in testdata/vaults/ in this process — no network, no key, no new dependency — and is
# what the demo runs on. "claudeconnect" uses the real ClaudeConnect library when it is installed and reachable,
# and falls back to local with a reason, reported in /api/health, when it is not.
FOLDER_LINK = os.getenv("FOLDER_LINK", "local")
FOLDER_ROOT = Path(os.getenv("FOLDER_ROOT", str(BASE_DIR.parent.parent / "testdata" / "vaults")))
# Where the real ClaudeConnect lives, when FOLDER_LINK=claudeconnect. Empty uses the library's own default
# (https://claudeconnect.io); a local instance of its sync server is a URL here. CC_HANDLE is the handle this hub
# claims for itself, and CC_TOKEN the bot token it was issued (see documentation/ARCHITECTURE.md).
CC_SERVER = os.getenv("CLAUDECONNECT_SERVER", "")
CC_HANDLE = os.getenv("CC_HANDLE", "")
CC_TOKEN = os.getenv("CC_TOKEN", "")
CC_TIMEOUT_S = float(os.getenv("CC_TIMEOUT_S", "2"))  # what one unreachable claudeconnect.io costs us

# What one read off the folder surface may cost. A file larger than this is refused with 413 rather
# than streamed: the corpus's largest file is a few hundred kilobytes, so a request for more than
# this is a mistake or an attempt to hold a worker. Reads are also counted per link, per hour.
FOLDER_READ_MAX_BYTES = int(os.getenv("FOLDER_READ_MAX_BYTES", str(25 * 1024 * 1024)))
FOLDER_READS_PER_LINK_HOUR = int(os.getenv("FOLDER_READS_PER_LINK_HOUR", "600"))
FOLDER_READS_TOTAL_HOUR = int(os.getenv("FOLDER_READS_TOTAL_HOUR", "6000"))

CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
SEED_ON_EMPTY = os.getenv("SEED_ON_EMPTY", "true").lower() == "true"
DEMO_RESET_TOKEN = os.getenv("DEMO_RESET_TOKEN", "")  # when set, /api/demo/reset needs it as X-Demo-Token
OWNER_EDIT_TOKEN = os.getenv("OWNER_EDIT_TOKEN", "")  # when set, owner edits need it as X-Owner-Token

# Running the hub itself: the blocklist and the neighbour list. Unlike the owner token this one
# fails closed — an unset ADMIN_TOKEN refuses every write rather than leaving the blocklist open.
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
# The same door for a person in a browser: POST the password to /api/admin/login for a short-lived session token,
# which then travels in X-Admin-Token like the static one. No default, on purpose — unset means administration is
# disabled, and a default password in the source would be a published one.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
# How long a session lasts. Short, because it is a bearer token and the only way to end one early is to sign out.
ADMIN_SESSION_MINUTES = int(os.getenv("ADMIN_SESSION_MINUTES", "30"))
# Guessing budget for the password endpoint, per client IP and for the whole backend, in one sliding window.
ADMIN_LOGIN_PER_CLIENT = int(os.getenv("ADMIN_LOGIN_PER_CLIENT", "5"))
ADMIN_LOGIN_TOTAL = int(os.getenv("ADMIN_LOGIN_TOTAL", "30"))
ADMIN_LOGIN_WINDOW_S = int(os.getenv("ADMIN_LOGIN_WINDOW_S", "900"))

# Who may join this hub. "open" admits anything that passes the checks, "vetted" puts every
# application in front of a person, "invite" needs a token, "closed" accepts nobody. The default is
# vetted, because a hub's standing with its peers is measured by whether its published ratings
# survive contact with real people: letting anyone in is a cost the hub pays later, in calibration.
ADMISSION_POLICY = os.getenv("ADMISSION_POLICY", "vetted")
INVITE_TOKENS = [t.strip() for t in os.getenv("INVITE_TOKENS", "").split(",") if t.strip()]

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

# How this hub keeps up with who its peers are. It asks each peer's /.well-known/hive.json on a timer, so a hub
# with peers configured knows their names without waiting for someone to run a federated search. A read of the
# directory is served from that cache and never fans out, because one slow peer must not make the picker slow.
PEER_ASK_SECONDS = float(os.getenv("PEER_ASK_SECONDS", "30"))  # 0 turns the background asking off
PEER_ASK_TIMEOUT_S = float(os.getenv("PEER_ASK_TIMEOUT_S", "2"))  # what one unreachable peer costs, in the background
PEER_STALE_AFTER_S = float(os.getenv("PEER_STALE_AFTER_S", "120"))  # past this, a cached answer is shown as stale

# What this Hive calls itself to its peers. A hub is an entity in the protocol like a business is, so it
# carries the same three fields: a name, a description, and a rating. The rating of a hub is never
# self-declared — each hub computes its own opinion of a peer in reputation.py.
HIVE_NAME = os.getenv("HIVE_NAME", "Adobee Hive (Basel)")
HIVE_DESCRIPTION = os.getenv("HIVE_DESCRIPTION", "Signed cards for Basel businesses: stays, tables and services.")
# A model call that hangs must not leave the chat "thinking": one call gives up after LLM_TIMEOUT_S, a whole agent
# run after AGENT_TIMEOUT_S, and the offline planner answers instead.
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "25"))
AGENT_TIMEOUT_S = float(os.getenv("AGENT_TIMEOUT_S", "60"))

# Which similarity provider discovery ranks with: "offline" (always available: stems, a concept table and
# character trigrams, no key and no network) or "embeddings" (only when a key is set). Empty picks the best
# available, the way LLM_PROVIDER does. Read at call time, so a key set at runtime needs no restart.
SEMANTIC_PROVIDER = os.getenv("SEMANTIC_PROVIDER", "")
# The embedding model used when a key is configured. Vectors are cached per card version, so the corpus is
# embedded when a card is published, never per query.
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
