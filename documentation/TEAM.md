# Team B6

BaselHack 2026, Adobe challenge *The Post-Website Business*. Hands off Sunday 2026-11-01 at 12:00, pitches at 13:00.

10 people. We list workstreams, not names or skills; who works on what is settled in person.

## Workstreams

From the whiteboard, pointed at the challenge. Each maps to its own files so people don't collide.

| # | Workstream | Files | Next deliverable |
| --- | --- | --- | --- |
| 1 | Hive core: cards, trust, discovery, booking | `hive.py`, `hive_seed.py`, `mcp_server.py`, `semantic.py` | Wire `semantic.py` into `discover`, a restaurant table flow, cancellation edge cases |
| 2 | Agents | `agent.py`, `second_opinion.py`, `critic.py` | Live OpenAI run tuned on the demo prompts; booking from Claude via the MCP URL |
| 3 | Owner studio and tamper test | `panels/OwnerPanel.tsx`, `owner.py` | Polish, mobile view, a "how agents see you" explainer |
| 4 | Traveller agent UI and brand | `TravellerAgent.tsx`, `App.tsx`, `styles.css` | Demo rehearsal |
| 5 | Vision deck | `documentation/`, `assets/` | The 5 to 10 year story: hotels, events, people; Adobe's brand-visibility angle |
| 6 | HR workflows | `code/backend/app/domains/hr.py`, tests, later an HR page | Fictional person seed, a person view, the person's yes/no inside it |
| 7 | Federation and trust | `federation.py`, `reputation.py`, `calibration.py`, `connections.py`, `hub.py`, `sharing.py` | A second hub deployed, calibration as a rank factor |
| 8 | Hub operations | `admin.py`, `registration.py`, `blocklist.py`, `panels/AdminPanel.tsx`, `panels/InstanceFinder.tsx`, `panels/NetworkPanel.tsx`, `lan.sh` | Route the app at the Hive the finder picked; a credential on the admission queue |

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
2. **Set up.** Clone the repo and follow [Run it locally in 5 minutes](../readme.md#run-it-locally-in-5-minutes).
   Ask a teammate in person for the OpenAI key if you need the live agent; it works offline without one.
3. **Pick a lane.** Find your workstream above and its files. Open ideas from the whiteboard are mapped to lanes in
   [CONTRIBUTING.md](../CONTRIBUTING.md#from-the-whiteboard-to-a-pr).
4. **First PR.** Branch from the latest `main` as `<type>/<short-topic>` (`docs/team-name`, `feat/restaurant-tables`),
   write the failing test first, keep it small, and open a PR into `main`. Please don't add your name or skills to the
   docs: the team is counted, not listed.
5. **Merge.** CI must be green and one teammate reviews; merge with a merge commit, never squash.

Every link (live app, PRs, CI, local URLs): [readme](../readme.md#links).
