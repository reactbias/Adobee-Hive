# Security

Adobee Hive is a hackathon prototype, deployed as a public demo. This page says what is protected, how, and what
is knowingly left open, so reviewers don't have to guess.

## Reporting

Open a GitHub issue without exploit details and we will contact you, or tell a Team B6 member at BaselHack.

## What is protected

| Asset | Threat | Protection | Where |
| --- | --- | --- | --- |
| Business facts | Scraped or forged copies, tampered prices, a copy re-signed with someone else's key | Every card version is signed (Ed25519 over canonical JSON). Each business's public key is pinned in the Hive's registry (`owner_keys` in `/.well-known/hive.json`); agents accept a card only if the pinned key signed it, and overwrite the server's own `signature_valid` with their check. The tamper test shows a changed copy and a stranger-signed copy both failing | `hive.verify_pinned`, `agent.verify_card` |
| Reviews | Fake or bulk reviews | A review needs the signed receipt of a real booking, once | `hive.review` |
| A business's card | Someone else editing it | Owner edits need `X-Owner-Token` when `OWNER_EDIT_TOKEN` is set (Render generates one); identity fields stay locked; cards are capped at 64 kB | `guard.py`, `owner.apply` |
| A real business shown without its consent | Misrepresenting it, or someone editing its card | The example cards hold public company information only, no people; each says it is unclaimed, with source and date; owner edits refuse unclaimed cards; an approved action only links to the business's own site and sends it nothing | `domains/examples.py`, `owner._owned`, `explore.approve` |
| A person on the hub | Being found is one thing; being contacted without a yes is another | A person is in `hive_discover` now, found by what they offer and need like any entity, and that is all: a person card holds no contact details at all, a result cannot invent one, an unflagged person card defaults to `confirm` so an introduction waits for them, and no `missed_demand` row is ever written against a person — demand is a signal a business asked for, and against a person it would be a record of the times they were passed over | `domains/hr.py`, `hive.NO_MISSED_DEMAND`, `hive.CONSENT_FIRST_KINDS`, `hub._entity_default` |
| The scout fetching what it should not, or inventing a business | Server-side request forgery; a made-up card | Only http(s) to hosts that resolve to public addresses, checked on every redirect; 6 s timeouts, size cap, at most 5 candidates and 200 compiled cards; a card only when the site answers, carries the name and is not closed; only facts found on the page; the model's own words never reach the card; model rate limit on the endpoint | `domains/scout.py` |
| The person asking | Profiling from questions or mood | The mood is set by the person, never inferred; only the mood, the cards asked about and the count of answers are logged, never the question text; the model, if any, only phrases items already selected from cards, which it is told are data | `explore.ask`, `explore.phrase` |
| The traveller's money | An agent booking on its own, an edited or replayed approval | The agent holds `hive_book` server-side under a one-time id until the traveller approves; approval books exactly what was held, once. The demo's rules-off run stores no hold, so nothing it shows can be approved | `agent.approve` |
| The traveller's agent | Prompt injection through card text | Every tool result is scanned before the agent reads it, and text addressed to agents (EN, DE, FR, IT rules) is withheld, shown to the human and logged for the card's owner; the agent verifies each card against the owner's pinned key itself instead of trusting the source's claim, and never pins keys from extra sources; tool results are passed as data and the system prompt says so; every tool call is shown to the human; a separate verifier agent checks the pick against the signed card, and can only warn, never book | `injection.py`, `agent.HiveConnections`, `agent.SYSTEM`, `second_opinion.py`, the agent trace |
| The demo's API budgets | Someone draining the Claude or OpenAI key | Calls that may reach either are rate-limited per client IP and in total (`LLM_CALLS_PER_CLIENT_HOUR`, `LLM_CALLS_TOTAL_HOUR`); agent turns are capped | `guard.py`, `AGENT_MAX_TURNS`, `POST /api/ask` |
| An entity this hub should not carry | A card that turned out to be a front, or a person who asked to be taken off | An operator withdraws it with a required reason: gone from `hive.list_cards`, so gone from discovery (out of the matches *and* out of the excluded list), and `hive.book` and `hive.check_availability` refuse it. Never a delete: every signed version stays, so a receipt can still prove what was promised | `removals.py`, `hive.list_cards`, `hive.carried` |
| A change to the hub nobody can account for | A peer or an entity quietly removed, and no record of why | Every peer change and every removal is appended to `hub_admin_log` with its time, subject, reason and which credential was used. Nothing in it is ever rewritten; an undone removal is its own row | `audit.py` |
| Running the hub | Someone else editing the blocklist, admitting entities, or brute-forcing the way in | Admin writes need `X-Admin-Token`: either the static `ADMIN_TOKEN` for curl and CI, or a session token a person gets by posting `ADMIN_PASSWORD` to `/api/admin/login`. Neither configured means every admin write is refused (503), never open. The password is compared with `secrets.compare_digest`, never logged, and has no default in the repo. The login endpoint is limited to 5 attempts per client IP and 30 for the whole backend per 15 minutes, and a lockout says how many seconds to wait. Session tokens are signed with the password plus a per-process secret, expire after `ADMIN_SESSION_MINUTES`, and die on a restart, a password change or a sign-out | `guard.require_admin`, `guard.admin_logins`, `main.admin_login` |
| Demo data | Wiping or flooding it | Reset needs `X-Demo-Token` when `DEMO_RESET_TOKEN` is set; simulated traffic is rate-limited | `main.py` |
| The server | Oversized or malformed input | Request models bound every string and count; dates, stay length (30 nights), guests (20) and text sizes are checked in the Hive core, so MCP calls get the same checks as REST | `main.py`, `hive.py` |
| The database | SQL injection, file access | Parameterised queries only; DuckDB runs with `enable_external_access=false` | `db.py` |
| Secrets | Keys in git | The OpenAI and Claude keys live in `.env` locally and in the Render dashboard in the cloud; `.env` is git-ignored; no secrets in the repo or its history, and CI scans every push with gitleaks | `.gitignore`, `render.yaml`, `ci.yml` |
| Personal data | The public repo exposing people | Team members are not named (head count only); no emails, phone numbers, account ids, device names, local paths or photo EXIF; whiteboard photos are downscaled, EXIF-stripped, with the Wi-Fi password and handwritten names pixelated | `CONTRIBUTING.md`, `assets/` |
| Ranking | A ruleset that quietly favours a business or hides its effect | Rulesets are signed by their authors and checked against keys pinned in `/.well-known/hive.json`; only additive rules are accepted (require tags, require attestations, show fewer), so none can boost or loosen the floor; every answer names the ruleset and what it changed, and each business it left out says why | `rulesets.py` |
| A card that arrives over another Hive | A relaying hub forging, tampering with or substituting a card | A federated result is verified at the destination, never taken from the carrier: the key comes from the card's own hub registry, fetched directly from that hub, and the card must match `hive.verify_pinned` exactly like a local one. A card that fails is dropped, named in `federation.rejected` with the hub that carried it, and costs that hub trust. A relaying hub can therefore withhold or delay a card, never change one | `federation._verified`, `reputation.record_invalid` |
| Rank in a federated answer | A hub buying rank for its members, or inflating its own scores | No hub can boost another's result: the rank is `local_relevance x hub_path_trust x hop_decay`, all three factors in `score_breakdown` with every hub's trust and reasons in the answer. A hub's trust is this hub's own, never a global score; declaring paid placement, missing deadlines or relaying cards that fail verification only lowers it | `federation.py`, `reputation.hub_trust` |
| This hub as an amplifier | A stranger using `radius` to make this hub flood its peers | Peer URLs come from configuration only, never from the request; the radius is capped at 3 hops and 4 peers per hop, the whole query runs on one time budget, and a search above radius 0 is rate-limited per client and in total | `guard.federated`, `federation.MAX_RADIUS` |
| What was promised | A business changing its price or policy after the booking and denying the old terms | Every signed card version is kept; the receipt pins the version and its digest, and `hive_what_was_promised` returns that version, signature included, only to a holder of the receipt | `hive.what_was_promised` |
| Standing requests | Spam to travellers, profiling who waits | An agent leaves one only when nothing fits and its traveller asked; it holds the structured ask, no name or free text; the agent's token is stored as a hash; requests end at check-in or after 30 days, 500 open at most; each business sends one offer per request, only when its signed card fits; owners see counts and budgets, never a single request | `waiting.py` |
| Errors | Leaking internals | Agent failures are logged server-side; the client gets a plain message | `main.run_agent` |
| Travellers' privacy | Profiling, names leaking | Searches and missed demand are logged as structured features only, never the free-text request (it can hold a name); bookings store only the guest name, dates and price, and the owner overview shows names only with the owner token, initials otherwise. The second opinion sends OpenAI the request text and the public card with `store=false` | `hive.py`, `second_opinion.py` |

The container runs as a non-root user. Dependencies are pinned to exact versions, and CI runs on every push.

## Known limits

- **The injection guard is a rule set, not a proof.** New phrasings can slip past it, which is why it is one layer
  of several: the signature check, data-not-instructions prompting, the second opinion and the human's approval. The
  demo's unverified mirror (`mirror.py`) and the rules-off run are reachable only through the `scenario` and `rules`
  options of `POST /api/agent`; the rules-off run is scripted, never calls Claude and never sends a booking.

- **Key custody.** The server holds each owner's signing key, so a server compromise could sign cards. The real
  design moves keys to the owner (a wallet or their Adobe account).
- **Trust in the registry.** Agents trust the keys a Hive publishes for its own cards. A forger who controls the Hive
  itself is not caught by this; the real design anchors owner keys outside it (a city or association registry).
- **Owner identity.** One shared owner token protects all cards in the demo; production needs per-owner accounts.
- **A carrier can still name the wrong origin.** A relayed result says which hub it came from, and this hub
  fetches that hub's registry directly, so a tampered card cannot pass. What is not yet anchored is the hub id
  itself: a hostile carrier could point at a registry it controls and present a card of its own as another hub's.
  It cannot forge an existing business's card that way, only offer one nobody else has. Anchoring hub ids (a hub
  directory, or DNS) is the fix.
- **Hub reputation is per process and per hub.** It is an opinion this backend formed since it started, not a
  published score; a restart means every peer starts again at trust on first use. That is deliberate, but it also
  means a hub that misbehaved before a restart gets a clean slate.
- **A peer's own ranking is still its own.** This hub re-verifies every card, but it cannot recompute a peer's
  availability or relevance from outside, so a peer's `local_relevance` is taken as given and discounted by hub
  trust. That is what makes hub trust, and the incentive behind it, load-bearing.
- **Rate limits** are kept in memory, which is fine because the backend runs as one instance (DuckDB on local disk).
  They also reset on a restart, so a redeploy clears a lockout.

- **The admin login's global cap is a denial-of-service lever.** 30 guesses per 15 minutes for the whole backend
  stops a botnet with a fresh IP per attempt from grinding the password, and the same cap lets that botnet keep the
  real operator out. The static `ADMIN_TOKEN` is the way back in while it is locked, and it is not rate-limited.
- **An admin session token is a bearer token.** Anything that can read it — a browser extension, a shoulder, a
  copied URL if someone pastes one — can administer the hub until it expires. It is kept in `sessionStorage` for the
  tab only, never `localStorage`, and the panel signs out on a 401 or 403. There is no CSRF token, which is safe only
  because the credential travels in a custom header rather than a cookie.
- **The password is one shared secret for the whole hub**, like the owner token: no operator accounts, so no audit
  trail of who admitted or refused what beyond `decided_by: "admin"`. The admin ledger (`audit.py`) records every
  removal and peer change with its time, subject, reason and *which credential* was used — the static token, or a
  browser session minted from the password — because that is the most this design can honestly say. It cannot tell
  two operators apart, so `audit.WHO_LIMIT` is printed next to the rows rather than letting a reader assume
  otherwise. Per-operator accounts are the fix.
- **Open by design.** Reading cards, searching, checking availability and booking are public, for agents and people
  alike, as on any booking site. CORS is `*` for the same reason. MCP host-header checks are off because the host
  serves the public domain; the MCP surface exposes only these public actions.
- **Payments** are out of scope: bookings say "pay at the property".
