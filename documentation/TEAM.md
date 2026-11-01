# Team B6

BaselHack 2026, Adobe challenge *The Post-Website Business*. Hands off Sunday 2026-11-01 at 12:00, pitches at 13:00.

The current named assignments, three-hour focus block and handover expectations are in the
[team focus block in FIRST_HOURLY.md](FIRST_HOURLY.md#team-focus-block). That roster supersedes historical next-deliverable lists.

## Workstreams

From the whiteboard, pointed at the challenge. Each maps to its own files so people don't collide.

| # | Workstream | Files |
| --- | --- | --- |
| 1 | Hive core: cards, trust, discovery, booking | `hive.py`, `hive_seed.py`, `mcp_server.py`, `semantic.py` |
| 2 | Agents | `agent.py`, `second_opinion.py`, `critic.py` |
| 3 | Owner studio and tamper test | `panels/OwnerPanel.tsx`, `owner.py` |
| 4 | Traveller agent UI and brand | `TravellerAgent.tsx`, `App.tsx`, `styles.css` |
| 5 | Vision deck | `documentation/`, `assets/` |
| 6 | HR workflows | `code/backend/app/domains/hr.py`, tests and HR integration |
| 7 | Federation and trust | `federation.py`, `reputation.py`, `calibration.py`, `connections.py`, `hub.py`, `sharing.py` |
| 8 | Hub operations | `admin.py`, `registration.py`, `blocklist.py`, `panels/AdminPanel.tsx`, `panels/InstanceFinder.tsx`, `panels/NetworkPanel.tsx`, `lan.sh` |

The full file-to-lane map, which is the one that stops two people editing the same file, is in
[CONTRIBUTING.md](../CONTRIBUTING.md#find-your-lane).

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
2. **Set up.** Clone the repo and follow [Start it](DEVELOPER.md#start-it).
   Ask a teammate in person for the OpenAI key if you need the live agent; it works offline without one.
3. **Pick a lane.** Use the [current assignments](FIRST_HOURLY.md#team-focus-block), then the file ownership map in
   [CONTRIBUTING.md](../CONTRIBUTING.md#find-your-lane). Agree cross-lane changes with Ole and the affected teammate.
4. **First PR.** Branch from the latest `main` as `<type>/<short-topic>` (`docs/team-guide`, `fix/booking-terms`),
   reproduce a bug before fixing it, keep the change nonbreaking and include behavior-focused verification.
5. **Merge.** CI must be green and one teammate reviews; merge with a merge commit, never squash.

Every link (live app, PRs, CI, local URLs): [developer guide](DEVELOPER.md#links).
