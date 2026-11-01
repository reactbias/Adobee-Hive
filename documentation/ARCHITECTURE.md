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
| `agent.py` | The traveller agent: an OpenAI or Claude tool loop over MCP, plus a scripted planner when no key is set. Verifies every card's signature itself and holds `hive_book` with its selected MCP source until approval; a removed source is refused, never replaced by the first configured Hive |
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
| `federation.py` | Hop-limited ("node radius") search across peer Hives: the peer list comes from `peers.py` rather than the environment, a query carries a radius, a time budget and the hubs it has already visited; each hop fans out to its most trusted peers in parallel, verifies every card that comes back against the key pinned in the card's own hub, dedups by card digest and ranks with the hub trust from `reputation.py`. Each registry outcome is shared within one query, including an empty startup registry, so a later query can still refresh it |
| `semantic.py` | Semantic similarity behind a small provider interface, so a search for "haircut" finds *"Cut, wash and finish"* and one for a *Gartenzimmer* finds a garden. The offline provider is the default and needs no key, no network and no new dependency: accent-folded stems, German compound splitting, a four-language concept table of the errands this hub carries, and character trigrams, compared with cosine similarity above a named floor. The seam for an optional key-using provider (embeddings) is there and empty: with no provider built, a hub with a key searches exactly as well as one without. `hive.discover()` turns a hit into one score component with a readable reason — worth less per word than really offering the thing, and less again from prose than from `offers`/`needs`; `/api/health` says which provider is in use, never anything about a key. Measured by `tools/eval_answer_key.py` against the answer key in `testdata/README.md` |
| `reputation.py` | Two levels of trust, kept apart: a peer *hub*'s reputation, judged locally and subjectively by this hub (declared vs observed vetting, paid placement, availability, cards it relayed that failed verification here), and a *business*'s reputation, the verified reviews and attestations discovery already scores |
| `services.py` | Optional outside services and the keys they need, set by an operator instead of by a redeploy. **Write-only**: a key goes into `hub_service_keys` and no endpoint, log or error message ever gives it back — an interface sees presence, a SHA-256 fingerprint and the last four characters. `key_for()` prefers the stored key and falls back to the environment variable, so a hub deployed with `OPENAI_API_KEY` behaves exactly as before; `provider()` and `enabled()` answer per call, so a key stored in the panel takes effect without a restart. One cheap probe per service says whether a key works. The key is stored in the clear unless the host encrypts its disk, and the UI says so rather than implying more |
| `peers.py` | The peer hubs this hub asks, as rows an operator changes while it runs: add, edit, remove, each with a required reason. `HIVE_PEER_URLS` is only the **seed for a fresh hub**; once anything is stored, including a removal, the table is the live list, so a dropped peer does not come back at the next restart. `federation._choose_peers` reads it per query, so there is no cache and no restart. Whether a peer answers is the stored result of a bounded parallel probe, never a fetch on a page load |
| `removals.py` | Entities this hub no longer carries. A **withdrawal, never a delete**: the signed card and every signed version stay, because `hive_card_history` is what lets a receipt prove what a card said on the day it was booked. A withdrawn entity is out of `hive.list_cards`, so out of discovery — matches and excluded alike — and `hive.book` and `hive.check_availability` refuse it. A reason is required, as on the blocklist. Removing is this hub dropping an entity; blocking is refusing it wherever it comes from |
| `audit.py` | The admin ledger: every peer change and every removal with its time, subject, reason and which credential was used. `actor` is always `admin` because the hub has one shared password, and `audit.WHO_LIMIT` says so rather than implying a name |
| `folders.py` | The folder link: two agents connecting their private folders between the search and the booking. A *link* is handle to handle and carries no content, and unlocks only the manifest — a linked peer sees that the `shared` files exist, which the Card never said. A *grant* is per path and is the only thing that makes bytes readable. `private` and `hidden` paths are counted, never named, and a refused grant says the same words for a hidden file as for one that was never there. One protocol, two implementations chosen by `FOLDER_LINK`: `LocalFolderLink` over the folders in `testdata/vaults/` (default; no key, no network, no new dependency) and `CcFolderLink` over [ClaudeConnect](https://github.com/bstadt/cc_daemon). `/api/health` says which is in use and why. The HTTP surface over it is [FOLDER_API.md](FOLDER_API.md) |
| `folder_keys.py` | Who is asking. A folder read needs a caller identity, and this hub has no accounts, so the credential is bound to the *link*: accepting one mints 32 random bytes, returns them exactly once and stores only their SHA-256. Presenting them as `Authorization: Bearer <secret>` resolves to the handle that holds them and the peer at the other end, which is why the read endpoints take no handle parameter and have nothing to enumerate. The link's state is re-read on every request, so revoking a link stops its reads on the next call rather than at a cache expiry. Never logged, never returned twice | 
| `limits.py` | How much room an entry has: a published ceiling on every field, list and total size a Card or an application may carry, enforced at both doors (`registration.apply`, `hive.publish`) and refused with the limit and the actual size. Normalises rather than refuses where it can — NFC, control and zero-width characters out, whitespace runs collapsed. Also the ASGI guard that refuses an oversized request body by size before it is parsed. Reads no content: the table is published in `documentation/cards/README.md` and at `GET /api/hub/registration` |
| `guard.py` | Owner and demo tokens, and the one admission boundary both transports spend: rate limits on calls that may reach Claude or OpenAI and on calls that reach this hub's peers. REST spends a limiter through `RateLimiter.check`, an MCP tool spends the same limiter object through `admit_mcp`, so a budget exhausted at one door refuses the other. The module docstring has the whole client-attribution table (see `SECURITY.md`) |
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
| `App.tsx`, `main.tsx` | Shared navigation and language switch for travel, business and network screens |
| `components/BackendStatus.tsx` | Independent backend reachability and configured planner status, selected Hive/address, last check, last success and failure retry. Checks only while visible, 15 seconds after completion, with a five-second health deadline; configuration does not prove a vendor has credits |
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
jumps to: `#find`, the agent network (a room or any business, one chat); `#offer`, the business's
side of the same booking. They are the two sides of every Card rather than two kinds of person, which is why
they are not named for a traveller and a business. `#travel` and `#business`, the names they used to carry, are
still read and are rewritten to the new ones in the address bar. Old links such as `/agent` load the same page. `tests/test_docs.py` fails when a second
page appears or when a panel in `code/frontend/src/panels` has no row here.

Two screens sit beside that story rather than inside it, because neither belongs to the person searching:

- **The instance finder** is what a first visit lands on, and **Join** on any of its hives opens the
  application to it (`Onboarding.tsx`). You pick a Hive before you use one, which is what a
  federated directory means. The choice is remembered in `sessionStorage` for the tab, and `?hub=<id>` in the
  address skips the screen entirely — that is what the pitch runbook uses, so nothing stands between the driver
  and the booking run at 0:15.
- **The admin panel** opens only with `?admin`. Nothing on the public page links to it. It asks for the hub's
  password, and the session token it gets back lives in `sessionStorage` for the tab only.

| Panel | Chapter | What a person does there |
| --- | --- | --- |
| `AdminPanel.tsx` | `?admin` only (`#admin`) | Run the hub: sign in with its password, then the overview (the three stores counted, and the settings form generated from the fields `GET /api/admin/settings` returns), the signup queue (admit, or refuse with a required reason), the entity list (`EntitiesPanel.tsx`), the blocklist (add with a required reason, lift) and the connected hubs (`PeersPanel.tsx`) and the optional services (`ServicesPanel.tsx`). A 401 or 403 returns to the password form; a 404 from an endpoint this hub does not serve yet says so instead of failing |
| `EntitiesPanel.tsx` | `?admin` only (`#admin`, Entities tab) | What this hub carries, as a list an operator can scan: id, name, kind, claimed or unclaimed, rating and count, when it was published. Open one and the detail view shows the whole signed card, its offers and needs, every contact channel with the sharing flag that actually applies, the trust block, the signature and the key it was checked against, and whether this hub has blocked it. From there: **Remove** (a withdrawal, reason required, with a confirmation that names the entity and says what will happen), **Restore**, and **Block**, with the difference between removing and blocking written on the screen |
| `ServicesPanel.tsx` | `?admin` only (`#admin`, Services tab) | The optional integrations: what each is for, what the hub does without it, whether a key is set and whether it came from the panel or the environment, and a *Test* button that makes one cheap call. Set and clear a key; a stored key is shown only as a fingerprint and four characters, never in full, and the panel says plainly that it is stored on this hub in the clear unless the host encrypts its disk |
| `PeersPanel.tsx` | `?admin` only (`#admin`, Neighbours tab) | Manage the connected hubs: add, edit and remove a peer at runtime, each with a required reason, and *Check now* to ask them all whether they answer. Each row carries the URL, the hub id, the name, whether it answers and when it was last tried, and its calibration. Removing and blocking are both offered, with the difference written on the screen: removing stops this hub asking a peer, blocking refuses it in both directions |
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
| `hive_discover` | Search **everything on the hub** by what it offers and what it needs: hotels, people, cafés, unclaimed example cards. `looking_for` says which side of the market the caller is on — `offers` (the default) finds whoever provides the thing, `needs` whoever wants what the caller provides, `any` both. `kind` is a filter the caller may apply, not a gate the hub applies for them. Hard constraints as before (features, max price, near, dates, guests), optionally under a ruleset the user chose, and optionally with a `radius` of 1 to 3 hops over peer Hives (0, the default, is this Hive only). Returns ranked matches with a score breakdown (`constraints`, `offers_needs`, `text_relevance`, `proximity`, reputation) and every excluded entity with why. `constraints` is earned, not granted: it is paid for the constraints the ask actually carried and the entity met, so an ask with no dates, no budget and no features pays nobody and relevance decides. Every entity carries `name`, `description`, `rating` (null until a signed receipt earns one), `contact`, `claimed` and `bookable`: an unclaimed card is a lead compiled from public information, never bookable. A federated match adds `provenance`, `hops` and the three federated rank factors. A `radius` above 0 spends the same per-caller-and-total budget `GET /api/hive/discover` spends, charged to the address the transport reports; `limit` bounds the answer at 50 matches, and a cut answer says `truncated` and `total_matches` rather than looking whole |
| `hive_rulesets` | The rulesets a user can choose, each signed by its author |
| `hive_get_card` | The full signed card with trust information |
| `hive_check_availability` | Free units and totals for given dates, each with a `terms` hash of its total and the card's policies |
| `hive_book` | Book a unit; returns a signed receipt. An optional `expected_terms` refuses the booking if the terms have changed |
| `hive_what_was_promised` | With a receipt: the signed card version the booking was made against, and which fields changed since |
| `hive_cancel` | Cancel with the receipt |
| `hive_review` | Leave a review; only valid with an unused booking receipt |
| `hive_wait` | When nothing fits and the traveller wants to be told: leave an anonymous standing request; returns an id and a secret token |
| `hub_connect` | Ask to be introduced to a business or person found in a search, and log the introduction. A public entry opens at once, one marked `needs_confirmation` waits for its owner's yes, and one shared only on the owner's initiative cannot be asked for |
| `hub_score` | Record how an introduction actually went, after the real meeting: tenths of a star out of five, once, and only while the connection is still open. The only input to how far this Hive trusts another |
| `hub_connections` | Introductions still waiting on an owner's yes or on a person's score, so an agent can ask before one goes stale. Each row carries `stale_in_days` (whole days left, 0 on the last one) as well as the absolute `stale_at`, and `stale_soon` flags an open introduction with a week or less to go, so the deadline reminds the agent instead of the agent having to work it out |
| `hub_standing` | What this Hive makes of its neighbours: published minus realised, lower is better, unproven when the evidence is thin |
| `hub_registration` | What this Hive asks of someone who wants to join: policy, checks, proof types and an example document |
| `hub_register` | Apply to join with one signed JSON document. Bring a public key and the user keeps the private half |
| `hub_directory` | The Hives this one knows of, so a user can choose which to join, with each one's calibration |
| `hive_check_waiting` | Read a standing request with its token: status and any offers, each signed by the business (check with its pinned key) |
| `hr_find_people` | Find person cards by skills (and location); public fields only, with reasons for who was left out |
| `explore_ask` | Answer a question from the cards that cover it (none if nothing does, counted as demand; `clarify` names what a request still has to say, such as a taxi's route and time), with reasons for what was left out and the mood the person chose; an action comes back as needing the person's approval in the app |
| `hive_scout` | When no card answers: find real businesses on the public web (OpenAI web search, else OpenStreetMap), verify each against its own site, add the verified ones as unclaimed cards with source and checks |
| `hr_request_intro` | Ask to meet a person; recorded for them, nothing shared until they consent |
| `hive_owner_card` | One card as its owner sees it: the signed card, its bookings or hand-offs, the demand it missed, what agents did with it in the last 7 days, and who is waiting for a change. The same answer as `GET /api/owner/{card_id}` — guest names come through as initials unless the connection carries the owner token, and nothing else is withheld |
| `hive_owner_propose` | A plain-language change to the owner's own card to a proposed card and a field-by-field diff, in EN/DE/FR/IT. Publishes nothing: the diff is what the agent shows its person. A change over one of the published ceilings is refused here, naming the ceiling and the size |
| `hive_owner_publish` | Sign and publish the proposed card the owner said yes to, as a new version; waiting agents get signed offers. Identity fields keep their values. **Fails closed**: the owner token must arrive in the `X-Owner-Token` header of the MCP connection, and a hub with no `OWNER_EDIT_TOKEN` set publishes nothing over MCP at all |

Agents can find the endpoint from `/.well-known/hive.json`. How a search reaches another hub and how a hub is
measured: [FEDERATION.md](FEDERATION.md). How an entity gets into a hub in the first place:
[REGISTRATION.md](REGISTRATION.md). What a card carries: [cards/README.md](cards/README.md). How to search a hub
from your own code, endpoint by endpoint with real responses: [SEARCH_API.md](SEARCH_API.md).
Agents can find the endpoint from `/.well-known/hive.json`.

## REST API

The web app's contract, in `code/backend/app/main.py`. Every running backend also serves it interactively at
`/docs` (Swagger UI) and as `/openapi.json`. Change an endpoint, `api.ts` and this table in one PR;
`tests/test_docs.py` fails when a served endpoint has no row here.

| Endpoint | What it does | Guard |
| --- | --- | --- |
| `GET /api/health` | Up, which model provider the agents use (`openai`, `claude` or `mock`) and which similarity provider discovery ranks with (`semantic`: `offline` or `embeddings`). Never anything about a key | |
| `GET /.well-known/hive.json` | Discovery for agents: the MCP URL, policies, pinned `owner_keys` and `ruleset_keys` | |
| `GET /api/hive/cards` | All cards, optionally `?kind=` | |
| `GET /api/hive/discover` | Structured constraints and `looking_for`, plus `radius`, `budget_ms` and `seen` for peer forwarding. Explicit hotel/room prose reuses the stay parser for constraints and removes declared guest identity from ranking; explicit query parameters win and absent stay dates are not invented. Generic services/needs searches remain generic | rate limit above radius 0 |
| `POST /api/hub/connect` | Ask to be introduced to an entity, and log it. Also hands the requester the secret for its side of the folder link the handshake opened, once. For an entity on a **peer**, pass `card` (the signed card the federated search returned) and `target_hub`: this hub verifies it against the key that hub pinned for it and refuses it otherwise, so an introduction is this hub's to record even when the entity is not its own | rate limit |
| `GET /api/hub/connections/{connection_id}/decision` | The document a target's owner signs to answer this introduction, and its canonical bytes | — |
| `POST /api/hub/connections/{connection_id}/score` | Score an introduction after the real meeting, once. Needs the **requester's** own link secret in `Authorization: Bearer`, which the connect answer returned. Fails closed | requester proof |
| `POST /api/hub/connections/{connection_id}/confirm` | The owner says yes. Needs authority over the target: its side of the link, a signature under the key it registered, or this hub's `X-Owner-Token`. Fails closed | target proof |
| `POST /api/hub/connections/{connection_id}/decline` | The owner says no; it never becomes a rating. Same authority, and the requester may withdraw with its own secret | target or requester proof |
| `GET /api/hub/connections` | Introductions waiting on a yes or on a score, each with the days it has left (`stale_in_days`, `stale_soon`) | — |
| `GET /api/hub/standing` | This hub's view of its neighbours, best calibrated first | — |
| `GET /api/folders/status` | Which folder link is in use, what was asked for, why they differ, what a read costs, and the honest line that on `local` both folders are on one disk. Names no server path | — |
| `GET /api/folders/manifest` | The peer's folder as this link may see it: paths, sizes, digests, `readable`, and `withheld` as a **count**. Owner and viewer come from the bearer and there is no handle parameter, so there is nothing to enumerate | `Authorization: Bearer <link secret>` |
| `GET /api/folders/file` | The bytes of one granted file, streamed in 64 KiB pieces. `public` needs no grant; everything else needs one naming that path. A hidden file, a private file, an ungranted file and a file that never existed are the identical 404. No `Range`; over `FOLDER_READ_MAX_BYTES` is 413. Every served read is a `folder.read` row in the ledger | `Authorization: Bearer <link secret>`, rate-limited per link |
| `POST /api/folders/keys` | Mint a link secret for one party to an established link, returned once. The hub's own token, which does **not** prove per-owner identity — see [FOLDER_API.md](FOLDER_API.md) | `X-Admin-Token`, fails closed |
| `GET /api/folders/grants` | Both halves of this link's grants, `given` and `received`, kept apart: an owner has to know which of them is theirs to take back | `Authorization: Bearer <link secret>` |
| `POST /api/folders/grants` | Open one path of the caller's **own** folder to the peer on this link. The body carries only a path: whose folder and to whom both come from the bearer, which is what makes it a per-owner write on a hub with no owner accounts. One path, never a pattern | `Authorization: Bearer <link secret>` |
| `DELETE /api/folders/grants/{grant_id}` | Take one grant back. Only the owner who gave it may, and somebody else's grant id is *not found* in the same words as one that never existed | `Authorization: Bearer <link secret>` |
| `DELETE /api/folders/links/{link_id}` | Withdraw the folder link, and with it every secret and every read it allowed, on the next request. Either party may | `Authorization: Bearer <link secret>` |
| `POST /api/admin/login` | Exchange the hub's `ADMIN_PASSWORD` for a short-lived session token, so a person can administer the hub from a browser. A refusal says nothing about the password; a lockout says when to try again | rate limit per client IP **and** in total, fails closed |
| `POST /api/admin/logout` | End this session token | `X-Admin-Token` |
| `GET /api/hub/registration` | The admission policy and the exact document to send | — |
| `POST /api/hub/register` | Apply to join. A refusal is 200 with `state: rejected`, not a 4xx | rate limit |
| `GET /api/hub/register/{application_id}` | Check on an application | — |
| `GET /api/hub/register/{application_id}/withdrawal` | The document to sign to withdraw this application, and its canonical bytes | — |
| `POST /api/hub/register/{application_id}/withdraw` | Withdraw your own application before a decision. An id is a lookup, not authority: needs a signed action under the key the application registered, or the capability the submission returned once, in `X-Application-Key`. Fails closed | applicant proof |
| `GET /api/hub/directory` | Hives to choose between, instances.social style | — |
| `GET /api/admin/applications` | The admission queue; `state=pending` is what waits on a person | — |
| `POST /api/admin/applications/{application_id}` | Admit or refuse; a refusal needs a reason | `X-Admin-Token` |
| `POST /api/admin/applications/{application_id}/withdraw` | Withdraw an application as the operator. Recorded as the operator's act, never as the applicant's consent | `X-Admin-Token`, fails closed |
| `POST /api/admin/connections/{connection_id}/{action}` | Confirm, decline or score an introduction as the operator. Recorded as the operator's act, never as the owner's consent or the requester's report | `X-Admin-Token`, fails closed |
| `GET /api/admin/entities` | Every entity this hub carries: id, name, kind, claimed, rating and count, published at | `X-Admin-Token`, fails closed |
| `GET /api/admin/entities/{entity_id}` | One entity in full: the signed card, its offers and needs, contact with the sharing flag that applies to each channel, its trust block, its signature state, and whether it is blocked | `X-Admin-Token`, fails closed |
| `POST /api/admin/entities/{entity_id}/remove` | Stop carrying an entity: out of discovery, not bookable, signed history kept. A reason is required | `X-Admin-Token`, fails closed |
| `POST /api/admin/entities/{entity_id}/restore` | Carry it again; the ledger keeps both decisions | `X-Admin-Token`, fails closed |
| `GET /api/admin/audit` | The admin ledger: what changed, when, why, with which credential | `X-Admin-Token`, fails closed |
| `GET /api/admin/peers` | The peers this hub asks: URL, hub id, name, whether it answers and when it was last tried, its calibration, its state. A database read, never a fetch | `X-Admin-Token`, fails closed |
| `POST /api/admin/peers` | Add a peer hub; the next federated search asks it | `X-Admin-Token`, fails closed |
| `PUT /api/admin/peers` | Change its hub id, the name shown here, or the note | `X-Admin-Token`, fails closed |
| `POST /api/admin/peers/remove` | Stop asking a peer. Not a block | `X-Admin-Token`, fails closed |
| `POST /api/admin/peers/check` | Ask every peer whether it answers, in parallel under one deadline, and store the result | `X-Admin-Token`, fails closed |
| `GET /api/admin/services` | Every optional integration: what it is for, whether a key is set and from where, how it last tested. Never a key: a stored one is shown only as a fingerprint and its last four characters | `X-Admin-Token`, fails closed |
| `POST /api/admin/services/{name}` | Store a key for one service; the next call that needs it uses it. Write-only: the answer is the service's status | `X-Admin-Token`, fails closed |
| `DELETE /api/admin/services/{name}` | Forget the stored key; the hub falls back to the environment, or to working without one | `X-Admin-Token`, fails closed |
| `POST /api/admin/services/{name}/check` | One cheap authenticated call with the key in use. A key that does not work is a 200 with `working: false`, scrubbed of the key | `X-Admin-Token`, fails closed |
| `GET /api/admin/overview` | The three stores counted, plus peer standing, for an admin front page | — |
| `GET /api/admin/settings` | Hub settings as renderable fields: value, help, options | — |
| `GET /api/admin/neighbours` | The peer list with each one's calibration | — |
| `GET /api/admin/blocklist` | Everything this hub has shut out; readable without a token on purpose | — |
| `POST /api/admin/blocklist` | Block a peer hub or an entity, in both directions | `X-Admin-Token` (static or a session token), declared so `/docs` shows a box, fails closed |
| `DELETE /api/admin/blocklist/{kind}/{subject}` | Lift a block | `X-Admin-Token`, fails closed |
| `GET /api/hive/cards/{card_id}` | One signed card by id or slug, with trust (signature, `valid_until`, `fresh`, attestations, reviews) | |
| `GET /api/hive/cards/{card_id}/availability` | Free units and totals for `check_in`, `check_out`, `guests` | |
| `POST /api/hive/cards/signed` | Store a card version its owner signed on their own node, exactly as signed. The first version pins the key, a later one must verify against it. This hub holds no key for that card, so it cannot edit or book it | `X-Owner-Token` |
| `POST /api/hive/cards/{card_id}/book` | A person's direct booking, for a business's own site; returns a signed receipt | |
| `POST /api/hive/reviews` | A proof-of-stay review; needs an unused booking receipt | |
| `POST /api/hive/verify` | Check a card as an agent would, against the owner's pinned key | |
| `POST /api/hive/demo/forge/{card_id}` | Tamper demo: a copy re-signed by a stranger, which must fail | rate limit |
| `GET /api/hive/demand` | The city demand map: what agents asked for, how often nobody could serve it | |
| `POST /api/demo/simulate` | Up to 200 simulated traveller searches for the demand map | rate limit |
| `POST /api/demo/reset` | Back to the seed cards, no bookings, no demand | `X-Demo-Token` |
| `POST /api/agent` | Run the traveller agent over MCP; a booking comes back held, as `pending`, with the verifier's `second_opinion`, the `critic` and `consensus` | model rate limit |
| `POST /api/agent/approve` | The traveller's yes: send the held booking once to its original configured MCP source; reject a removed source rather than retargeting it | one-time hold |
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
The three owner routes are the other way round — they have MCP tools *as well*, so an owner's own agent never has
to leave the protocol to look after their entry: `hive_owner_card`, `hive_owner_propose`, `hive_owner_publish`.
All six paths go through `owner.py`, and the read guard is one function (`owner.overview`) so the two surfaces
cannot drift into different ideas of what an owner may read. What differs is the write guard, on purpose: a REST
route with no `OWNER_EDIT_TOKEN` set is open, as it has always been, while the MCP tools refuse — see
[LIMITS.md](LIMITS.md#running-a-hub).

## Separate nodes

The design keeps the browser, the agent, the business and the hub apart, wherever each one runs. Two of those
separations can be switched on today, using the same backend code with different settings:

- **The agent as its own service.** Set `HIVE_MCP_URLS` to the hub's `/mcp/`, leave its store empty with
  `SEED_ON_EMPTY=false`, and build the app with `VITE_AGENT_URL` (`api.agentBase`). Without that variable the app
  uses the hub's own agent, as before. A person who picks another hub gets that hub's agent.
- **A hotel's own node.** `tools/hotel_node.py` signs a card into the node's own database with its `contact.mcp`
  address, then hands the signed card to the hub. The agent checks that card against the hub's registry, then asks
  the node for availability and sends the held booking there, and accepts only a receipt signed by the pinned key.
  A card without `contact.mcp` books on the hub as before.

What each one still lacks: [LIMITS.md](LIMITS.md#separate-nodes).

## Trust by design

- **Signatures.** Each card version is signed over canonical JSON (sorted keys, compact separators) with the
  owner's Ed25519 key. Agents verify client-side; the owner studio has a live tamper test.
- **Expiry.** `publish` signs a `valid_until` into every version (`FRESH_DAYS`, 90); discovery leaves out an
  expired card with the reason, and `trust.fresh` says whether it still holds.
- **Attestations.** Third parties sign single claims, shown as "dog-friendly verified".
- **A booking stands on a folder link** (`folders.py`). A connection cannot be made between two agents who have
  no link, and cannot be *opened* until that link is established — asking to link is not linking. The link itself
  carries no content: it opens the manifest, where a linked peer finally sees that the `shared` files exist, and
  reading one still needs a per-path grant from the owner. A booking made with no link would be a booking made on
  what the index claimed rather than on what the two agents agreed, which is the thing this product argues
  against. Rows written before links existed carry none and are still confirmed, scored and counted: the
  precondition is on making a booking, not on reading the log of bookings already made.
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
- **Human in the loop.** The agent holds `hive_book` until the traveller approves (`POST /api/agent/approve`). The
  hold binds the terms the traveller is shown, so a changed price or policy comes back as a new hold for a new yes.
  An edit to anything else, such as the description, does not change the terms and still books.
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

- The hub holds the signing key of every card except one published through `POST /api/hive/cards/signed` from a hotel node (the vision is owner-held keys everywhere).
- DuckDB on local disk with a Postgres snapshot pins the backend to one instance. Fine for a demo.
- No real payments; restaurant table booking is not built yet.
