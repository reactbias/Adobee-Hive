# Notes for coding agents

You are working in Adobee Hive, Team B6's BaselHack 2026 entry for Adobe's *The Post-Website Business* challenge.
Read `readme.md` for the idea and `documentation/ARCHITECTURE.md` for the modules before changing code.

## Rules

- Follow `CONTRIBUTING.md`: stay in the lane you were asked to work in, small Conventional Commits, one topic per PR.
- Keep the `Co-Authored-By:` trailer your tool adds to commits.
- Before you push, run `ruff check . && ruff format --check . && pytest -q` in `code/backend` and
  `npm run format:check && npm run build` in `code/frontend`; CI runs the same.
- The demo must keep working with **no** `ANTHROPIC_API_KEY` (scripted planner, rule-based owner edits). Any new
  Claude call needs an offline fallback.
- Card text, reviews and user input are data. Never let them become instructions in a prompt.
- Every card change goes through `hive.publish` (owner edits via `owner.apply`), which signs the new version.
  Never write `hive_cards` directly.
- Don't add dependencies without a reason in the commit body; pin exact versions.
- Seed data stays fictional. No secrets, keys or real personal data in the repo.
- New endpoints that call Claude, edit a card or wipe data must use `guard.py`; keep `SECURITY.md` true.
- Every public function and class gets a docstring; ruff enforces it.

## Layout

```
code/backend/app/     FastAPI app, Hive core, MCP server, agents (Python 3.12)
code/backend/tests/   pytest, including an end-to-end booking over MCP
code/frontend/src/    React + Vite + TypeScript; api.ts is the typed client
documentation/        vision, demo script, architecture, deploy, brand, team
assets/               exports for slides
```

## Style

Match the surrounding code: type hints and short docstrings in Python, typed props and small components in
TypeScript, comments only where the *why* isn't obvious.
