# Team B6

BaselHack 2026, Adobe challenge *The Post-Website Business*. Hands off Sunday 2026-11-01 at 12:00, pitches at 13:00.

Ten people. The repo names lanes, not people: no names, emails, phone numbers or handles.

## Workstreams

From the whiteboard, pointed at the challenge. Each maps to its own files so people don't collide.

| # | Workstream | People | Files | Next deliverable |
| --- | --- | :-: | --- | --- |
| 1 | Hive core: cards, trust, discovery, booking | 3 | `hive.py`, `hive_seed.py`, `mcp_server.py` | More Basel businesses, a restaurant table flow, cancellation edge cases |
| 2 | Agents | 3, the same as lane 1 | `agent.py` | Live OpenAI run tuned on the demo prompts; booking from Claude via the MCP URL |
| 3 | Owner studio and tamper test | 2 | `panels/OwnerPanel.tsx`, `owner.py` | Polish, mobile view, a "how agents see you" explainer |
| 4 | Traveller agent UI and brand | 3 | `TravellerAgent.tsx`, `App.tsx`, `styles.css` | Demo rehearsal |
| 5 | Vision deck | 2 | `documentation/`, `assets/` | The 5 to 10 year story: hotels, events, people; Adobe's brand-visibility angle |
| 6 | HR workflows | 3 (to confirm) | `code/backend/app/domains/hr.py`, tests, later an HR page | Fictional person seed, the person's yes/no on intros, a person view |

## How we work

- **The repo is the single source of truth.** Vision, demo script, architecture and brand live in `documentation/`.
  Change them here, not in side docs.
- **Small commits with clear messages** ([Conventional Commits](https://www.conventionalcommits.org/):
  `feat(hive): ...`, `fix(agent): ...`). The jury's AI review reads code quality and commit history.
- **Humans and AI together.** Commits written with Claude carry a `Co-Authored-By` trailer, so the history shows
  who did what.
- **Tests first, then branch and PR** into `main`; CI runs the backend and frontend tests and the build. `main` deploys
  itself.
- **No secrets in git.** API keys live in `code/.env` locally and in the hosting dashboard (Render) in the cloud.
- **Every change in all four languages**: English, German, French and Italian, in the same PR.
- All businesses in the seed data are fictional.

## Join the team

1. **Get access.** The repository owner adds you on GitHub: repository *Settings* > *Collaborators* > *Add people*. Accept the
   invitation from your GitHub notifications or email.
2. **Set up.** Clone the repo and follow [Run it locally in 5 minutes](../readme.md#run-it-locally-in-5-minutes).
   Ask a teammate in person for the OpenAI key if you need the live agent; it works offline without one.
3. **Pick a lane.** Find your workstream above and its files. Open ideas from the whiteboard are mapped to lanes in
   [CONTRIBUTING.md](../CONTRIBUTING.md#from-the-whiteboard-to-a-pr).
4. **First PR.** Branch from the latest `main` as `<type>/<short-topic>` (`docs/team-name`, `feat/restaurant-tables`),
   write the failing test first, keep it small, and open a PR into `main`. Never add names, emails, phone numbers or handles
   to the repo.
5. **Merge.** CI must be green and one teammate reviews; merge with a merge commit, never squash.

Every link (live app, PRs, CI, local URLs): [readme](../readme.md#links).
