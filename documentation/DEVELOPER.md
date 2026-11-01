# Developer guide

How to start everything that is built, use it, change it and ship it. The [readme](../readme.md) says what Adobee
Hive is; this page is for whoever picks up the work. Every command here was run against `main` before it was written
down; if one stops working, fix the command or the code in the same PR.

## The parts

| Part | Where | Runs on | What it is |
| --- | --- | --- | --- |
| Backend | `code/backend/app` | http://localhost:8000 | FastAPI: the REST API for the app, the Hive MCP server at `/mcp/`, the agents, DuckDB |
| Frontend | `code/frontend/src` | http://localhost:5173 | React + Vite: one page in two chapters (the agent network for a room or any business, the business's side) |
| Data | `code/backend/data/abh.duckdb` | local file, gitignored | Signed cards, bookings, demand; seeded with fictional Basel businesses on first start |

How the parts fit, in four pictures: [DIAGRAMS.md](DIAGRAMS.md). Which module does what: [ARCHITECTURE.md](ARCHITECTURE.md). Where each one is hosted: [DEPLOY.md](DEPLOY.md).

## Start it

You need **Git**, **Python 3.12** and **Node 22**. No API key is needed.

```bash
git clone https://github.com/reactbias/Adobee-Hive.git && cd Adobee-Hive
cp code/.env.example code/.env        # Windows PowerShell: copy code\.env.example code\.env
```

**Backend**, in a first terminal:

```bash
cd code/backend
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: py -3.12 -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000 --env-file ../.env
```

**Frontend**, in a second terminal:

```bash
cd code/frontend
npm ci
npm run dev
```

Open http://localhost:5173. In development Vite forwards `/api`, `/mcp` and `/.well-known` to the backend on port
8000 (`vite.config.ts`), so the app needs no URL setting. Check the backend with
`curl http://localhost:8000/api/health`: `"llm": "mock"` means offline mode, `"openai"` means the key is in use.
http://localhost:8000/docs lists every endpoint and lets you try it.

**A second copy next to the first** (for example a demo copy you don't want to disturb): give it its own ports and
data file.

```bash
DUCKDB_PATH=./data/second.duckdb uvicorn app.main:app --port 8001 --env-file ../.env   # code/backend
VITE_DEV_BACKEND=http://localhost:8001 npm run dev -- --port 5180                     # code/frontend
```

**The whole stack in Docker**: `cd code && docker compose up --build` (app on 5173, backend on 8000, data in a
Docker volume).

## Three hubs on one machine (`lan.sh`)

A single hub cannot show federation. [`lan.sh`](../lan.sh) starts three real ones — `basel`, `zurich`, `bern` —
each configured with the other two as `HIVE_PEER_URLS`, on this machine, bound to the LAN address rather than to
localhost:

```bash
./lan.sh up       # three hubs, seed the test vaults, build the app, print the join URL
./lan.sh check    # is this machine actually reachable from another device?
./lan.sh down     # stop everything
```

What it does, and why each part is the way it is:

- **Three hubs, peered both ways.** Only `basel` seeds the fictional Basel cards (`SEED_ON_EMPTY`); `zurich` and
  `bern` start empty and are filled in the next step. Each gets its own DuckDB file under `.lan/`.
- **Registration through the real endpoint.** `tools/seed_vaults.py` reads the markdown vaults in
  [`testdata/`](../testdata/README.md) and applies to each hub with `POST /api/hub/register`, signed, so what you
  search afterwards arrived the way a member would arrive. `ADMISSION_POLICY` is `open` for the run.
- **The app same-origin, over http.** It is built with `VITE_API_URL=""` and served by `vite preview` with the
  `basel` hub proxied behind `/api`. An https page cannot call an http hub, and Chrome's Private Network Access
  blocks a private address calling another one, so proxying is the only arrangement that works from a phone on
  the same wifi. The app's port is fixed at 8440 because it is the URL people are given.
- **A directory with real rows.** `http://<lan-ip>:8420/api/hub/directory` now answers with three hubs that each
  described themselves, which is what `InstanceFinder` and `NetworkPanel` render.

If another device cannot reach it but this one can, the wifi has client isolation; use a phone hotspot and put
every device on it. What federation does with those hubs: [FEDERATION.md](FEDERATION.md). How someone joins one:
[REGISTRATION.md](REGISTRATION.md).

## Models and offline mode

All settings are environment variables in `code/.env` (gitignored; template in `code/.env.example`).

| Variable | Default | What it does |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | Turns on the live agent, model owner edits and the model verifier. Put the team's key here or in the host's dashboard, never in the repo or a chat |
| `OPENAI_MODEL` | `gpt-5-mini` | The one OpenAI model for all three |
| `LLM_PROVIDER` | empty | `openai`, `claude` or `offline`. Empty picks OpenAI if its key is set, then Claude, then offline. `offline` forces the scripted planner even with a key |
| `AGENT_MAX_TURNS` | `10` | Caps each agent run |
| `LLM_CALLS_PER_CLIENT_HOUR`, `LLM_CALLS_TOTAL_HOUR` | `30`, `300` | Cost guard on calls that may reach a model |
| `OWNER_EDIT_TOKEN`, `DEMO_RESET_TOKEN` | empty | When set, owner edits need `X-Owner-Token` and a reset needs `X-Demo-Token`. Leave empty locally for the owner studio — but the three owner MCP tools below fail closed, so set `OWNER_EDIT_TOKEN` to try an agent editing its own card |
| `HIVE_MCP_URLS` | empty | Comma-separated MCP URLs of other Hives the agent searches too |
| `DUCKDB_PATH` | `code/backend/data/abh.duckdb` | Where the data lives |
| `DATABASE_URL` | empty | Optional Postgres: the DuckDB file is restored from it on boot and saved after each write, so data survives redeploys |
| `HIVE_PEER_URLS` | empty | Peer Hives for hop-limited federated search: comma-separated base URLs. Empty means every search stays local whatever the radius |
| `HIVE_HUB_ID` | `local` | How this hub names itself in a result's `provenance` chain and in a query's `seen` list |
| `HIVE_NAME`, `HIVE_DESCRIPTION` | Basel defaults | What this hub calls itself in `/.well-known/hive.json` and in a peer's directory row |
| `HIVE_VERIFICATION` | `signed` | What this hub declares it checks before carrying an entity. Peers weigh the claim against what they observe |
| `PEER_ASK_SECONDS`, `PEER_ASK_TIMEOUT_S`, `PEER_STALE_AFTER_S` | `30`, `2`, `120` | How often peers are asked who they are, how long one may take, and when a cached answer is shown as stale. `0` turns the asking off |
| `ADMISSION_POLICY` | `vetted` | Who may join: `open`, `vetted`, `invite` or `closed`. With `invite`, `INVITE_TOKENS` holds the accepted tokens ([REGISTRATION.md](REGISTRATION.md)) |
| `ADMIN_TOKEN`, `ADMIN_PASSWORD` | empty | Running the hub. The static token is for curl and CI, the password is what a person types in the admin panel. Both unset means every admin write is refused, never open |
| `SEMANTIC_PROVIDER` | empty | `offline` or `embeddings`. Discovery ranks with it; `embeddings` is a seam with nothing in it yet and falls back to `offline`, which `GET /api/health` reports. See [LIMITS.md](LIMITS.md#discovery) |

**Without a key nothing breaks.** A scripted planner walks the same MCP tools in English, German, French and Italian,
owner edits understand simple phrases ("add sauna", "remove parking", room prices), a rule check gives the second
opinion, and the header shows *Offline mode*. If the model fails mid-run, the agent finishes offline and says so.
Every new model call needs such a fallback; the tests run without a key and without network.

## Tests and checks

The same commands CI runs on every pull request (`.github/workflows/ci.yml`), plus a secret scan with gitleaks:

```bash
cd code/backend && ruff check . && ruff format --check . && pytest -q
cd code/frontend && npm run format:check && npm test && npm run build
```

**Run the backend suite with no model key exported.** The tests pin what the offline planner writes, so an
`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in your shell makes the agent answer live and about fifteen of them fail
for a reason that has nothing to do with your change. Either keep the key in `code/.env` only (uvicorn reads it
with `--env-file`, pytest does not) or run `env -u OPENAI_API_KEY -u ANTHROPIC_API_KEY pytest -q`. CI has no key,
so it never sees this.

Fix formatting with `ruff format .` and `npm run format`. Run one file or one test while you work:

```bash
pytest -q tests/test_hive.py -k book          # code/backend
npx vitest run src/pages                      # code/frontend
```

Some tests guard the docs and the promises, not only the code: `tests/test_docs.py` fails when an endpoint, MCP
tool or panel has no row in [ARCHITECTURE.md](ARCHITECTURE.md), when a link between the docs breaks, or when this
guide names a tool or endpoint that doesn't exist. `src/i18n/*.test.ts(x)` fails on a missing translation or text
outside `t()`. How to write tests first: [CONTRIBUTING.md](../CONTRIBUTING.md#tests-first).

### Mutation testing: does the suite actually notice?

```bash
cd code/backend && source .venv/bin/activate
python tools/mutate.py                  # the 76 curated mutants; all must die
python tools/mutate.py --modules app/semantic.py,app/hive.py   # only these modules
python tools/mutate.py --random 8       # seeded random operator and constant flips
python tools/mutate.py --all
```

Each mutant breaks one line, runs the suite, and restores the file. A mutant the tests still pass is a
missing assertion, printed with the line to look at. Exit code is the survivor count, so CI gates on it.

There is no way to know whether the tests notice a break except to run them against it, so the cost is
one suite run per mutant. Four are checked at a time, each in its own throwaway copy of the tree: measured
over the 71 mutants there were when this was written, a full local run took 19m34s sequentially and 6m28s
with four workers, same mutants, same `No survivors.` On a runner the whole job is about eight minutes. CI
goes further and checks only the modules a pull request touched, keeping every one of them for each push to
main — `--modules app/calibration.py` is three mutants and 43s. It stays a separate CI job rather than part of
`backend` so a survivor reads as "the tests have a hole", not "the build is broken".

Your checkout is never mutated — the copies are — and they are deleted on the way out, including on
SIGINT, SIGTERM and SIGHUP. A run still refuses to start if an older in-place run left a mutant behind.
Full notes, including the holes it has found and the three it has not closed:
[code/backend/tools/README.md](../code/backend/tools/README.md).

## Be the agent: the MCP endpoint

Any MCP client can use the Hive at `http://localhost:8000/mcp/` (Streamable HTTP, stateless, JSON answers). Agents
find it in `/.well-known/hive.json`, together with each business's pinned public key. The tools are listed in
[ARCHITECTURE.md](ARCHITECTURE.md#mcp-tools-mcp-streamable-http).

**With curl** (macOS, Linux, Git Bash), one request per call, no session needed:

```bash
curl -s http://localhost:8000/mcp/ \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"hive_discover",
       "arguments":{"kind":"hotel","near":"basel sbb","features":["dog-friendly"],"max_price_chf":200}}}'
```

Use `"method":"tools/list"` (no params) to see every tool with its arguments.

`hive_discover` searches everything on the hub by what it **offers** and what it **needs**; `kind` only narrows
it. `looking_for` says which side of the market you are on — `offers` (the default) finds whoever provides the
thing, `needs` whoever wants what you provide, `any` both. So this finds the people looking for a contractor:

```bash
curl -s http://localhost:8000/mcp/ \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"hive_discover",
       "arguments":{"query":"svelte contractor","looking_for":"needs"}}}'
```

Every result says whether it is `claimed` by its subject and whether it is `bookable`: an unclaimed card was
compiled from public information, so it can only be handed off to the business's own site after a person's yes.

**An agent looking after its own person's card** has the three owner tools: `hive_owner_card` (the owner's view,
no token needed, guest names as initials without one), `hive_owner_propose` (plain words in, a diff out, nothing
published) and `hive_owner_publish` (the diff becomes the live, re-signed card). The owner token goes in the
`X-Owner-Token` **header of the connection**, never in an argument, and the two write tools refuse without it —
including on a hub that has no `OWNER_EDIT_TOKEN` set, so start the backend with one to try them:

```bash
export OWNER_TOKEN=$(python -c 'import secrets; print(secrets.token_hex(16))')
OWNER_EDIT_TOKEN=$OWNER_TOKEN uvicorn app.main:app --reload       # from code/backend
curl -s http://localhost:8000/mcp/ \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H "X-Owner-Token: $OWNER_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"hive_owner_propose",
       "arguments":{"card_id":"hotel-gare","instruction":"add dog-friendly, standard double 150"}}}'
```

`changes` in the answer is what an agent shows its person before anything moves; publishing takes `proposed`
back unchanged. Worked examples of all three, with the refusals:
[SEARCH_API.md](SEARCH_API.md#the-owners-own-three-tools--hive_owner_card-hive_owner_propose-hive_owner_publish).

**With Python**, a whole booking: discover, check availability, book. Save it as `book.py` and run it with the
backend's virtual environment active (it has the `mcp` package). Use dates in the future.

```python
import asyncio
import json

from mcp import Client

DATES = {"check_in": "2026-11-06", "check_out": "2026-11-08", "guests": 2}


async def main() -> None:
    async with Client("http://localhost:8000/mcp/") as hive:

        async def call(tool: str, **args):
            result = await hive.call_tool(tool, args)
            return json.loads(result.content[0].text)

        found = await call("hive_discover", kind="hotel", near="basel sbb", features=["dog-friendly"], max_price_chf=200, **DATES)
        best = found["matches"][0]  # found["excluded"] says why the others were left out
        print("pick:", best["id"], best["why"])

        free = await call("hive_check_availability", card_id=best["id"], **DATES)
        room = free["available_units"][0]
        print("room:", room["id"], room["total_chf"], "CHF")

        booked = await call("hive_book", card_id=best["id"], unit_id=room["id"], guest_name="Mara Keller", agent="my-agent", **DATES)
        print("booked:", booked["booking_id"])  # keep booked["receipt"] for hive_cancel and hive_review


asyncio.run(main())
```

A real agent shows the human the pick and the price and asks before `hive_book`. Our own agent does that by holding
the call (next section). To try the Hive from Claude, add the URL of a deployed backend's `/mcp/` as a custom
connector ([DEPLOY.md](DEPLOY.md#point-any-agent-at-the-hive)); a connector can't reach `localhost`.

## Our agent over REST: hold, then approve once

The app talks to `POST /api/agent`. A booking comes back **held** in `pending`, with the verifier's
`second_opinion`, the `critic` and `consensus`; nothing is booked until `POST /api/agent/approve`, which works once.

```bash
curl -s http://localhost:8000/api/agent -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"I am Mara Keller. Dog-friendly hotel near Basel SBB under CHF 200 a night, 2026-11-06 to 2026-11-08, 2 guests. Book it."}]}'
```

Send the `pending` object back as `{"pending": {...}}` to `/api/agent/approve` and the answer carries the booking and
its signed receipt. Sending the same `pending` again answers *already approved or expired*. Add
`"scenario": "injection"` to the first request to run the stress test with a manipulated listing.

## Signed cards

A **Hive card** is a business's agent-facing page: offering, units and prices, policies, contact. Every version is
signed with the business's Ed25519 key over canonical JSON and expires after 90 days (`valid_until`). Agents check
the signature against the key pinned in `/.well-known/hive.json`; a card that fails is not trusted.

- **Read one:** `curl -s http://localhost:8000/api/hive/cards/hotel-rheinblick` (by id or slug); `trust` holds the
  signature, its validity, attestations and verified reviews. All cards: `/api/hive/cards?kind=hotel`.
- **Check one:** `POST /api/hive/verify` with `{"card": {...}}` answers `{"signature_valid": true}`. A copy from
  `POST /api/hive/demo/forge/hotel-rheinblick` (re-signed by a stranger) answers `false`: that is the tamper test.
- **Edit one:** only through the owner studio, never in the database. `owner.py` proposes, `hive.publish` signs a new
  version and keeps the old one, so a receipt can still show what was promised.

```bash
curl -s http://localhost:8000/api/owner/hotel-rheinblick/propose -H 'Content-Type: application/json' \
  -d '{"instruction":"add sauna"}'
```

The answer holds `proposed` (the whole new card) and `summary_items` (what changed). Nothing is live yet. Send
`{"proposed": {...}}` to `/api/owner/hotel-rheinblick/publish` to sign and publish it as the next version.

- **Add a business to the demo:** add a dict to `CARDS` in `code/backend/app/hive_seed.py` (fictional only; copy an
  existing hotel), with `id`, `slug`, `kind`, `features`, `distances_m` and `units`. Seeding runs only on an empty
  database, so reset afterwards.
- **Reset local data:** `curl -s -X POST http://localhost:8000/api/demo/reset` puts back the seed cards with no
  bookings and no demand. Or stop the backend and delete `code/backend/data/abh.duckdb`.
- **A new kind of business** (events, shops) is a new domain module with its own MCP tools:
  [CONTRIBUTING.md](../CONTRIBUTING.md#add-a-use-case).

## The app, chapter by chapter

1. **Agent network (`#find`).** Click an example or write a request and press **Enter** (Shift+Enter for a new
   line), or tap the microphone and speak it. A stay goes to the booking agent; a question about any other business
   (BaselHack, Adobe, an adventure under CHF 500) goes to the Hive's cards (`lib/route.ts` decides by the words), and
   the businesses answer in the same chat with their cards. An action on an unclaimed card waits for your yes and
   then only hands you to the business's own site. Your agent, the critic and the verifier talk in a group chat while the
   MCP calls run; the chat follows the newest message, waits if you scroll up to reread, and offers *New messages*
   to jump back. The booking waits for **Approve**. After it: the signed receipt and next steps, including *Show the
   hotel's side*.
2. **The business (`#offer`).** You are the owner of the hotel just booked. The panel opens on the owner studio:
   the booking that arrived, what agents asked you for (**Use** previews that change), and your card as agents see it. Type a
   change in plain words in the box ("add sauna"), press Enter to see the diff, then **Sign and publish**: the panel
   says which version is live, and waiting agents whose request now fits get a signed offer. The **Demand map** tab
   shows what Basel asked for that nobody offers.

Presenter tools stay off the public page: open it with `?demo` (for example
`http://localhost:5173/?demo`) for the stress test (a manipulated mirror listing, rules off), *Simulate 40 traveller
searches*, the tamper test and the raw MCP exchange in the chat (`lib/demo.ts`). With `?demo` the page also ends in
the **live activity feed** (`?demo#activity`, linked from the stress test): one line per agent step as it happens,
partner cards first, the web scout when none fits, *hand-off only* for web results, Approve and receipt for partners.
It polls `GET /api/activity?after=<last>`; the lines name agents, steps and businesses, never a person.

Speech input is the browser's own Web Speech API (`components/MicButton.tsx`) in the page's language: no key and
no service of ours. Chrome and Edge send the audio to their vendor's recogniser, Safari listens on the device, and
Firefox has none, so there the button is hidden. The ask API still takes an optional `mood`; the app no longer
shows a picker.

The click-by-click demo for the jury: [DEMO.md](DEMO.md).

## Text in four languages

The app speaks English, German (Swiss spelling, ss not ß), French and Italian. Every user-facing text ships in all
four in the same PR:

1. Add the key to `code/frontend/src/i18n/en.ts`, then to `de.ts`, `fr.ts` and `it.ts`.
2. Use it in the component with `const { t } = useI18n();` and `t("your.key")`. Never write text into a component.
3. Text the backend writes itself goes in `code/backend/app/replies.py`, also in all four.

`npm test` and `pytest` fail on a missing or empty translation, English copied into another language, or text outside
`t()`. Details and register: [CONTRIBUTING.md](../CONTRIBUTING.md#strings-and-languages).

## Deploy

Nothing to run by hand: every merge to `main` deploys.

| Part | Where | How |
| --- | --- | --- |
| Frontend | https://reactbias.github.io/Adobee-Hive/ | GitHub Actions, *Deploy frontend (GitHub Pages)*; the repo variable `VITE_API_URL` points it at the backend |
| Backend | https://adobee-hive.onrender.com | Render builds `code/backend/Dockerfile` from `render.yaml`; the key and tokens are set in the Render dashboard |

Render's free tier sleeps after 15 idle minutes (a keep-warm workflow pings it) and has no lasting disk, so the
backend keeps its data as a snapshot in a free Render Postgres (`DATABASE_URL`): bookings and owner edits survive a
merge. Without `DATABASE_URL` (local runs, tests) nothing changes: the local DuckDB file only. Don't merge in
the last 15 minutes before a demo. Setup, settings and costs: [DEPLOY.md](DEPLOY.md).

## Ship a change

1. Branch from the latest `main`: `<type>/<short-topic>`, e.g. `feat/events-domain`.
2. Write the failing test first, then the change; commit them together. Never skip or loosen a test.
3. Small [Conventional Commits](https://www.conventionalcommits.org/) (`feat(hive): ...`). Keep the
   `Co-Authored-By:` trailer your coding agent adds, so the history shows people and agents honestly.
4. Added, removed or renamed a module, MCP tool, endpoint, agent, hosting piece or data path? Update
   [DIAGRAMS.md](DIAGRAMS.md) too; CI fails until the pictures show it.
5. Run the checks above, push, open a PR **against `main`** with the template filled in. Never stack PRs.
6. CI green, then merge with a **merge commit**, never squash: the jury reads the small commits.

The repo is public: no keys, tokens, `.env`, database files, local paths or personal data, and seed data stays
fictional. Lanes, review and the full rules: [CONTRIBUTING.md](../CONTRIBUTING.md); what is protected and why:
[SECURITY.md](../SECURITY.md); notes for coding agents: [AGENTS.md](../AGENTS.md).

## When something is off

| Symptom | Fix |
| --- | --- |
| The app loads but every request fails | The backend isn't running on 8000, or Vite was started before it; start the backend and reload |
| Header says *Offline mode* although you set a key | The key line in `code/.env` is empty or `LLM_PROVIDER=offline`; restart uvicorn after editing `.env` |
| A seed card you added doesn't show | Seeding only runs on an empty database: `POST /api/demo/reset` |
| `Address already in use` | Another copy runs on that port; use the second-copy commands above |
| No microphone button | The browser has no speech recognition (Firefox); type instead |
| Microphone button crossed out | The browser blocked the microphone; allow it in the address bar and tap again |
| PowerShell refuses `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, once |
| The live site is slow on the first request | Render is waking up; wait about a minute |
