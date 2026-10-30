<p align="center"><img src="assets/brand/adobee-hive-wordmark.png" alt="Adobee Hive" width="420"></p>

<p align="center"><b>On GitHub you find projects to work on. On Adobee Hive, agents find businesses and people to work with.</b></p>

BaselHack 2026, Team B6, for Adobe's challenge **The Post-Website Business**: how does a local hotel, café or shop
stay found, trusted and bookable when its first visitor is an AI agent, not a person on a website?

## The idea in one minute

The website was the front door. Then platforms took it. Next, agents walk in, and today they read whatever they
scrape and guess. We give the front door back to the business: every business publishes a **Hive card**, a
structured document **signed by the owner**, that agents query and book through over **MCP**. The same card renders
as a page for humans, and the owner edits it by typing what changed.

- **Signed facts, not scraped guesses.** Agents verify the owner's Ed25519 signature themselves; third parties
  attest single claims like "dog-friendly".
- **Proof-of-stay reviews.** Only a signed booking receipt can leave a review.
- **Ranking in the open.** Every result says why it won and why the others were left out. No paid placement.
- **The twist: agents write the business plan.** Every request no one could serve is logged as missed demand. A café
  learns that agents asked for vegan breakfast; Basel learns what nobody offers yet.

Read the full story in [documentation/VISION.md](documentation/VISION.md).

## What works today

An agent that never opens a website discovers, verifies, compares and books a fictional Basel hotel, end to end
over MCP. Try it with any MCP client, Claude included.

| Piece | Where |
| --- | --- |
| Hive cards for six fictional Basel businesses, signed with Ed25519 | `code/backend/app/hive.py`, `hive_seed.py` |
| MCP server: discover, get card, check availability, book, cancel, review | `code/backend/app/mcp_server.py` |
| Traveller agent: Claude over MCP, verifies every signature, explains its choice | `code/backend/app/agent.py`, `TravellerAgent.tsx` |
| Owner studio: plain-language edit, diff, sign and publish, missed demand | `code/backend/app/owner.py`, `OwnerStudio.tsx` |
| Human card page with direct booking and a live tamper test | `CardPage.tsx` |
| Basel demand map: what agents asked for that nobody offers | `DemandMap.tsx` |

Without an API key everything still runs on a scripted planner over the same tools, so the demo never dies.

## Quick start

```bash
cd code/backend && pip install -r requirements.txt -r requirements-dev.txt && pytest -q
uvicorn app.main:app --port 8000          # add ANTHROPIC_API_KEY for the live Claude agent
cd ../frontend && npm install && npm run dev   # http://localhost:5173
```

Docker, AWS auto-deploy and connecting Claude: [documentation/DEPLOY.md](documentation/DEPLOY.md).

## Repository

| Folder | Contents |
| --- | --- |
| [`code/`](code) | `backend/` FastAPI + DuckDB + MCP + agents, `frontend/` React + Vite, `scripts/aws/`, `docker-compose.yml` |
| [`documentation/`](documentation) | [Vision](documentation/VISION.md) · [Demo script](documentation/DEMO.md) · [Architecture](documentation/ARCHITECTURE.md) · [Run and deploy](documentation/DEPLOY.md) · [Brand](documentation/BRAND.md) · [Team](documentation/TEAM.md) |
| [`assets/`](assets) | Logo, wordmark and mascot exports for slides |

Layout follows the BaselHack template. All businesses in the seed data are fictional.
MIT licensed, see [license.txt](license.txt).
