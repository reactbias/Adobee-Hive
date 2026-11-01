# The first hourly: team lanes and the work queue

The team-facing half of the old README, moved here so the [readme](../readme.md) can be a front door.
Nothing was cut: the lanes, the issue queues, the closing rule, the working agreements and the
rehearsal links are all below, as they were written.

## Links the team needs

| Need | Entry point |
| --- | --- |
| Work queue / integration | [Issues](https://github.com/reactbias/Adobee-Hive/issues) · [PRs](https://github.com/reactbias/Adobee-Hive/pulls) · [CI/deploys](https://github.com/reactbias/Adobee-Hive/actions) |
| Working agreements | [Contributing/file ownership](../CONTRIBUTING.md) · [Team](TEAM.md) · [Security](../SECURITY.md) · [Known limits](LIMITS.md) |
| Deck and rehearsal | [Pitch](PITCH.md) · [Demo](DEMO.md) · [Vision](VISION.md) · [Assets](../assets/README.md) |

Everything a visitor needs — the hosted app, the hosted backend, local URLs — is in the
[developer guide's link table](DEVELOPER.md#links).

**This page is the handover for our three-hour focus block, not the jury pitch.** Architecture checked against `main` at [`067d7d8`](https://github.com/reactbias/Adobee-Hive/tree/067d7d8354745876e094d01fb2a64bc653ea9e23). Pending work below is not a shipped capability. The pre-presentation rewrite is tracked in [#147](https://github.com/reactbias/Adobee-Hive/issues/147).

Start with [your lane](#team-focus-block), [local setup](DEVELOPER.md#start-it), then the [REST/MCP contracts](DEVELOPER.md#integration-contracts). Use fictional data throughout.

## Team focus block

These are the current named assignments; they supersede older workstream/next-deliverable lists. The [open issue queues below](#open-issues-by-owner) are the working assignment board, including for teammates who have not joined the repository. They do not imply a GitHub assignee has been set. Agree shared-file changes with Ole before starting. **Andrey's two lanes are alternatives, not two simultaneous commitments.**

| Who | Focus | Starting point and handover |
| --- | --- | --- |
| **Tobi (`reactbias`)** | UI and the end-to-end browser experience | `code/frontend/src/App.tsx`, `pages/TravellerAgent.tsx`, `panels/`, `components/`, `api.ts`, `i18n/`. Keep selected-hub status, discovery, Details, explicit approval and receipt usable. Coordinate API changes with Ole; pair with Andrey on the hotel-MCP alternative below. |
| **Andrey (`dodonov-dev`)** | Support fuzzy search over the cards' JSON; **alternatively**, help Tobi handle a hotel that advertises its own booking MCP in a discovered folder | Search: `app/hive.py`, `app/semantic.py`, [Search API](SEARCH_API.md), `tools/eval_answer_key.py`, `tools/eval_search.py`. Work with the existing offline matcher and score breakdown. Hotel-MCP option: [provider handoff](#a-hotel-advertises-its-own-booking-mcp), with Tobi and Ole; agree a real provider contract before changing routing. |
| **Saad + Emily (`asukuna`)** | A coherent slide deck, with a complete understanding of the actual architecture | Follow the [architecture](DEVELOPER.md#architecture) and [journeys](DEVELOPER.md#the-two-journeys), then `documentation/PITCH.md`, `DEMO.md`, `VISION.md`, `assets/`. Show the implemented system separately from future vision; check each technical claim with its lane owner. |
| **Felix + baker** | Tests, measured performance gains, stability and fixes for existing issues — **nonbreaking changes only** | `code/backend/tests/`, frontend `*.test.ts(x)`, `code/backend/tools/`. Pick a bounded issue with Ole, reproduce on current `main`, add a behavior regression, measure before/after for performance work. Keep public schemas, signatures, consent/approval gates and offline behavior intact; no broad refactor or dependency/DB cutover. See [stability work](#stability-work-without-breaking-the-demo). |
| **Aneeq + Sarder + Shayan** | A separate system that finds CVs in folders; learn the hub MCP and integrate discovery/access | Start with [MCP](DEVELOPER.md#mcp-for-an-external-agent), the [Folder API walkthrough](FOLDER_API.md) and [your issue queue](#cv-team). Distinguish card metadata from file bytes. Use fictional data, link credentials and explicit grants; coordinate backend dependencies with Ole rather than inventing folder MCP tools. Bring back one candidate → permitted CV → extraction result with source attribution and a clear blocked/denied outcome. |
| **Ole (`busssard`)** | Backend MCP/REST API. Not a gate: the contracts are documented, read them first | `code/backend/app/main.py`, `mcp_server.py`, `domains/`, `config.py`, `guard.py`, storage and folder integration. Own shared-contract decisions, backend availability, integration order and rehearsal. Unblock other lanes without changing their interfaces underneath them. |

`app/...` above means `code/backend/app/...`. Coordinate edits to `main.py`, `mcp_server.py`, `api.ts`, `hive.py`, `config.py`, auth and deployment files; those are shared boundaries, not independent sandboxes.

**How to use the block:** get a clean run and agree one deliverable per lane first; spend the middle on small tested changes; reserve the end for integration and rehearsal, not new architecture. Hand over the branch/PR, exact entry command, changed contract, observed result and remaining blocker. Do not merge another lane's unfinished work merely to make a demo appear complete.

### Open issues by owner

**Pick one focus item, not the whole queue.** These are lane leads and coordination responsibilities; shared backend/UI work needs both owners. **Roadmap** items are parked planning work, not commitments for this three-hour block. Older reports may already be partly fixed: check acceptance criteria against current `main` before implementing again.

**Closing rule:** whoever closes an issue must remove its task/link from this README, including other stale open-work references, and update any affected blocker/limitation text. Include that cleanup in the closing PR; if closing manually, merge the README cleanup first. Do not leave completed work in an open queue. Each linked issue carries the same closure reminder.

#### Tobi

- **Focus:** [#139 Details/reach/connect bug list](https://github.com/reactbias/Adobee-Hive/issues/139) — items 1 and 2 are done (#157); item 3 is partly done and the rest is #182, #173 and #128. [#171 retain the link credential and browse permitted folder files](https://github.com/reactbias/Adobee-Hive/issues/171) — PR open.
- **Auth boundary — the contract is [SECURITY.md](../SECURITY.md), which names every credential and what it does *not* prove:** [#106 keep saved credentials scoped to the issuing hub](https://github.com/reactbias/Adobee-Hive/issues/106).
- **Search controls:** [#132 kind and offers/needs selection](https://github.com/reactbias/Adobee-Hive/issues/132), [#133 per-search rulesets](https://github.com/reactbias/Adobee-Hive/issues/133), [#134 standing requests/offers in the browser](https://github.com/reactbias/Adobee-Hive/issues/134).
- **Introduction/calibration UI follow-up:** [#165 visible hub calibration](https://github.com/reactbias/Adobee-Hive/issues/165) — PR open.
- **UI roadmap — the backend contract is [SEARCH_API.md](SEARCH_API.md):** [#166 interaction/search history](https://github.com/reactbias/Adobee-Hive/issues/166) (browser half has a PR), [#167 folder requests and demand visibility](https://github.com/reactbias/Adobee-Hive/issues/167), [#168 owner-visible agent/folder-read history](https://github.com/reactbias/Adobee-Hive/issues/168), [#169 booking/introduction notifications](https://github.com/reactbias/Adobee-Hive/issues/169) (PR open), [#170 inbox/contact experience](https://github.com/reactbias/Adobee-Hive/issues/170). The half of #166 that is left is a person's own past introductions, which needs a `state=` or `include=` filter on `GET /api/hub/connections`.
- **Owner/onboarding roadmap — see [FOLDERS.md](FOLDERS.md) and the `hive_owner_*` tools in [SEARCH_API.md](SEARCH_API.md):** [#174 rescan a folder and regenerate its Card](https://github.com/reactbias/Adobee-Hive/issues/174), [#175 folder-selection and onboarding clarity](https://github.com/reactbias/Adobee-Hive/issues/175), [#176 sign-in/accounts](https://github.com/reactbias/Adobee-Hive/issues/176), [#178 per-person API-key experience](https://github.com/reactbias/Adobee-Hive/issues/178), [#179 admin settings/read boundaries](https://github.com/reactbias/Adobee-Hive/issues/179), [#180 reporting/moderation decisions](https://github.com/reactbias/Adobee-Hive/issues/180), [#181 index-copying policy and visibility](https://github.com/reactbias/Adobee-Hive/issues/181).

#### Andrey

- **Alternative, paired with Tobi:** [#173 discover and safely hand off to an owner-supplied hotel MCP](https://github.com/reactbias/Adobee-Hive/issues/173). Agree the real provider contract and approval gate before implementation; see [provider handoff](#a-hotel-advertises-its-own-booking-mcp).

#### Saad and Emily

- **Deck/video:** [#73 presentation structure and video](https://github.com/reactbias/Adobee-Hive/issues/73).
- **Presentation cutover:** [#147 jury-facing README, final architecture visual and verified try-it path](https://github.com/reactbias/Adobee-Hive/issues/147). Saad/Emily align the story and slides; Ole coordinates the final runnable backend and publication.

#### Felix and baker

- **Nonbreaking test/performance focus:** [#154 oversized MCP discovery payloads](https://github.com/reactbias/Adobee-Hive/issues/154).
- **Correctness fixes — read [SECURITY.md](../SECURITY.md) before touching booking or auth:** [#104 approved price/cancellation terms](https://github.com/reactbias/Adobee-Hive/issues/104), [#112 federation query deadline](https://github.com/reactbias/Adobee-Hive/issues/112).
- **Contract follow-up, not a silent semantics change:** [#122 booking-backed reviews versus completed stays](https://github.com/reactbias/Adobee-Hive/issues/122). The wording and `verified_stay: false` are done; what is left is deciding what proves a completed stay and who may issue it.

#### CV team

**Aneeq, Sarder and Shayan own the CV client/extraction work.** The backend it talks to is documented: [SEARCH_API.md](SEARCH_API.md) for the Card and the search endpoints, [FOLDER_API.md](FOLDER_API.md) for reading a linked folder. These links are not an instruction to build a second hub or to finish the whole HR roadmap.

- **CV slice:** [#127 CV import and person-owned HR flow](https://github.com/reactbias/Adobee-Hive/issues/127). Keep the broader profile/consent workflow coordinated with Ole.
- **Backend dependency, contract in [SEARCH_API.md](SEARCH_API.md):** [#150 retrieve a person Card found on another hub](https://github.com/reactbias/Adobee-Hive/issues/150); preserve the discovered origin and inline signed Card.
- **Later exchange/deployment dependencies:** [#128 private-context exchange beyond link metadata](https://github.com/reactbias/Adobee-Hive/issues/128), [#182 a folder service on the person's own machine](https://github.com/reactbias/Adobee-Hive/issues/182). The current [Folder API](FOLDER_API.md) serves permitted files on the hub's disk; it does not solve cross-machine sync.

#### Ole (`busssard`)

Most of this block shipped. **Done:** #72, #105, #109, #164, the folder read surface, cross-hub
connect, the owner's MCP tools, the public readme.

**In flight, one PR each:** #107, #108, #110, #111, #121, #155, #156, #158, #159.

**Not promised:** #123, #124, #125, #126, #129, #130, #131, #135, #136, #137. #170 and #180 are
decisions before they are work — an inbox or a TOS scanner commits the hub to hosting messages or
judging content, and `folders.py` and `waiting.py` promise the opposite in words a jury could read.

**Nothing here gates anyone else.** The contracts are written down: [SEARCH_API.md](SEARCH_API.md),
[FOLDER_API.md](FOLDER_API.md), [FOLDERS.md](FOLDERS.md), [SECURITY.md](../SECURITY.md),
[ARCHITECTURE.md](ARCHITECTURE.md), and [LIMITS.md](LIMITS.md) for what is honestly missing. Read
those first; open an issue if one is wrong. Several were wrong this week and were fixed by people
who checked rather than asked.

## Notes for the deck lane

For Saad/Emily: the supplied [architecture diagram](diagrams/05-current-architecture.svg) is a working sketch, only reachable on the team network. Its “browser never passes radius” warning is stale, its calibration/ranking relationship is not implemented, and its folder/API status must be rechecked after merges. Use the version-controlled map above for this handover; refresh the presentation visual under [#147](https://github.com/reactbias/Adobee-Hive/issues/147).

## Operating the shared LAN stack

**Whoever is hosting the shared stack starts and stops it.** `lan.sh` now refuses to touch servers belonging to another checkout and refuses to start on ports already held, so a branch worktree can no longer take the shared demo down by accident ([DEVELOPER.md](DEVELOPER.md)). `lan.sh up` can reclaim its configured app port; choose a free one, not another team's live port. Do not reset or reseed the presentation instance as a test. The older warning in `SEARCH_API.md` about `down` sweeping every worktree is historical: current cleanup checks process working directories, but the shared instance is still not your sandbox.

## Search and UI notes for the API consumers

For Andrey and Tobi:

- `offers`/`needs` are the market-side index; `kind` is an optional filter. Use `looking_for=offers|needs|any` deliberately. Do not make every service or CV search a hotel search.
- Hard constraints determine eligibility. An entity the ask earned nothing from is left out, and `matched: 0` means nothing answered; `include_irrelevant=true` returns the full ranking. Reputation points do not prove a content match, so inspect `score_breakdown`, `why` and `excluded`.
- REST recognizes explicit room requests and reuses the stay parser; explicit parameters win. MCP uses its explicit tool parameters, not that REST text-normalization step. Supply structured dates, guests, budget and features when their correctness matters.
- `radius=0` is local; positive radius searches configured peers, up to three hops. REST additionally exposes `budget_ms` and `seen`. The presenter reach control already passes radius; broader browser search controls remain incomplete.
- A local match is a summary: fetch its Card by ID. A federated match includes its signed `card`; do not fetch a remote ID from the answering hub's local card endpoint. Show origin-first `provenance.path` and retain `origin_url`/source identity. The remaining browser handover is [#172](https://github.com/reactbias/Adobee-Hive/issues/172): send that signed Card with a cross-hub introduction.
- The full [Search API handover](SEARCH_API.md) has payloads and fixtures, but some recorded startup/routing warnings predate subsequent fixes. Current code and the running schema win over historical observations.

## CV and folder integration

Aneeq, Sarder and Shayan can work independently on extraction. The hub access contract is [FOLDER_API.md](FOLDER_API.md) — a link opens the manifest, a per-path grant opens the bytes; read it rather than asking.

| Layer | Available on this main snapshot | Not implied |
| --- | --- | --- |
| Card discovery | REST/MCP search and signed Card `structure` metadata | CV bytes or a ready-made CV parser |
| Introduction | `hub_connect` / `POST /api/hub/connect`: `requester`, `entity_id`, optional `target_hub`/`via_hub`; returns connection/link state and inline `folder` manifest | Authenticated real-person consent or automatic remote-hub routing |
| Local folder primitives | `app/folders.py`: handles, links, manifests, grants, permission checks and server-local reads | Encryption or cross-machine sync |
| Development file access | Separate `tools/serve_folders.py` HTTP listing/downloads of fictional allowed files | An authenticated private folder service |
| Hub REST read surface | [Folder API](FOLDER_API.md): link-bound bearer credentials for manifest/file/grant/revoke routes; remaining driving scope in [#116](https://github.com/reactbias/Adobee-Hive/issues/116) | Folder MCP tools, individual owner accounts or cross-machine file exchange |

A `public` introduction opens immediately; a `confirm` one waits. A link reveals additional manifest metadata, **not blanket byte access**; nonpublic reads need a separate grant in the local implementation. Current requester strings and confirmation routes do not establish caller ownership. Do not describe them as production authentication. The [folder plan](FOLDERS.md) is merged design documentation, not proof its proposed endpoints are available.

### Start extraction now, with a fictional CV

From `code/backend`, venv active, in its own terminal:

```bash
python tools/serve_folders.py --host 127.0.0.1 --port 8600 --vault jonas-brun
```

Then inspect and download:

```bash
curl -fsS http://127.0.0.1:8600/jonas-brun/
curl -fsS http://127.0.0.1:8600/jonas-brun/cv.pdf -o /tmp/hive-fictional-cv.pdf
```

The file is a real PDF containing fictional test material. The fixture deliberately serves `public` **and `public-summary` anonymously**, including this CV; `--strict` restricts it to `public` and would exclude this CV. It is for development, **not a privacy boundary or a way to expose real folders**. The source corpus and field/visibility examples are in [testdata](../testdata/README.md) and [the fixture guide](SEARCH_API.md#the-three-folder-fixture).

For another laptop, the fixture host must explicitly bind an agreed LAN interface (`--host 0.0.0.0`) and share its actual address/port. `localhost` on a teammate's laptop is not Ole's server. Coordinate with Ole; keep extracted personal data and secrets out of git, prompts and public logs.

### A hotel advertises its own booking MCP

**Andrey's alternative, with Tobi.** Main can carry an arbitrary contact channel such as `contact.mcp` (the folder seeder reads `contact.md`), but no current fixture advertises a hotel MCP. Neither the folder manifest nor the booking agent implements automatic folder-to-provider discovery. There is no agreed descriptor-file schema to assume.

The handover to agree is: find the advertisement → establish the hotel's/provider's identity and permitted endpoint → inspect its real transport/auth/tool schemas → map the discovered hotel/room to provider IDs → display an offer → obtain explicit approval → book through that same provider. Finding a URL is data, **not authorization to connect or book**.

The existing planner expects Hive-shaped discovery/cards/availability. **Only the exact `hive_book` tool name is held for approval today**; a different provider's mutating tool name is not automatically protected. Do not simply add an arbitrary hotel's MCP to `HIVE_MCP_URLS` and assume compatibility or consent. Preserve server-side source binding through approval and reject missing/untrusted providers instead of falling back to another hotel. This is proposed integration work, not a shipped workflow.

## Stability work without breaking the demo

Felix and baker: choose a small issue from your queue and check the current revision before fixing it. An open issue can describe code that has since changed; search normalization, source-bound approval and backend-status fixes are already merged even where old issues remain open.

Use the [Felix and baker issue queue](#felix-and-baker) above as the single task list. Fixes touching booking or auth: read [SECURITY.md](../SECURITY.md) first, then open a PR rather than silently changing the contract; do not pick an already completed issue from an old prose list.

**Nonbreaking means:** preserve request/response shapes, signed canonical data, explicit approvals, origin verification, withheld-data rules and the no-key path. Keep performance work measurable on the same fictional workload; do not trade away relevance or safety checks for speed. No test skipping, raised timeouts to hide races, swallowed errors or synthetic success fallbacks. For a bug, keep a behavior regression and exercise the actual API/MCP/UI path after the fix.

From the repository root, with the backend venv active and frontend dependencies installed:

```bash
( cd code/backend && python -m ruff check . && python -m ruff format --check . && python -m pytest -q )
( cd code/frontend && npm run format:check && npm test && npm run build )
```

For federation/trust/access-rule changes also run the existing mutation gate from `code/backend`: `python tools/mutate.py`. Search measurements: `python tools/eval_answer_key.py` and `python tools/eval_search.py`. These are commands to run for your change, not a claim that the current branch is green. CI's snapshot round-trip test uses a throwaway Postgres via `TEST_DATABASE_URL`; do not point it at the live database. Use the existing test fixtures and keep checks deterministic and isolated.

## Continuing work and presentation cutover

- Branch from latest `main`, keep small Conventional Commits and one topic per PR. Share the issue/PR and changed contract with the affected lane. [CONTRIBUTING.md](../CONTRIBUTING.md) has the full workflow.
- New browser strings ship in EN, DE (Swiss), FR and IT in the same change. `api.ts` and backend schema/documentation move together when the contract changes. Preserve the no-key rehearsal path.
- **Do not claim yet:** private cross-machine context exchange, arbitrary hotel-MCP handoff, independent business negotiation, owner-held publishing keys, verified real-world identity, verified completed stays, payments or production-grade ownership/consent. The code supports a prototype; [known limits](LIMITS.md) and the open issues describe its boundaries.
- Before the jury/presentation, execute [#147](https://github.com/reactbias/Adobee-Hive/issues/147): check final `main` and deployments, update the architecture/deck, rehearse the exact try-it path, then make the README visitor-first while retaining this contributor handover through linked developer documentation.
