<p align="center"><img src="assets/brand/adobee-hive-wordmark.png" alt="Adobee Hive" width="420"></p>

<p align="center"><b>The front door, signed.</b></p>

BaselHack 2026, Team B6, for Adobe's challenge **The Post-Website Business**: how does a local hotel, café or shop
stay found, trusted and bookable when its first visitor is an AI agent, not a person on a website?

## Links

| What | Where |
| --- | --- |
| Live app (deploys from `main`) | https://reactbias.github.io/Adobee-Hive/ · one page, two chapters: [agent network](https://reactbias.github.io/Adobee-Hive/#travel) · [business](https://reactbias.github.io/Adobee-Hive/#business) |
| Live backend | [adobee-hive.onrender.com](https://adobee-hive.onrender.com/api/health) ([setup](documentation/DEPLOY.md#free-hosting-github-pages--render-the-hackathon-setup)): [`/api/health`](https://adobee-hive.onrender.com/api/health), [`/docs`](https://adobee-hive.onrender.com/docs), MCP for agents [`/mcp/`](https://adobee-hive.onrender.com/mcp/) · [Render dashboard](https://dashboard.render.com) (access: ask the repository owner) |
| Presenter view (stage) | [`?demo`](https://reactbias.github.io/Adobee-Hive/?demo) adds the stress test, Simulate 40, the tamper test and the raw MCP exchange · [live activity feed](https://reactbias.github.io/Adobee-Hive/?demo#activity) |
| Code, PRs, issues | [Repository](https://github.com/reactbias/Adobee-Hive) · [Pull requests](https://github.com/reactbias/Adobee-Hive/pulls) · [Issues](https://github.com/reactbias/Adobee-Hive/issues) · [Actions (CI and deploys)](https://github.com/reactbias/Adobee-Hive/actions) |
| Local, after the [5-minute setup](#run-it-locally-in-5-minutes) | App http://localhost:5173 · API docs http://localhost:8000/docs · health http://localhost:8000/api/health · MCP http://localhost:8000/mcp/ |
| Team, lanes and joining | [documentation/TEAM.md](documentation/TEAM.md) |

## Where to read what

Six questions a reviewer asks, one hop each.

| Question | Page |
| --- | --- |
| What is this, and why is it plausible in five years? | [VISION.md](documentation/VISION.md) |
| How does a search reach another Hive? | [FEDERATION.md](documentation/FEDERATION.md#how-far-to-look-the-radius) |
| How is a Hive measured, and how is a business? | [FEDERATION.md](documentation/FEDERATION.md#two-levels-of-trust) |
| How does a business or a person join a Hive? | [REGISTRATION.md](documentation/REGISTRATION.md) |
| How do I run it, and what does each part do? | [DEVELOPER.md](documentation/DEVELOPER.md) · [ARCHITECTURE.md](documentation/ARCHITECTURE.md) · [DIAGRAMS.md](documentation/DIAGRAMS.md) |
| How is it tested, and what is protected? | [DEVELOPER.md](documentation/DEVELOPER.md#tests-and-checks) · [tools/README.md](code/backend/tools/README.md) · [SECURITY.md](SECURITY.md) |
| How do I search it from my own code? | [SEARCH_API.md](documentation/SEARCH_API.md) |

And the one a jury asks last: **what does it not do?**
[LIMITS.md](documentation/LIMITS.md) — every gap we know of, checked against the code.

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
| One page in two chapters: one agent chat for a room or any business, then the business's side, where the hotel sees the booking arrive | `App.tsx`, `TravellerAgent.tsx`, `components/Chapter.tsx` |
| Owner studio (chapter 2): plain-language edit, diff, sign and publish, missed demand | `code/backend/app/owner.py`, `panels/OwnerPanel.tsx` |
| Trust: owner keys pinned in each Hive's registry (`/.well-known/hive.json`); the agent checks every card itself; a changed copy and a stranger-signed copy both fail the live tamper test in the owner studio | `hive.py`, `agent.verify_card`, `panels/OwnerPanel.tsx` |
| Basel demand map (chapter 2): what agents asked for that nobody offers | `panels/DemandPanel.tsx` |
| Whose rules: signed rulesets a person picks per search ("Dogs, verified" by a dog owners' club). They only narrow, and every answer names the ruleset and what it changed | `code/backend/app/rulesets.py` |
| Standing requests: when nothing fits, an agent can wait anonymously; the owner sees how many wait for which change, and publishing it sends each a signed offer | `code/backend/app/waiting.py`, `panels/OwnerPanel.tsx` |
| Three agents agree before you are asked: your agent proposes, a critic always argues for the strongest alternative from the open ranking, and a verifier checks the held booking against the request and the signed card. If they don't all agree, the chat says so and you still decide | `code/backend/app/critic.py`, `second_opinion.py` |
| Any business, in the same chat (chapter 1): questions about six real businesses (adventures, AI workflows, process instrumentation, creative software, life insurance, BaselHack itself) answered from unclaimed public-info cards, with a yes before any hand-off | `code/backend/app/domains/explore.py`, `examples.py`, `components/AskParts.tsx`, `lib/route.ts` |
| Web scout: when no card fits ("book me a taxi"), the agent first asks what is missing (route and time), then looks on the public web, a verifier checks each business's own site, and the find joins the Hive as an unclaimed card. Unclaimed cards say *Unclaimed · hand-off only*: the agent never books them, it takes you to the business's site after your yes. Jobs questions list the employers' careers pages | `code/backend/app/domains/scout.py`, `explore.py` |
| Live activity feed (`?demo#activity`): one line per agent step, partner or web, never a person | `code/backend/app/activity.py`, `panels/ActivityPanel.tsx` |
| Persistence: the Hive lives in DuckDB and is snapshotted to Postgres when `DATABASE_URL` is set, so a redeploy keeps cards, bookings and demand; without it the backend seeds a fresh Basel | `code/backend/app/storage.py` |
| Second use case, HR (starter): person cards, skills search, introductions only with consent | `code/backend/app/domains/hr.py` |
| Federated search with a hop radius: a query carries how far it may travel, the time it has left and the hubs it has already visited; every card that comes back is verified against the key pinned in *its own* hub, so a relaying hub can withhold a card but never forge one ([how](documentation/FEDERATION.md)) | `code/backend/app/federation.py`, `components/Reach.tsx` |
| Two levels of trust: a peer *hub*'s reputation from how it has behaved, and its *calibration* from whether its published ratings matched what our people found afterwards (published minus realised, lower is better) | `reputation.py`, `calibration.py`, `connections.py` |
| Joining a hub: one signed JSON application, five checks in order, and an admission policy of `open`, `vetted`, `invite` or `closed`. A refusal is an answer with a reason and a next step ([how](documentation/REGISTRATION.md)) | `code/backend/app/registration.py` |
| Joining from a browser, without filling in a profile: point it at a folder on your disk, which is read in the page and never uploaded, and the Card is filled from it; the Ed25519 key is made in the browser and the private half is yours to download; you see the exact JSON before it is signed and sent | `panels/Onboarding.tsx`, `lib/signing.ts`, `lib/folderScan.ts` |
| Asking to be introduced to someone a search found: a `public` entry connects at once, a `confirm` one says it waits for the owner's yes before you click, and the owner accepts or declines the ones waiting on them in the business chapter | `components/Connect.tsx`, `components/ConnectionRequests.tsx`, `code/backend/app/connections.py` |
| Scoring the real meeting afterwards, which is the only thing that teaches this Hive which other Hives to believe: tenths of a star, once, with the deadline visible, and the answer shows what the hub promised against what you found, and where that leaves the hub it came from | `panels/Introductions.tsx`, `code/backend/app/hub.py` |
| Item-level sharing: `public`, `confirm`, `push` (held, never searchable) or `never`, set per item, and the stricter of the item's flag and the entity's default always wins | `code/backend/app/sharing.py` |
| A hub directory and an instance finder: pick a Hive before you use one, instances.social style, with the one column a Mastodon directory cannot offer — how honest each hub's ratings turned out to be | `admin.directory`, `panels/InstanceFinder.tsx` |
| Running a hub in a browser: `?admin`, the hub's password for a short-lived session, then the overview, the signup queue, the entity list, the blocklist and the neighbours | `code/backend/app/admin.py`, `panels/AdminPanel.tsx` |
| The network, live: this hub in the centre of a honeycomb, each peer a cell with an edge coloured by its calibration, a blocked peer still drawn and visibly cut | `panels/NetworkPanel.tsx`, `lib/network.ts` |
| Three peered hubs on one machine, reachable from any phone on the wifi, seeded through the real signup endpoint ([how](documentation/DEVELOPER.md#three-hubs-on-one-machine-lansh)) | `lan.sh`, `tools/seed_vaults.py` |
| A test corpus whose cards never use the words a person would type, with an answer key, so search can be measured rather than demonstrated | [`testdata/`](testdata/README.md), `tools/make_corpus.py` |
| `contact` on every entity: the key is always there, an empty value means "not published", and a channel the owner marked `never` is absent rather than listed as withheld | `hive.with_contact`, `documentation/cards/README.md` |
| Semantic similarity with no key, no network and no new dependency: stems, German compound splitting, a four-language concept table and character trigrams above a measured floor. A score component in `hive.discover` with its own readable reason, so "haircut" finds *"Cut, wash and finish"*: **19/41 first on the answer key, against 0/41 for the substring matching it replaced** | `code/backend/app/semantic.py`, `tools/eval_answer_key.py` |

The live agent runs on OpenAI (or Claude, see `LLM_PROVIDER`). Without an API key everything still runs on a
scripted planner over the same tools, so the demo never dies. Bookings are held server-side until you approve, once. The
web app speaks English, German, French and Italian.

## Who tests the tests

Coverage proves a line ran. It does not prove a test would fail if that line were wrong. So on every pull
request, after the ordinary tests pass, CI **deliberately breaks the code** and checks the suite notices:
remove the loop guard that stops a federated search revisiting a hub, flip the sign of a hub's calibration
error, let a stale introduction be scored, let a blocked entity back into a search. Thirty-five of these,
each aimed at a promise the design rests on. **Every one must fail the tests.** A change nothing notices is
a hole in the tests, named and located.

It has already found four real holes. The clearest: `HttpTransport` had **no test at all** — the fakes
replaced it wholesale, so the parser that supplies the keys every relayed card is verified against was
never executed. Blanking `owner_keys` there passed all twenty-four federation tests. Coverage could not see
it, because the line *was* covered, by a fake.

The harness is itself tested (`tests/test_mutation.py`), because the one failure mode that makes such a tool
worse than useless is a confident false all-clear — which happened once, when two test files were missing
from its list and eight breakages were reported as "survived" while the real tests caught every one.

How it works and how to run it: [code/backend/tools/README.md](code/backend/tools/README.md).

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

Taking over the code? The [diagrams](documentation/DIAGRAMS.md) show how the parts fit; the [developer guide](documentation/DEVELOPER.md) shows how to start, test, call and ship every part.

## Repository

| Folder | Contents |
| --- | --- |
| [`code/`](code) | `backend/` FastAPI + DuckDB (Postgres snapshot) + MCP + agents, `frontend/` React + Vite, `docker-compose.yml` |
| [`documentation/`](documentation) | [Challenge](documentation/CHALLENGE.md) · [Vision](documentation/VISION.md) · [Pitch](documentation/PITCH.md) · [Demo script](documentation/DEMO.md) · [Architecture](documentation/ARCHITECTURE.md) · [Federation](documentation/FEDERATION.md) · [The Card](documentation/cards/README.md) · [Joining a hub](documentation/REGISTRATION.md) · [Search API](documentation/SEARCH_API.md) · [Known limits](documentation/LIMITS.md) · [Diagrams](documentation/DIAGRAMS.md) · [Developer guide](documentation/DEVELOPER.md) · [Run and deploy](documentation/DEPLOY.md) · [Brand](documentation/BRAND.md) · [Team](documentation/TEAM.md) |
| [`testdata/`](testdata/README.md) | Fictional vaults and the answer key search is measured against; `lan.sh` seeds them into three hubs through the real signup endpoint |
| [`assets/`](assets) | Whiteboard photos, jury slide, logo and mascot exports ([index](assets/README.md)) |

Working on it: [CONTRIBUTING.md](CONTRIBUTING.md) for people, [AGENTS.md](AGENTS.md) for coding agents,
[SECURITY.md](SECURITY.md) for what is protected. Layout follows the BaselHack template. The Basel businesses in the seed data are fictional; the six example cards are real businesses compiled from their public websites and marked unclaimed.
MIT licensed, see [license.txt](license.txt).
