# Architecture

One FastAPI backend serves the web app over REST and agents over MCP. Both read the same signed Hive cards in
DuckDB, kept across redeploys as a Postgres snapshot. A model (OpenAI `gpt-5-mini` by default, Claude as an
alternative, see `LLM_PROVIDER`) is called by your agent, the verifier, the relevance check, the scout and owner
edits. Without a key, offline paths do all of them.

Pictures of the hosting, a booking from question to receipt, a question about any business and the data path:
[DIAGRAMS.md](DIAGRAMS.md).

## Modules (`code/backend/app`)

| File | Responsibility |
| --- | --- |
| `hive.py` | Hive cards, Ed25519 signing and verification, attestations, discovery and ranking, availability, booking with signed receipts, proof-of-stay reviews, missed demand and the city demand map |
| `hive_seed.py` | Six fictional Basel businesses (five hotels, one café) with distances and attestations |
| `mcp_server.py` | The MCP server agents connect to |
| `agent.py` | The traveller agent: an OpenAI or Claude tool loop over MCP, plus a scripted planner when no key is set. Verifies every card's signature itself and holds `hive_book` until the traveller approves |
| `injection.py` | The guard on every tool result: text that addresses agents (EN, DE, FR, IT rules) is withheld before the agent reads it and reported in the trace |
| `mirror.py` | Demo only: an unverified MCP source serving a manipulated copy of Muensterhof's card, for the stress test in chapter 1 |
| `second_opinion.py` | The verifier: a separate agent (OpenAI) checks each held booking against the request and the signed card before the traveller is asked; a rule check answers without a key |
| `critic.py` | The critic: always argues for the strongest alternative to the pick from the Hive's open ranking and concedes only when the pick ranks higher. With the verifier it sets `consensus` on the agent's answer. No model call |
| `owner.py` | Plain-language card edits: proposal, diff, then re-sign and publish. Identity fields are locked. Without a key, a rule-based edit understands add, remove and room prices in EN, DE, FR and IT and returns `summary_items` the studio words in the page's language |
| `rulesets.py` | Signed rulesets a person chooses per request (e.g. "Dogs, verified" by a fictional dog owners' club). They can only narrow a search, never boost; the answer names the ruleset, its author and what it changed. Authors' keys are in `/.well-known/hive.json` under `ruleset_keys` |
| `waiting.py` | Standing requests: an agent waits anonymously when nothing fits; the owner sees counts and budgets per missing change; a published card that now fits sends each waiting agent an offer signed with the business's key |
| `replies.py` | What the backend writes itself (offline planner, rules-off demo, approval, rule-check second opinion) in EN, DE, FR and IT; the language comes from the app's `Accept-Language` header, and model runs are told to answer in it |
| `simulate.py` | Simulated traveller searches for the demand map |
| `activity.py` | The live activity feed: reads each agent result (run, Approve, ask, hand-off, scout) and keeps one line per step from fixed lists (agent, step, business, outcome, `partner` or `web`), never a person or the question. Newest 300 in `hive_activity`, so they ride along in the Postgres snapshot |
| `federation.py` | Hop-limited ("node radius") search across peer Hives: a query carries a radius, a time budget and the hubs it has already visited; each hop fans out to its most trusted peers in parallel, verifies every card that comes back against the key pinned in the card's own hub, dedups by card digest and ranks with the hub trust from `reputation.py` |
| `semantic.py` | Semantic similarity behind a small provider interface, so a search for "haircut" finds *"Cut, wash and finish"*. The offline provider is the default and needs no key, no network and no new dependency: accent-folded stems, a small four-language concept table and character trigrams, compared with cosine similarity above a named floor. An optional embedding provider is used when a key is set. `hive.discover()` turns a hit into one score component and a readable reason; `/api/health` says which provider is in use |
| `reputation.py` | Two levels of trust, kept apart: a peer *hub*'s reputation, judged locally and subjectively by this hub (declared vs observed vetting, paid placement, availability, cards it relayed that failed verification here), and a *business*'s reputation, the verified reviews and attestations discovery already scores |
| `limits.py` | How much room an entry has: a published ceiling on every field, list and total size a Card or an application may carry, enforced at both doors (`registration.apply`, `hive.publish`) and refused with the limit and the actual size. Normalises rather than refuses where it can — NFC, control and zero-width characters out, whitespace runs collapsed. Also the ASGI guard that refuses an oversized request body by size before it is parsed. Reads no content: the table is published in `documentation/cards/README.md` and at `GET /api/hub/registration` |
| `guard.py` | Owner and demo tokens, rate limits on calls that may reach Claude or OpenAI (see `SECURITY.md`) |
| `db.py`, `storage.py` | DuckDB connection, writes, and the Postgres snapshot and restore (`DATABASE_URL`) |
| `llm.py`, `config.py` | Structured-output calls on OpenAI or Claude; provider choice and environment settings |

## Use cases (`code/backend/app/domains`)

The core knows cards, trust, events and bookings. A use case adds a card kind and its own MCP tools:

| Domain | Card kind | Tools | Where |
| --- | --- | --- | --- |
| Stays | `hotel`, `cafe` | `hive_*` | `mcp_server.py` (the first domain, kept in place) |
| HR (starter) | `person` | `hr_find_people`, `hr_request_intro` | `domains/hr.py`; people are in `hive_discover` too, their contact never is |
| Explore | `adventure`, `service`, `industrial`, `software`, `event` | `explore_ask` | `domains/explore.py`, cards in `domains/examples.py` |
| Scout | any kind found on the web (`taxi`, ...) | `hive_scout` | `domains/scout.py`: web search, verifier, unclaimed cards `w-*` |

Each domain module has a `register(server)` function and is listed in `domains.DOMAINS`. How to add one:
[CONTRIBUTING.md](../CONTRIBUTING.md#add-a-use-case).

## Frontend (`code/frontend/src`)

| File | Responsibility |
| --- | --- |
| `api.ts` | Typed client for the REST API |
| `App.tsx`, `main.tsx` | The one page: a header with the two chapters, the AI status and the language switch |
| `pages/TravellerAgent.tsx` | The page itself: the traveller's brief, the approval step, the signed receipt and the next steps, questions about any business in the same chat (chapter 1), then the business's side (chapter 2) |
| `components/Chapter.tsx` | A chapter of the page: number, headline, lead and its anchor |
| `components/GroupChat.tsx` | The agent stage as a group chat: every MCP call and answer becomes a message from a named persona, paced by `lib/pace.ts`, with Replay and Skip |
| `components/TraceParts.tsx` | How each MCP call and answer reads in the chat (ranking ledger, signed card, availability) |
| `components/Reach.tsx`, `lib/hubScene.ts` | How far a search goes (this Hive, nearby Hives, further: discover radius 0, 1 or 3) and the live search that draws the result cards, each saying which hub it came from and how many hops away, with any hub that did not answer or copy that was refused |
| `components/NextSteps.tsx`, `lib/next.ts` | After a booking: a calendar file, a nearby place from the Hive, the walk from Basel SBB, and the hotel's side further down. None of them books or pays |
| `components/Icon.tsx`, `components/Display.tsx` | Our icon set; headlines with one italic phrase |
| `panels/` | The parts of chapters 2 and 3, one file each; see [The page](#the-page) |
| `components/TrustBadge.tsx`, `components/B6Bee.tsx` | Trust status lines; the footer easter egg |
| `i18n/` | English, German, French and Italian strings, the language switch and browser-language detection |
| `lib/format.ts` | Swiss date, CHF and distance formatting per language |
| `components/Connect.tsx`, `components/ConnectionRequests.tsx`, `lib/connect.ts` | Introductions. On an opened live result, the button says what connecting takes before the click: *Connect* for a `public` entry, *Ask to connect* with a line saying it waits for the owner's yes for a `confirm` one, nothing for an entry nobody may ask for; contact shows a published channel, a gated one as available on request, an empty one as not provided. The owner accepts or declines waiting requests in the business chapter. The requester is one id per browser, kept in `localStorage` |
| `lib/provenance.ts`, `lib/calibration.ts` | Which hub a result came from (origin first, answering hub last, so a relay is visible) and how a hub's calibration reads (lower is better; negative means it undersold what it offered) |
| `**/*.test.ts(x)` | Vitest unit and component tests in jsdom, `api.ts` mocked (`npm test`) |
| `styles.css` | Design tokens and every component style; see [BRAND.md](BRAND.md) |

## The page

The app is one page (`App.tsx`, no router) that tells one story in two chapters, each with an anchor the header
jumps to: `#travel`, the agent network (a room or any business, one chat); `#business`, the business's
side of the same booking. Old links such as `/agent` load the same page. `tests/test_docs.py` fails when a second
page appears or when a panel in `code/frontend/src/panels` has no row here.

Two screens sit beside that story rather than inside it, because neither belongs to the traveller:

- **The instance finder** is what a first visit lands on, and **Join** on any of its hives opens the
  application to it (`Onboarding.tsx`). You pick a Hive before you use one, which is what a
  federated directory means. The choice is remembered in `sessionStorage` for the tab, and `?hub=<id>` in the
  address skips the screen entirely — that is what the pitch runbook uses, so nothing stands between the driver
  and the booking run at 0:15.
- **The admin panel** opens only with `?admin`. Nothing on the public page links to it. It asks for the hub's
  password, and the session token it gets back lives in `sessionStorage` for the tab only.

| Panel | Chapter | What a person does there |
| --- | --- | --- |
| `AdminPanel.tsx` | `?admin` only (`#admin`) | Run the hub: sign in with its password, then the overview (the three stores counted, and the settings form generated from the fields `GET /api/admin/settings` returns), the signup queue (admit, or refuse with a required reason), the entity list (`EntitiesPanel.tsx`), the blocklist (add with a required reason, lift) and the neighbours with their calibration. A 401 or 403 returns to the password form; a 404 from an endpoint this hub does not serve yet says so instead of failing |
| `EntitiesPanel.tsx` | `?admin` only (`#admin`, Entities tab) | What this hub carries, as a list an operator can scan: id, name, kind, claimed or unclaimed, rating and count, when it was published. Open one and the detail view shows the whole signed card, its offers and needs, every contact channel with the sharing flag that actually applies, the trust block, the signature and the key it was checked against, and whether this hub has blocked it |
| `NetworkPanel.tsx` | after 2, always (`#network`) | The live node view of the hub network: this hub in the centre of a honeycomb, each configured peer a cell around it with an edge coloured by its calibration, a blocked peer still drawn and visibly cut. Four counts above it, the same hubs as rows below, and the rows alone on a phone. Open to anyone, built from `GET /api/admin/overview` and `/api/admin/neighbours`, with names and entity counts from `/api/hub/directory` where it is deployed; a hub we have not asked reads as unknown, never as zero. Polls every 10 s, only while on screen |
| `InstanceFinder.tsx` | before 1 (`#finder`) | Pick which Hive to use or join, instances.social style. Each hive answers three questions side by side: what it carries (description, entities, when it was last asked), whether it will have you (accepting, admission policy) and whether to trust it (calibration, lower is better, `unproven` when the evidence is thin). `accepting: null` and `entities: null` read as not asked yet, never as no or none. Search across name, address and description; filters for hives taking members and hives with a track record. The hive you are on is badged, not pinned first. Join is disabled where admission is closed. Falls back to one row for this hub when `GET /api/hub/directory` is not deployed |
| `Onboarding.tsx` | before 1, from Join | Join a hive without filling in a profile. Reads the hive's rules from `GET /api/hub/registration` at its `apply_at`; reads a folder in the page (`showDirectoryPicker`, `<input webkitdirectory>` as the fallback, `lib/folderPick.ts`) and never uploads it; per-part visibility, where shared and hidden parts never reach the Card; fills the Card with `seed_vaults.py`'s rules (`lib/folderScan.ts`) and asks only for the gaps, the id checked against the hive. Typing it all by hand works too. Makes an Ed25519 key in the browser and offers the private half as a download, or lets the hive hold it with the cost stated; shows the exact JSON, signs its canonical form (`lib/signing.ts`) and posts it to `POST /api/hub/register`. Admitted, pending and rejected each render with the checks, the reason and the next step; a refusal is an answer, not an error |
| `Introductions.tsx` | after 1, only while something waits (`#introductions`) | Say how an introduction actually went. Reads `GET /api/hub/connections?requester=` for this browser's open introductions, the one about to go stale first, and asks "How did it go with X?" with the deadline visible. A score is tenths of a star (0.0–5.0), given once through `POST /api/hub/connections/{id}/score`; the answer shows what the hub promised against what the person found, and where that leaves the hub (lower error is better). A stale introduction says so and stops asking |
| `InstanceFinder.tsx` | before 1 (`#finder`) | Pick which Hive to use, instances.social style: what each hub carries, whether it is accepting members, its admission policy, how many entities, when it was last asked, and how closely its published ratings matched what people found. A peer is named and described in its own words, read from its discovery document; what it has not published stays unknown rather than being shown as zero or as a refusal. Deliberately a plain first pass, and it says so on screen. **It always renders something**: loading says so, a failed or slow read says what happened and offers a retry, and this hub is listed either way, so the screen can never go blank. **Picking a Hive points the app at it**: the id and the hub's base URL go into this tab's session, and `api.ts` resolves its base per call, so every request after the pick goes to the chosen hub. `VITE_API_URL` stays the build's default for before anything is picked. A hub this page cannot call — plain HTTP from an HTTPS page, or one with no address — is offered with the reason rather than pretended at. Built from `GET /api/hub/directory` |
| `ActivityPanel.tsx` | after 2, `?demo` only (`#activity`) | Presenter tools: what the agents do behind the scenes, live: partner cards first, the web scout when none fits, hand-off only for web results, the Approve and receipt for partners |
| `DemandPanel.tsx` | 2, business | The Demand map tab: what Basel asked for that nobody offers; simulates a busy week with `?demo` |
| `OwnerPanel.tsx` | 2, business | The whole business chapter: the change box in the brief; in the panel, the owner studio (the booking just made, what agents asked for, the diff, sign and publish, the new version live) and the demand map as a tab; the tamper test with `?demo` |

## MCP tools (`/mcp/`, Streamable HTTP)

| Tool | What it does |
| --- | --- |
| `hive_discover` | Search **everything on the hub** by what it offers and what it needs: hotels, people, cafés, unclaimed example cards. `looking_for` says which side of the market the caller is on — `offers` (the default) finds whoever provides the thing, `needs` whoever wants what the caller provides, `any` both. `kind` is a filter the caller may apply, not a gate the hub applies for them. Hard constraints as before (features, max price, near, dates, guests), optionally under a ruleset the user chose, and optionally with a `radius` of 1 to 3 hops over peer Hives (0, the default, is this Hive only). Returns ranked matches with a score breakdown (`constraints`, `offers_needs`, `text_relevance`, `proximity`, reputation) and every excluded entity with why. `constraints` is earned, not granted: it is paid for the constraints the ask actually carried and the entity met, so an ask with no dates, no budget and no features pays nobody and relevance decides. Every entity carries `name`, `description`, `rating` (null until a signed receipt earns one), `contact`, `claimed` and `bookable`: an unclaimed card is a lead compiled from public information, never bookable. A federated match adds `provenance`, `hops` and the three federated rank factors |
| `hive_rulesets` | The rulesets a user can choose, each signed by its author |
| `hive_get_card` | The full signed card with trust information |
| `hive_check_availability` | Free units and totals for given dates |
| `hive_book` | Book a unit; returns a signed receipt |
| `hive_what_was_promised` | With a receipt: the signed card version the booking was made against, and which fields changed since |
| `hive_cancel` | Cancel with the receipt |
| `hive_review` | Leave a review; only valid with an unused booking receipt |
| `hive_wait` | When nothing fits and the traveller wants to be told: leave an anonymous standing request; returns an id and a secret token |
| `hub_connect` | Ask to be introduced to a business or person found in a search, and log the introduction. A public entry opens at once, one marked `needs_confirmation` waits for its owner's yes, and one shared only on the owner's initiative cannot be asked for |
| `hub_score` | Record how an introduction actually went, after the real meeting: tenths of a star out of five, once, and only while the connection is still open. The only input to how far this Hive trusts another |
| `hub_connections` | Introductions still waiting on an owner's yes or on a person's score, so an agent can ask before one goes stale |
| `hub_standing` | What this Hive makes of its neighbours: published minus realised, lower is better, unproven when the evidence is thin |
| `hub_registration` | What this Hive asks of someone who wants to join: policy, checks, proof types and an example document |
| `hub_register` | Apply to join with one signed JSON document. Bring a public key and the user keeps the private half |
| `hub_directory` | The Hives this one knows of, so a user can choose which to join, with each one's calibration |
| `hive_check_waiting` | Read a standing request with its token: status and any offers, each signed by the business (check with its pinned key) |
| `hr_find_people` | Find person cards by skills (and location); public fields only, with reasons for who was left out |
| `explore_ask` | Answer a question from the cards that cover it (none if nothing does, counted as demand; `clarify` names what a request still has to say, such as a taxi's route and time), with reasons for what was left out and the mood the person chose; an action comes back as needing the person's approval in the app |
| `hive_scout` | When no card answers: find real businesses on the public web (OpenAI web search, else OpenStreetMap), verify each against its own site, add the verified ones as unclaimed cards with source and checks |
| `hr_request_intro` | Ask to meet a person; recorded for them, nothing shared until they consent |

Agents can find the endpoint from `/.well-known/hive.json`.

## REST API

The web app's contract, in `code/backend/app/main.py`. Every running backend also serves it interactively at
`/docs` (Swagger UI) and as `/openapi.json`. Change an endpoint, `api.ts` and this table in one PR;
`tests/test_docs.py` fails when a served endpoint has no row here.

| Endpoint | What it does | Guard |
| --- | --- | --- |
| `GET /api/health` | Up, and which model provider the agents use (`openai`, `claude` or `mock`) | |
| `GET /.well-known/hive.json` | Discovery for agents: the MCP URL, policies, pinned `owner_keys` and `ruleset_keys` | |
| `GET /api/hive/cards` | All cards, optionally `?kind=` | |
| `GET /api/hive/discover` | Search with the same constraints and `looking_for` as `hive_discover`, plus `radius` (0 = this Hive, up to 3 hops over peer Hives), `budget_ms` and `seen`. Also the door one Hive uses to forward a query to another | rate limit above radius 0 |
| `POST /api/hub/connect` | Ask to be introduced to an entity, and log it | rate limit |
| `POST /api/hub/connections/{connection_id}/score` | Score an introduction after the real meeting, once | — |
| `POST /api/hub/connections/{connection_id}/confirm` | The owner says yes to an introduction | — |
| `POST /api/hub/connections/{connection_id}/decline` | The owner says no; it never becomes a rating | — |
| `GET /api/hub/connections` | Introductions waiting on a yes or on a score | — |
| `GET /api/hub/standing` | This hub's view of its neighbours, best calibrated first | — |
| `POST /api/admin/login` | Exchange the hub's `ADMIN_PASSWORD` for a short-lived session token, so a person can administer the hub from a browser. A refusal says nothing about the password; a lockout says when to try again | rate limit per client IP **and** in total, fails closed |
| `POST /api/admin/logout` | End this session token | `X-Admin-Token` |
| `GET /api/hub/registration` | The admission policy and the exact document to send | — |
| `POST /api/hub/register` | Apply to join. A refusal is 200 with `state: rejected`, not a 4xx | rate limit |
| `GET /api/hub/register/{application_id}` | Check on an application | — |
| `POST /api/hub/register/{application_id}/withdraw` | Withdraw before a decision | — |
| `GET /api/hub/directory` | Hives to choose between, instances.social style | — |
| `GET /api/admin/applications` | The admission queue; `state=pending` is what waits on a person | — |
| `POST /api/admin/applications/{application_id}` | Admit or refuse; a refusal needs a reason | `X-Admin-Token` |
| `GET /api/admin/entities` | Every entity this hub carries: id, name, kind, claimed, rating and count, published at | `X-Admin-Token`, fails closed |
| `GET /api/admin/entities/{entity_id}` | One entity in full: the signed card, its offers and needs, contact with the sharing flag that applies to each channel, its trust block, its signature state, and whether it is blocked | `X-Admin-Token`, fails closed |
| `GET /api/admin/overview` | The three stores counted, plus peer standing, for an admin front page | — |
| `GET /api/admin/settings` | Hub settings as renderable fields: value, help, options | — |
| `GET /api/admin/neighbours` | The peer list with each one's calibration | — |
| `GET /api/admin/blocklist` | Everything this hub has shut out; readable without a token on purpose | — |
| `POST /api/admin/blocklist` | Block a peer hub or an entity, in both directions | `X-Admin-Token` (static or a session token), declared so `/docs` shows a box, fails closed |
| `DELETE /api/admin/blocklist/{kind}/{subject}` | Lift a block | `X-Admin-Token`, fails closed |
| `GET /api/hive/cards/{card_id}` | One signed card by id or slug, with trust (signature, `valid_until`, `fresh`, attestations, reviews) | |
| `GET /api/hive/cards/{card_id}/availability` | Free units and totals for `check_in`, `check_out`, `guests` | |
| `POST /api/hive/cards/{card_id}/book` | A person's direct booking, for a business's own site; returns a signed receipt | |
| `POST /api/hive/reviews` | A proof-of-stay review; needs an unused booking receipt | |
| `POST /api/hive/verify` | Check a card as an agent would, against the owner's pinned key | |
| `POST /api/hive/demo/forge/{card_id}` | Tamper demo: a copy re-signed by a stranger, which must fail | rate limit |
| `GET /api/hive/demand` | The city demand map: what agents asked for, how often nobody could serve it | |
| `POST /api/demo/simulate` | Up to 200 simulated traveller searches for the demand map | rate limit |
| `POST /api/demo/reset` | Back to the seed cards, no bookings, no demand | `X-Demo-Token` |
| `POST /api/agent` | Run the traveller agent over MCP; a booking comes back held, as `pending`, with the verifier's `second_opinion`, the `critic` and `consensus` | model rate limit |
| `POST /api/agent/approve` | The traveller's yes: send the held booking, once | one-time hold |
| `POST /api/ask` | Ask the Hive about the example cards, with an optional mood; actions come back held | model rate limit |
| `POST /api/ask/scout` | No card answered: the scout finds, verifies and adds unclaimed cards from the public web, then asks again; the request counts as unserved demand | model rate limit |
| `POST /api/ask/approve` | The person's yes: hand the held action off to the business | one-time hold |
| `GET /api/activity` | The live activity feed: lines newer than `?after=` (oldest first, up to `limit`), and `last` as the next cursor. No personal data | |
| `GET /api/owner/{card_id}` | Owner studio data for any card, unclaimed too: bookings, hand-offs to the business's site (item and time, never who), missed demand, waiting requests, and what agents did with the card in the last 7 days (`shown`, `read`, `checked`, `booked`, `explore_handoff`); guest names as initials without the token | `X-Owner-Token` for names |
| `POST /api/owner/{card_id}/propose` | The owner's words to a proposed card and a diff; nothing is published | `X-Owner-Token`, model rate limit |
| `POST /api/owner/{card_id}/publish` | Sign and publish the approved card as a new version; waiting agents get signed offers | `X-Owner-Token` |

Every request carries the app's language as `Accept-Language`; `/api/agent`, `/api/agent/approve` and the
second opinion answer in it.

Rulesets, standing requests and "what was promised" are agent features, so they are MCP tools only (see above).

## Trust by design

- **Signatures.** Each card version is signed over canonical JSON (sorted keys, compact separators) with the
  owner's Ed25519 key. Agents verify client-side; the owner studio has a live tamper test.
- **Expiry.** `publish` signs a `valid_until` into every version (`FRESH_DAYS`, 90); discovery leaves out an
  expired card with the reason, and `trust.fresh` says whether it still holds.
- **Attestations.** Third parties sign single claims, shown as "dog-friendly verified".
- **Receipts.** A booking returns `base64url(body).signature`. A review needs one, once. The receipt pins the card
  version and its digest; every signed version is kept, so the receipt can later show what was promised.
- **Offers.** An offer to a waiting agent has the same form, signed by the business; `hive.verify_statement` checks
  it against the pinned key. It holds no room: the agent still asks its human before `hive_book`.
- **Transparent ranking.** No paid placement; the score breakdown and exclusion reasons are part of the response.
- **Two levels of trust** (`reputation.py`). A *business* earns reputation from proof-of-stay reviews and
  attestations. A peer *Hive* earns a hub reputation, judged locally and subjectively by this hub alone: there is
  no global score and no consensus. New peers start low (trust on first use) and accrue slowly; a hub that
  declares paid placement, misses deadlines, or relays cards that fail verification here is downweighted, which
  lowers every card it carries. Vetting its own members honestly is therefore each hub's own interest.
- **Federated search, hop by hop** (`federation.py`). A query's `radius` is its hop limit (0 = this Hive, cap 3),
  with a time budget, a breadth cap per hop and a `seen` list that cuts the cycles in the peer graph. A result's
  rank is `local_relevance x hub_path_trust x hop_decay`, all three in `score_breakdown`, and its `provenance`
  names every hub it travelled. Signatures are checked at the destination against the key pinned in the card's own
  hub registry, fetched directly, so a relaying hub can withhold or delay a card but never forge one.
- **Missed demand.** Every exclusion and every search is logged; owners see what they were turned away for, the
  city sees what nobody offers.
- **Prompt safety.** Card text is treated as data in the agent's prompt, never as instructions. A guard withholds
  text addressed to agents before the agent reads it, and the agent checks every card's signature itself. Try it with
  the stress test in chapter 1, or `POST /api/agent` with `"scenario": "injection"` (and `"rules": "off"` for the
  unguarded counterfactual, which is scripted and never books).
- **Human in the loop.** The agent holds `hive_book` until the traveller approves (`POST /api/agent/approve`).
- **Unclaimed cards.** A card with `provenance.verified_by_owner: false` was compiled from a public website and is
  signed by the Hive as compiler. `trust.claimed` is false, the UI and every answer say so, owner edits refuse it,
  and an approved action only hands the person off to the business's own site.
- **Chosen, not inferred.** The API takes an optional mood a person sets (the app no longer shows a picker); the
  answer echoes it with its effects. Only the mood and the cards asked about are counted, never the question text or who asked.
- **Abuse limits.** Owner edits can require a token, model calls are rate-limited, all input is bounded.
  Details and known limits: [SECURITY.md](../SECURITY.md).

## Stack and cost

Python 3.12, FastAPI, DuckDB, MCP Python SDK, OpenAI SDK (Anthropic SDK as the alternative); React 18, Vite,
TypeScript. Agents use `gpt-5-mini` (`OPENAI_MODEL`); `AGENT_MAX_TURNS` caps each run and `AGENT_TIMEOUT_S` hands a
slow run to the offline planner. Hosting is free: GitHub Pages for the app, Render and Render Postgres for the
backend. Without a key everything still runs offline.

## Known limits

- The server holds each owner's signing key (the vision is owner-held keys).
- DuckDB on local disk with a Postgres snapshot pins the backend to one instance. Fine for a demo.
- No real payments; restaurant table booking is not built yet.
