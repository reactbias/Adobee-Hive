# AdoBee Hive

**On GitHub you find projects to work on. On AdoBee Hive, agents find businesses and people to work with.**

BaselHack 2026, team B6, for Adobe's challenge *The Post-Website Business*: how does a local business stay
found, trusted and bookable when the first visitor is an AI agent, not a person on a website?

Our answer: every business (and every person) publishes a **Hive card**, a signed, structured document that
agents query and act on over MCP. The same card renders as a page for humans, and the owner edits it in plain words.

## What works in the prototype

| Piece | What it does | Where |
| --- | --- | --- |
| Hive cards | Structured presence for six fictional Basel businesses, each version signed with the owner's Ed25519 key | `backend/app/hive.py`, `hive_seed.py` |
| MCP server | `hive_discover`, `hive_get_card`, `hive_check_availability`, `hive_book`, `hive_cancel`, `hive_review` at `/mcp/` | `backend/app/mcp_server.py` |
| Traveller agent | Connects over MCP like any third-party agent, verifies signatures itself, compares and books end to end | `backend/app/agent.py`, `frontend/src/pages/TravellerAgent.tsx` |
| Trust | Third-party attestations, proof-of-stay reviews (needs the signed booking receipt), explainable ranking with no paid placement | `hive.py` |
| Owner studio | Type "add sauna, courtyard double is 165 francs", review the diff, sign and publish. See bookings and the demand you missed | `backend/app/owner.py`, `OwnerStudio.tsx` |
| Human fallback | `/card/<slug>` renders the same card with direct booking | `CardPage.tsx` |

Without `ANTHROPIC_API_KEY` everything still runs: a scripted planner walks the same MCP tools, and owner
edits fall back to simple rules ("add sauna"). The nav bar shows "Claude live" or "offline mode".

## Run it locally

```bash
# backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                                   # includes an end-to-end booking over MCP
ANTHROPIC_API_KEY=sk-ant-... uvicorn app.main:app --reload --port 8000

# frontend (another terminal)
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Or the whole stack: `cp .env.example .env` (add the key), then `docker compose up --build`.

### Point any agent at the Hive

The MCP endpoint is `http://localhost:8000/mcp/` (Streamable HTTP). Agents can also find it from
`/.well-known/hive.json`. Add it as a custom connector in Claude and ask: *"Find me a dog-friendly hotel near
Basel SBB under CHF 200 for next weekend and book it."*

## Deploy to AWS (auto-deploy on push to `main`)

- **Frontend:** AWS Amplify Hosting builds `frontend/` with `amplify.yml`.
- **Backend:** GitHub Actions pushes a Docker image to ECR; App Runner auto-deploys it. The Claude key lives in
  Secrets Manager, and the DuckDB file is snapshotted to S3 so data survives redeploys.

One-time setup, about 15 minutes:

1. `AWS_PROFILE=... ANTHROPIC_API_KEY=... ./scripts/aws/bootstrap.sh` (needs Docker and the AWS CLI).
   It prints the backend URL.
2. GitHub repo secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (IAM user that can push to ECR).
3. Amplify console: *New app* → GitHub → this repo, branch `main`, monorepo root `frontend`.
   Environment variable `VITE_API_URL` = the backend URL. Under *Rewrites and redirects* add
   `</^[^.]+$|\.(?!(css|gif|ico|jpg|js|png|txt|svg|woff|woff2|ttf|map|json|webp)$)([^.]+$)/>` → `/index.html` (200)
   so deep links like `/card/rheinblick` work.
4. Push to `main`.

## Cost guard for the demo key

The booking agent uses `claude-opus-5-5` at low effort with prompt caching on the tool definitions; owner edits
use `claude-haiku-5-5`. Change either with `CLAUDE_MODEL` /
`CLAUDE_FAST_MODEL`. `AGENT_MAX_TURNS` caps each agent run.

## Repo map

```
backend/   FastAPI + DuckDB + MCP server + agents (Python 3.12)
frontend/  React + Vite + TypeScript
scripts/aws/bootstrap.sh   one-time AWS setup
amplify.yml, .github/workflows/   deploy and CI
```

All businesses in the seed data are fictional. MIT licensed, see `LICENSE`.
