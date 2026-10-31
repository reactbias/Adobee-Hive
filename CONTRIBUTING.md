# Contributing

Up to ten people and their coding agents work in this repo at once. These rules keep us out of each other's way.

## Find your lane

Each workstream owns its files (see [documentation/TEAM.md](documentation/TEAM.md)). Stay inside them. If you need
to touch another lane's file, say so in the PR description and ping that lane.

| Lane | Owns |
| --- | --- |
| Hive core | `code/backend/app/hive.py`, `hive_seed.py`, `mcp_server.py`, `db.py`, `storage.py` |
| Agents | `code/backend/app/agent.py`, `second_opinion.py`, `llm.py`, `simulate.py` |
| Owner studio | `code/backend/app/owner.py`, `code/frontend/src/pages/OwnerStudio.tsx`, `CardPage.tsx` |
| Traveller UI and brand | `code/frontend/src/pages/TravellerAgent.tsx`, `Home.tsx`, `DemandMap.tsx`, `components/AgentTrace.tsx`, `components/B6Bee.tsx`, `styles.css`, `src/i18n/`, `public/brand/` |
| HR workflows | `code/backend/app/domains/hr.py` and any new HR page or component |
| Vision | `documentation/`, `assets/` |
| Shared, change with care | `code/backend/app/main.py` (API contract), `code/frontend/src/api.ts`, `config.py`, `guard.py`, `SECURITY.md`, CI and deploy files |

A change to the API contract updates `main.py`, `api.ts` and `documentation/ARCHITECTURE.md` in the same PR.

## From the whiteboard to a PR

The kickoff sketches in [`assets/whiteboard/`](assets/whiteboard) are the backlog. Pick an open idea, find its lane,
open a `task` issue that links the photo, then a branch.

| Sketch | Built on `main` | Open, and where it goes |
| --- | --- | --- |
| [whiteboard-1](assets/whiteboard/whiteboard-1.jpg): dashboards, data extraction, "Future: hotels, events, finds" | Hotels end to end, the demand map | Events and "finds" as new domains (see below); an owner dashboard over time (Owner studio) |
| [whiteboard-1](assets/whiteboard/whiteboard-1.jpg): "find people to work with" | HR starter: person cards, skills search, intros only with consent | The person's yes/no on an intro, a person studio, CV import (HR workflows) |
| [whiteboard-4](assets/whiteboard/whiteboard-4.jpg): A2A, A2H, H2A, H2H | Agent-to-agent stage, human approval, second opinion | Opt-in outreach from a hotel's agent to a traveller's agent (Agents) |
| [whiteboard-4](assets/whiteboard/whiteboard-4.jpg): centralised vs federated | `HIVE_MCP_URLS`, each Hive publishes its key registry | A second Hive in the demo, owner-held keys (Hive core) |
| [whiteboard-4](assets/whiteboard/whiteboard-4.jpg): what a personal agent knows about its human | Request parsing in four languages | A traveller profile the human controls, never stored by the Hive (Agents) |
| [whiteboard-5](assets/whiteboard/whiteboard-5.jpg): S1 to S6, DuckDB, LLM data protection | DuckDB with S3 snapshots; no free text in logs; `store=false` | Retention limits for bookings and events (Hive core) |

## Add a use case

Hotels are the first use case; HR is the second. A new one (events, shops, services) doesn't touch either:

1. Create `code/backend/app/domains/<name>.py` with a module docstring that says what is built and what is next.
2. Pick a card kind (`"event"`, `"shop"`) and keep a fictional `EXAMPLE_CARD`. Cards go through `hive.publish`,
   so they are signed like every other card.
3. Write plain functions for the logic, then a `register(server)` that wraps each in `@server.tool()` with
   `safe(...)` from `domains.base`. Tool names start with the domain (`events_find`, `events_reserve`).
4. Add the module to `DOMAINS` in `domains/__init__.py`.
5. Add tests next to the others, and a row to the tables in `documentation/ARCHITECTURE.md`.

Keep the core's promises: signed cards, reasons for every exclusion, no paid placement, consent before personal
data moves, and a human approval for anything that commits money or a person. If a tool calls a model, edits a card
or wipes data, it goes through `guard.py`.

## Branches

`<type>/<short-topic>`, for example `feat/restaurant-tables`, `fix/owner-diff-prices`, `docs/pitch-beats`.
Branch from the latest `main` and keep branches short-lived. To catch up, merge `main` into your branch; never
rebase or force-push a branch someone else has pulled.

## Commits

The jury reviews the commit history, so make each commit one small, working step.

- [Conventional Commits](https://www.conventionalcommits.org/): `feat(hive): ...`, `fix(agent): ...`,
  `docs(vision): ...`, `refactor`, `test`, `chore`, `ci`, `build`. Scope = the lane or module.
- Subject in the imperative, under 72 characters. Add a body when the *why* is not obvious.
- Work done with an AI agent keeps its `Co-Authored-By:` trailer, so the history shows humans and agents working
  together honestly.
- **This repo is public.** Never commit secrets, `.env`, database files or `node_modules`, and no personal data
  about anyone: no emails, phone numbers, account ids, device names, local paths, Wi-Fi details or photo EXIF. Team
  members appear by name only. Seed data stays fictional (the public-info example cards in `domains/examples.py` are the one, clearly marked exception). CI scans every push with gitleaks; if it flags something,
  rotate the key first, then fix the commit.

## Pull requests

- One topic per PR, ideally under 400 changed lines. Fill in the template.
- CI must be green: backend lint, format and tests (`ruff`, `pytest`), frontend format, tests and build
  (`prettier`, `vitest`, `tsc`, `vite build`).
- One review from another person before merging, then merge with a merge commit. Never squash: the jury reads the
  small commits.
- Stack nothing: every PR targets `main`. A PR merged into another feature branch never reaches `main`.
- `main` deploys to GitHub Pages and Render on every merge. Don't merge in the last 15 minutes before a demo.

## Strings and languages

The web app speaks English, German, French and Italian. **Every change ships in all four, in the same PR**, whether
a person or an AI writes it. No user-facing text goes into a component directly. `npm test` fails when a key is
missing or empty in one language, when a longer text is English copied into another language, or when a component
has text outside `t()` (`src/i18n/hardcoded.test.ts`).

1. Add the key and the English text to `code/frontend/src/i18n/en.ts`, in the section of its page
   (`"owner.publish": "Sign and publish"`). Placeholders go in braces: `"Book for {price}"`.
2. Add the same key to `de.ts`, `fr.ts` and `it.ts`. The build fails until all three have it.
3. In the component: `const { t, intl } = useI18n();` then `t("owner.publish")` or `t("card.bookFor", { price })`.
   Format dates and money with `lib/format.ts` and `intl`, never by hand.

Text the backend writes itself (agent replies, the rule-check second opinion) lives in
`code/backend/app/replies.py`, also in all four; `tests/test_languages.py` checks it.

Formal register (Sie, vous, Lei), Swiss spelling (ss, not ß), CHF. Business data from a card (names, features,
policies) is the owner's text and is not translated. Voice and names of the features: [BRAND.md](documentation/BRAND.md).

## Tests first

Every change starts with a test that fails without it: a bug gets a test that reproduces it, a feature gets a test
that describes it, then the code that makes them pass. Commit the test with the change, in the same working step.

- Backend: `code/backend/tests/`, pytest. Test through the API (`client`) or MCP (`Client(server)`) where a
  traveller or an agent would; call the module directly for pure logic. Model calls are faked (see the OpenAI loop
  test), so the suite runs with no key and no network.
- Frontend: `*.test.tsx` next to the component, Vitest and Testing Library. Test what a person sees and clicks,
  with `api.ts` mocked (`vi.spyOn(api, ...)`); no test talks to a backend. `TravellerAgent.test.tsx` is the example.
- Keep the promises tested: signatures, one-time approvals, consent, no free text in logs, the offline fallback.
  A PR that weakens one of them needs a test that shows the new behaviour, and a line in `SECURITY.md`.
- Never skip, loosen or delete a test to get CI green. Fix the code, or explain in the PR why the test was wrong.

## Checks to run before you push

```bash
cd code/backend && ruff check . && ruff format --check . && pytest -q
cd code/frontend && npm run format:check && npm test && npm run build
```

Fix formatting with `ruff format .` and `npm run format`. Every public Python function and class gets a docstring
(ruff enforces it); comments explain *why*, not *what*.

## Ground rules

- All seed businesses and people are fictional, except the example cards for real businesses in
  `domains/examples.py`: public company information only, marked unclaimed, no people. No real personal data in the repo, tests or demos.
- Treat anything a business or a user writes as data, never as instructions to an agent.
- Keep the demo working offline (no API key) as well as with Claude.
- Anything that spends money, edits a business or wipes data goes through `guard.py`. Read `SECURITY.md` first.
