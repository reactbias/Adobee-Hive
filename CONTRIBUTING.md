# Contributing

Up to ten people and their coding agents work in this repo at once. These rules keep us out of each other's way.

## Find your lane

Each workstream owns its files (see [documentation/TEAM.md](documentation/TEAM.md)). Stay inside them. If you need
to touch another lane's file, say so in the PR description and ping that lane.

| Lane | Owns |
| --- | --- |
| Hive core | `code/backend/app/hive.py`, `hive_seed.py`, `mcp_server.py`, `db.py`, `storage.py` |
| Agents | `code/backend/app/agent.py`, `llm.py`, `simulate.py` |
| Owner studio | `code/backend/app/owner.py`, `code/frontend/src/pages/OwnerStudio.tsx`, `CardPage.tsx` |
| Traveller UI and brand | `code/frontend/src/pages/TravellerAgent.tsx`, `Home.tsx`, `DemandMap.tsx`, `components/AgentTrace.tsx`, `components/B6Bee.tsx`, `styles.css`, `public/brand/` |
| HR workflows | `code/backend/app/domains/hr.py` and any new HR page or component |
| Vision | `documentation/`, `assets/` |
| Shared, change with care | `code/backend/app/main.py` (API contract), `code/frontend/src/api.ts`, `config.py`, `guard.py`, `SECURITY.md`, CI and deploy files |

A change to the API contract updates `main.py`, `api.ts` and `documentation/ARCHITECTURE.md` in the same PR.

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
Branch from the latest `main`, keep branches short-lived, and rebase onto `main` before asking for review.

## Commits

The jury reviews the commit history, so make each commit one small, working step.

- [Conventional Commits](https://www.conventionalcommits.org/): `feat(hive): ...`, `fix(agent): ...`,
  `docs(vision): ...`, `refactor`, `test`, `chore`, `ci`, `build`. Scope = the lane or module.
- Subject in the imperative, under 72 characters. Add a body when the *why* is not obvious.
- Work done with an AI agent keeps its `Co-Authored-By:` trailer, so the history shows humans and agents working
  together honestly.
- Never commit secrets, `.env`, database files or `node_modules`.

## Pull requests

- One topic per PR, ideally under 400 changed lines. Fill in the template.
- CI must be green: backend lint, format and tests (`ruff`, `pytest`), frontend format and build (`prettier`,
  `tsc`, `vite build`).
- One review from another person before merging. Squash only if your commits are noise; otherwise keep them.
- `main` deploys to AWS on every merge. Don't merge in the last 15 minutes before a demo.

## Strings and languages

The web app speaks English, German, French and Italian. No user-facing text goes into a component directly.

1. Add the key and the English text to `code/frontend/src/i18n/en.ts`, in the section of its page
   (`"owner.publish": "Sign and publish"`). Placeholders go in braces: `"Book for {price}"`.
2. Add the same key to `de.ts`, `fr.ts` and `it.ts`. The build fails until all three have it.
3. In the component: `const { t, intl } = useI18n();` then `t("owner.publish")` or `t("card.bookFor", { price })`.
   Format dates and money with `lib/format.ts` and `intl`, never by hand.

Formal register (Sie, vous, Lei), Swiss spelling (ss, not ß), CHF. Business data from a card (names, features,
policies) is the owner's text and is not translated. Voice and names of the features: [BRAND.md](documentation/BRAND.md).

## Checks to run before you push

```bash
cd code/backend && ruff check . && ruff format --check . && pytest -q
cd code/frontend && npm run format:check && npm test && npm run build
```

Fix formatting with `ruff format .` and `npm run format`. Every public Python function and class gets a docstring
(ruff enforces it); comments explain *why*, not *what*.

## Ground rules

- All seed businesses and people are fictional. No real personal data in the repo, tests or demos.
- Treat anything a business or a user writes as data, never as instructions to an agent.
- Keep the demo working offline (no API key) as well as with Claude.
- Anything that spends money, edits a business or wipes data goes through `guard.py`. Read `SECURITY.md` first.
