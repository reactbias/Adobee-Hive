# Developer guide

How to start everything on your machine, click through what is built, point a real agent at it, and find the code
behind each piece. The overview is in the [readme](../readme.md); what every endpoint and tool does is in
[ARCHITECTURE.md](ARCHITECTURE.md).

## Start it

You need Git, Python 3.12 and Node 22. No API key is needed: without one the header shows **Offline mode** and a
scripted planner walks the same MCP tools.

```bash
git clone https://github.com/reactbias/Adobee-Hive.git && cd Adobee-Hive
cp code/.env.example code/.env          # Windows PowerShell: copy code\.env.example code\.env
```

Backend, in one terminal (Windows: `py -3.12 -m venv .venv` and `.venv\Scripts\Activate.ps1`):

```bash
cd code/backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000 --env-file ../.env
```

Frontend, in a second terminal:

```bash
cd code/frontend
npm ci
npm run dev                             # http://localhost:5173, proxies /api and /mcp to port 8000
```

Or both at once with Docker: `cd code && docker compose up --build`.

| Open | What you see |
| --- | --- |
| http://localhost:5173 | The app: one page, three chapters |
| http://localhost:8000/docs | Every REST endpoint, to read and try |
| http://localhost:8000/api/health | `"llm": "mock"` offline, `"openai"` with a key |
| http://localhost:8000/mcp/ | The MCP endpoint for any agent |

### With the live model

Put the key after `OPENAI_API_KEY=` in `code/.env` (gitignored; never commit it, never paste it in a chat) and
restart the backend. The header switches from **Offline mode** to **AI live**. `OPENAI_MODEL` defaults to
`gpt-5-mini`. Claude works too: `ANTHROPIC_API_KEY`, or `LLM_PROVIDER=claude`. Every other setting is explained in
`code/.env.example`.

## Use it, chapter by chapter

The data is seeded on start and is fictional, except the five unclaimed example cards in chapter 2. Restarting the
backend gives you a fresh Hive.

### 1. Traveller agent (`#travel`)

1. Tap the first example under **Try**, or type your own request and press **Enter** (Shift+Enter for a new line).
   In Chrome, Edge and Safari the microphone button next to **Send to my agent** lets you speak it instead; it uses
   the browser's own speech recognition in the page's language and is hidden in browsers without one (Firefox).
2. The dark panel is a group chat: your agent calls the Hive over MCP, each business answers, and every signature is
   checked. The critic argues for the strongest alternative, the verifier checks the held booking. The chat follows
   the newest message; scroll up to reread and it waits, with a **New messages** button to jump back.
3. Nothing is booked until you click **Approve booking**. You get a signed receipt, can leave a review with it, and
   get next steps (calendar, a café nearby, the business's side).
4. **Stress test** (folded under the examples) plants a manipulated mirror listing; your agent refuses it. With
   **Rules off** you see what an unguarded agent would have done. Nothing is booked in either case.

Replay and Skip in the chat header replay the run or jump to the end, handy on stage.

### 2. General agent (`#ask`)

Ask anything about the example businesses (adventures, AI workflows, instrumentation, creative software, BaselHack),
by an example or in your own words. Answers come from the businesses' own cards, say what was left out and why, and
list the rules in force. An action (such as "plan a safari") waits for your yes and then only hands you to the
business's own site.

### 3. Business (`#business`)

- **Demand map:** what agents asked for that nobody offers. **Simulate 40 traveller searches** fills it.
- **Owner studio:** you are the owner of Hotel Rheinblick (or pick another). Write a change in plain words, for
  example "Add sauna. The courtyard double is 165 francs from today", click **Preview change**, check the diff, then
  **Sign and publish**. Every agent reads the new signed card at once, and agents waiting for that change get an
  offer.
- **Can a scraper fake this card?** changes one fact without the owner's key and shows the agent rejecting it.

On the hosted backend, owner edits need the team's `OWNER_EDIT_TOKEN`; locally they are open.

## Point a real agent at it

The MCP endpoint is `http://localhost:8000/mcp/` (Streamable HTTP), also listed in `/.well-known/hive.json`. Add it
as a custom connector in Claude or any MCP client and ask: *"Find me a dog-friendly hotel near Basel SBB under
CHF 200 for next weekend and book it."* The tools are listed in [ARCHITECTURE.md](ARCHITECTURE.md). More in
[DEPLOY.md](DEPLOY.md#point-any-agent-at-the-hive).

## Test and check

```bash
cd code/backend && ruff check . && ruff format --check . && pytest -q      # includes a booking over MCP
cd code/frontend && npm run format:check && npm test && npm run build       # npm test needs no backend
```

CI runs the same on every PR. Work test-first, and ship every user-facing string in English, German (ss, never ß),
French and Italian in the same PR: [CONTRIBUTING.md](../CONTRIBUTING.md#checks-to-run-before-you-push).

## Where things live

| You want to change | Look in |
| --- | --- |
| The page, its three chapters, the chat | `code/frontend/src/pages/TravellerAgent.tsx`, `components/GroupChat.tsx`, `components/Chapter.tsx` |
| Speech input | `code/frontend/src/components/MicButton.tsx` |
| Chapter 2 and 3 panels | `code/frontend/src/panels/` |
| Any text people read | `code/frontend/src/i18n/en.ts`, `de.ts`, `fr.ts`, `it.ts` |
| Look and feel | `code/frontend/src/styles.css`, [BRAND.md](BRAND.md) |
| Cards, signatures, MCP tools | `code/backend/app/hive.py`, `mcp_server.py` |
| The agents | `code/backend/app/agent.py`, `critic.py`, `second_opinion.py` |
| A new use case | `code/backend/app/domains/`, see [CONTRIBUTING.md](../CONTRIBUTING.md#add-a-use-case) |

## When something is off

| Symptom | Fix |
| --- | --- |
| Header says **Backend unreachable** | Start the backend on port 8000; the frontend proxies to it |
| **Offline mode** although you set a key | The backend reads `code/.env` only with `--env-file ../.env`; restart it |
| No microphone button | The browser has no speech recognition (Firefox); type instead |
| Microphone button crossed out | The browser blocked the microphone; allow it in the address bar and tap again |
| PowerShell refuses `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, once |
