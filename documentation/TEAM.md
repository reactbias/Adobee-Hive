# Team B6

BaselHack 2026, Adobe challenge *The Post-Website Business*. Hands off Sunday 2026-11-01 at 12:00, pitches at 13:00.

Tobias Schäuble, Andrey Dodonov, Lezhi Chen, Ole Müller, Muhammad Saad Uddin, Felix Lüdin, Emily Schell,
Aneeq Ur Riyan Ahmed, Shayan Shashaani, Sarthak Biswas.

## Workstreams

From the whiteboard, pointed at the challenge. Each maps to its own files so people don't collide.

| # | Workstream | People | Files | Next deliverable |
| --- | --- | --- | --- | --- |
| 1 | Hive core: cards, trust, discovery, booking | Aneeq, Shayan, Sarthak | `hive.py`, `hive_seed.py`, `mcp_server.py` | More Basel businesses, a restaurant table flow, cancellation edge cases |
| 2 | Agents | Aneeq, Shayan, Sarthak | `agent.py` | Live Claude run tuned on the demo prompts; booking from Claude via the MCP URL |
| 3 | Owner studio and human card page | Ole, Lezhi | `OwnerStudio.tsx`, `CardPage.tsx`, `owner.py` | Polish, mobile view, a "how agents see you" explainer |
| 4 | Traveller agent UI and brand | Tobias, Felix, Andrey | `TravellerAgent.tsx`, `Home.tsx`, `styles.css` | Demo rehearsal, Mannin font |
| 5 | Vision deck | Emily, Saad | `documentation/`, `assets/` | The 5 to 10 year story: hotels, events, people; Adobe's brand-visibility angle |

## How we work

- **The repo is the single source of truth.** Vision, demo script, architecture and brand live in `documentation/`.
  Change them here, not in side docs.
- **Small commits with clear messages** ([Conventional Commits](https://www.conventionalcommits.org/):
  `feat(hive): ...`, `fix(agent): ...`). The jury's AI review reads code quality and commit history.
- **Humans and AI together.** Commits written with Claude carry a `Co-Authored-By` trailer, so the history shows
  who did what.
- **Branch and PR** into `main`; CI runs the backend tests and the frontend build. `main` deploys itself.
- **No secrets in git.** The Claude key lives in `.env` locally and in AWS Secrets Manager in the cloud.
- All businesses in the seed data are fictional.
