<p align="center"><img src="assets/brand/adobee-hive-wordmark.png" alt="Adobee Hive" width="420"></p>

<p align="center"><b>The front door, signed.</b></p>

BaselHack 2026, Team B6, for Adobe's challenge **The Post-Website Business**: how does a local hotel, café or shop
stay found, trusted and bookable when its first visitor is an AI agent, not a person on a website?

## The next guest is an agent

The website was the front door. Then platforms took it. Now agents walk in, and today they read whatever they
scrape and guess. Adobee Hive gives the front door back to the business.

Every business publishes one **Hive card**: its rooms or tables, prices, availability and policies, **signed by the
owner**. Agents find it, verify it and book through it over **MCP**. People see the same card as a page. The owner
writes it in plain words, and nothing is booked until a person says yes.

- **Signed facts.** Every card carries the owner's Ed25519 signature. Agents verify it themselves and turn away any
  altered copy; third parties attest single claims like "dog-friendly".
- **Open ranking.** Every result says why it won and why the others were left out. Placement cannot be bought.
- **Proof of stay.** Only a signed booking receipt can leave a review. No stay, no review.
- **Your yes.** Agents negotiate. People decide. You see every call your agent made before you approve.

And one idea beyond them, **missed demand**: every request no business could serve is recorded. A café learns that
agents asked for vegan breakfast; Basel learns what nobody offers yet. Agents write the business plan. And the
demand waits: a traveller whose agent found nothing can ask to be told, anonymously, and the moment an owner signs the
change, that agent receives an offer signed by the business.

What the Hive will not do: sell placement, profile travellers (it learns *what* was asked, never *who*), or take
orders from a listing (card text is data, never instructions). The full story: [documentation/VISION.md](documentation/VISION.md).

> On GitHub you find projects to work on. On Adobee Hive, agents find businesses and people to work with.

## What works today

An agent that never opens a website discovers, verifies, compares and books a fictional Basel hotel, end to end
over MCP. Try it with any MCP client, Claude included.

| Piece | Where |
| --- | --- |
| Hive cards for six fictional Basel businesses, signed with Ed25519 | `code/backend/app/hive.py`, `hive_seed.py` |
| MCP server: discover, get card, check availability, book, cancel, review | `code/backend/app/mcp_server.py` |
| Traveller agent: an OpenAI or Claude model over MCP, verifies every signature, explains its choice, books only after you approve. You watch both agents negotiate live on one stage | `code/backend/app/agent.py`, `TravellerAgent.tsx`, `AgentTrace.tsx` |
| Owner studio: plain-language edit, diff, sign and publish, missed demand | `code/backend/app/owner.py`, `OwnerStudio.tsx` |
| Trust: owner keys pinned in each Hive's registry (`/.well-known/hive.json`); the agent checks every card itself; a changed copy and a stranger-signed copy both fail the live tamper test | `hive.py`, `agent.verify_card`, `CardPage.tsx` |
| Human card page with direct booking | `CardPage.tsx` |
| Basel demand map: what agents asked for that nobody offers | `DemandMap.tsx` |
| Whose rules: signed rulesets a person picks per search ("Dogs, verified" by a dog owners' club). They only narrow, and every answer names the ruleset and what it changed | `code/backend/app/rulesets.py` |
| Standing requests: when nothing fits, an agent can wait anonymously; the owner sees how many wait for which change, and publishing it sends each a signed offer | `code/backend/app/waiting.py`, `OwnerStudio.tsx` |
| Second opinion: a separate sceptic agent checks each held booking against the request and the signed card before you approve | `code/backend/app/second_opinion.py` |
| Ask the Hive: questions about five real businesses (adventures, AI workflows, process instrumentation, creative software, BaselHack itself) answered from unclaimed public-info cards, with a mood you choose and a yes before any hand-off | `code/backend/app/domains/explore.py`, `examples.py`, `AskHive.tsx` |
| Second use case, HR (starter): person cards, skills search, introductions only with consent | `code/backend/app/domains/hr.py` |

The live agent runs on OpenAI (or Claude, see `LLM_PROVIDER`). Without an API key everything still runs on a
scripted planner over the same tools, so the demo never dies. Bookings are held server-side until you approve, once. The
web app speaks English, German, French and Italian.

## Quick start

```bash
cd code/backend && pip install -r requirements.txt -r requirements-dev.txt && pytest -q
uvicorn app.main:app --port 8000          # add OPENAI_API_KEY for the live agent
cd ../frontend && npm install && npm test && npm run dev   # http://localhost:5173
```

Docker, AWS auto-deploy and connecting Claude: [documentation/DEPLOY.md](documentation/DEPLOY.md).

## Repository

| Folder | Contents |
| --- | --- |
| [`code/`](code) | `backend/` FastAPI + DuckDB + MCP + agents, `frontend/` React + Vite, `scripts/aws/`, `docker-compose.yml` |
| [`documentation/`](documentation) | [Challenge](documentation/CHALLENGE.md) · [Vision](documentation/VISION.md) · [Pitch](documentation/PITCH.md) · [Demo script](documentation/DEMO.md) · [Architecture](documentation/ARCHITECTURE.md) · [Run and deploy](documentation/DEPLOY.md) · [Brand](documentation/BRAND.md) · [Team](documentation/TEAM.md) |
| [`assets/`](assets) | Whiteboard photos, jury slide, logo and mascot exports ([index](assets/README.md)) |

Working on it: [CONTRIBUTING.md](CONTRIBUTING.md) for people, [AGENTS.md](AGENTS.md) for coding agents,
[SECURITY.md](SECURITY.md) for what is protected. Layout follows the BaselHack template. The Basel businesses in the seed data are fictional; the five example cards on `/ask` are real businesses compiled from their public websites and marked unclaimed.
MIT licensed, see [license.txt](license.txt).
