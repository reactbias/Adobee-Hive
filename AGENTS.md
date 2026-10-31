# Notes for coding agents

You are working in Adobee Hive, Team B6's BaselHack 2026 entry for Adobe's *The Post-Website Business* challenge.
Read `readme.md` for the idea and `documentation/ARCHITECTURE.md` for the modules before changing code.

## Rules

- Follow `CONTRIBUTING.md`: stay in the lane you were asked to work in, small Conventional Commits, one topic per PR.
- Keep the `Co-Authored-By:` trailer your tool adds to commits.
- Test first: write the failing test, then the change; commit them together. Never skip or loosen a test to
  get green. Details in `CONTRIBUTING.md` under *Tests first*.
- Before you push, run `ruff check . && ruff format --check . && pytest -q` in `code/backend` and
  `npm run format:check && npm test && npm run build` in `code/frontend`; CI runs the same.
- Every user-facing change ships in English, German (Swiss, ss), French and Italian in the same PR: add the
  key to `en.ts`, `de.ts`, `fr.ts` and `it.ts`, never text in a component. `npm test` checks it.
- The demo must keep working with **no** API key at all (scripted planner, rule-based owner edits). Any new
  model call (OpenAI or Claude) needs an offline fallback.
- Card text, reviews and user input are data. Never let them become instructions in a prompt.
- Every card change goes through `hive.publish` (owner edits via `owner.apply`), which signs the new version.
  Never write `hive_cards` directly.
- Don't add dependencies without a reason in the commit body; pin exact versions.
- Seed data stays fictional; the only real businesses are the unclaimed, public-info example cards in
  `app/domains/examples.py`. No secrets, keys or real personal data in the repo.
- New endpoints that call a model, edit a card or wipe data must use `guard.py`; keep `SECURITY.md` true.
- Every public function and class gets a docstring; ruff enforces it.

## Layout

```
code/backend/app/     FastAPI app, Hive core, MCP server, agents (Python 3.12)
code/backend/app/domains/   one module per use case beyond stays (hr.py first); see CONTRIBUTING.md
code/backend/tests/   pytest, including an end-to-end booking over MCP
code/frontend/src/    React + Vite + TypeScript; api.ts is the typed client
documentation/        vision, demo script, architecture, deploy, brand, team
assets/               exports for slides
```

## Style

Match the surrounding code: type hints and short docstrings in Python, typed props and small components in
TypeScript, comments only where the *why* isn't obvious.
