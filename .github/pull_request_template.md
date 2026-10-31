## What and why

<!-- One topic. What changes for a traveller, an owner or an agent? -->

## Lane

<!-- Hive core / Agents / Owner studio / Traveller UI and brand / Vision. Name any file outside your lane. -->

## How I checked it

- [ ] `ruff check . && ruff format --check . && pytest -q` in `code/backend`
- [ ] `npm run format:check && npm test && npm run build` in `code/frontend`
- [ ] Still works with no API key (offline mode)
- [ ] Anything that spends money, edits a card or wipes data goes through `guard.py`
- [ ] API contract changed? `main.py`, `api.ts` and `documentation/ARCHITECTURE.md` updated together

## Screenshots or demo notes

