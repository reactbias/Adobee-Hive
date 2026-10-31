<p align="center"><img src="assets/brand/adobee-hive-wordmark.png" alt="Adobee Hive" width="420"></p>

<p align="center"><b>The front door, signed.</b></p>

BaselHack 2026, Team B6, for Adobe's challenge **The Post-Website Business**: how does a local hotel, café or shop
stay found, trusted and bookable when its first visitor is an AI agent, not a person on a website?

## Links

| What | Where |
| --- | --- |
| Live app (deploys from `main`) | https://reactbias.github.io/Adobee-Hive/ · one page, three chapters: [traveller agent](https://reactbias.github.io/Adobee-Hive/#travel) · [general agent](https://reactbias.github.io/Adobee-Hive/#ask) · [business](https://reactbias.github.io/Adobee-Hive/#business) |
| Live backend | Render URL, added here once the service is live ([setup](documentation/DEPLOY.md#free-hosting-github-pages--render-the-hackathon-setup)); then `<backend>/api/health`, `<backend>/docs`, `<backend>/mcp/` |
| Code, PRs, issues | [Repository](https://github.com/reactbias/Adobee-Hive) · [Pull requests](https://github.com/reactbias/Adobee-Hive/pulls) · [Issues](https://github.com/reactbias/Adobee-Hive/issues) · [Actions (CI and deploys)](https://github.com/reactbias/Adobee-Hive/actions) |
| Local, after the [5-minute setup](#run-it-locally-in-5-minutes) | App http://localhost:5173 · API docs http://localhost:8000/docs · health http://localhost:8000/api/health · MCP http://localhost:8000/mcp/ |
| Team, lanes and joining | [documentation/TEAM.md](documentation/TEAM.md) |

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
| Traveller agent: an OpenAI or Claude model over MCP, verifies every signature, explains its choice, books only after you approve. You watch it play out as a group chat of named agents, and after the booking it offers next steps | `code/backend/app/agent.py`, `TravellerAgent.tsx`, `GroupChat.tsx` |
| One page in three chapters: the traveller agent, a general agent for any business, then the business's side, where the hotel sees the booking arrive | `App.tsx`, `TravellerAgent.tsx`, `components/Chapter.tsx` |
| Owner studio (chapter 3): plain-language edit, diff, sign and publish, missed demand | `code/backend/app/owner.py`, `panels/OwnerPanel.tsx` |
| Trust: owner keys pinned in each Hive's registry (`/.well-known/hive.json`); the agent checks every card itself; a changed copy and a stranger-signed copy both fail the live tamper test in the owner studio | `hive.py`, `agent.verify_card`, `panels/OwnerPanel.tsx` |
| Basel demand map (chapter 3): what agents asked for that nobody offers | `panels/DemandPanel.tsx` |
| Whose rules: signed rulesets a person picks per search ("Dogs, verified" by a dog owners' club). They only narrow, and every answer names the ruleset and what it changed | `code/backend/app/rulesets.py` |
| Standing requests: when nothing fits, an agent can wait anonymously; the owner sees how many wait for which change, and publishing it sends each a signed offer | `code/backend/app/waiting.py`, `panels/OwnerPanel.tsx` |
| Second opinion: a separate sceptic agent checks each held booking against the request and the signed card before you approve | `code/backend/app/second_opinion.py` |
| Ask the Hive (chapter 2, the general agent): questions about five real businesses (adventures, AI workflows, process instrumentation, creative software, BaselHack itself) answered from unclaimed public-info cards, with a mood you choose and a yes before any hand-off | `code/backend/app/domains/explore.py`, `examples.py`, `panels/AskPanel.tsx` |
| Second use case, HR (starter): person cards, skills search, introductions only with consent | `code/backend/app/domains/hr.py` |

The live agent runs on OpenAI (or Claude, see `LLM_PROVIDER`). Without an API key everything still runs on a
scripted planner over the same tools, so the demo never dies. Bookings are held server-side until you approve, once. The
web app speaks English, German, French and Italian.

## Run it locally in 5 minutes

You need **Git**, **Python 3.12** and **Node 22**. No API key: without one, the agent runs on a scripted planner
over the same MCP tools and the header shows **Offline mode**.

**1. Clone and configure**

```bash
git clone https://github.com/reactbias/Adobee-Hive.git && cd Adobee-Hive
cp code/.env.example code/.env        # Windows PowerShell: copy code\.env.example code\.env
```

For the live agent, put the team's key after `OPENAI_API_KEY=` in `code/.env`. That file is gitignored; never
commit a key or paste it in a chat.

**2. Backend** (one terminal, from `code/backend`)

| macOS, Linux | Windows (PowerShell) |
| --- | --- |
| `python3.12 -m venv .venv` | `py -3.12 -m venv .venv` |
| `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |

Then, on both:

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q                                              # all green, including a booking over MCP
uvicorn app.main:app --port 8000 --env-file ../.env
```

**3. Frontend** (a second terminal, from `code/frontend`)

```bash
npm ci
npm test                                               # component tests, no backend needed
npm run dev
```

**4. Open it**

| URL | What |
| --- | --- |
| http://localhost:5173 | The app, one page; click the first example |
| http://localhost:8000/docs | Every REST endpoint, to read and try |
| http://localhost:8000/api/health | `"llm": "openai"` with a key, `"mock"` offline |
| http://localhost:8000/mcp/ | The MCP endpoint for any agent, Claude included ([how](documentation/DEPLOY.md#point-any-agent-at-the-hive)) |

Before you push, run the checks in [CONTRIBUTING.md](CONTRIBUTING.md#checks-to-run-before-you-push). What each
endpoint, MCP tool and page does: [ARCHITECTURE.md](documentation/ARCHITECTURE.md). Docker and hosting:
[DEPLOY.md](documentation/DEPLOY.md). If PowerShell refuses to run `Activate.ps1`, run
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

## Repository

| Folder | Contents |
| --- | --- |
| [`code/`](code) | `backend/` FastAPI + DuckDB + MCP + agents, `frontend/` React + Vite, `scripts/aws/`, `docker-compose.yml` |
| [`documentation/`](documentation) | [Challenge](documentation/CHALLENGE.md) · [Vision](documentation/VISION.md) · [Pitch](documentation/PITCH.md) · [Demo script](documentation/DEMO.md) · [Architecture](documentation/ARCHITECTURE.md) · [Run and deploy](documentation/DEPLOY.md) · [Brand](documentation/BRAND.md) · [Team](documentation/TEAM.md) |
| [`assets/`](assets) | Whiteboard photos, jury slide, logo and mascot exports ([index](assets/README.md)) |

Working on it: [CONTRIBUTING.md](CONTRIBUTING.md) for people, [AGENTS.md](AGENTS.md) for coding agents,
[SECURITY.md](SECURITY.md) for what is protected. Layout follows the BaselHack template. The Basel businesses in the seed data are fictional; the five example cards in chapter 2 are real businesses compiled from their public websites and marked unclaimed.
MIT licensed, see [license.txt](license.txt).
