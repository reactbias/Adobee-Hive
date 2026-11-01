# Security

Adobee Hive is a hackathon prototype, deployed as a public demo. This page says what is protected, how, and what
is knowingly left open, so reviewers don't have to guess. The product's own gaps — what it does not do yet, as
opposed to what it does not defend — are in [documentation/LIMITS.md](documentation/LIMITS.md).

## Reporting

Open a GitHub issue without exploit details and we will contact you, or tell a Team B6 member at BaselHack.

## What is protected

| Asset | Threat | Protection | Where |
| --- | --- | --- | --- |
| Business facts | Scraped or forged copies, tampered prices, a copy re-signed with someone else's key | Every card version is signed (Ed25519 over canonical JSON). Each business's public key is pinned in the Hive's registry (`owner_keys` in `/.well-known/hive.json`); agents accept a card only if the pinned key signed it, and overwrite the server's own `signature_valid` with their check. The tamper test shows a changed copy and a stranger-signed copy both failing | `hive.verify_pinned`, `agent.verify_card` |
| Reviews | Fake or bulk reviews | A review needs the signed receipt of a confirmed booking, once. That proves the booking, not the stay, and bookings are free ([LIMITS](documentation/LIMITS.md#trust)) | `hive.review` |
| A business's card | Someone else editing it | Owner edits need `X-Owner-Token` when `OWNER_EDIT_TOKEN` is set (Render generates one); identity fields stay locked; cards are capped at 256 kB (`limits.MAX_CARD_BYTES`). Over MCP the same token arrives as a header on the connection — never a tool argument, which would be written into the agent's transcript and its client's logs — is compared in constant time and is never logged or echoed in an answer. The MCP write path **fails closed**: a hub with no `OWNER_EDIT_TOKEN` set publishes nothing over it, and a transport that carries no headers (stdio, in-process) cannot edit at all. Reading the owner's view needs no token and degrades to initials, exactly as the REST route does | `guard.require_secret`, `guard.secret_matches`, `owner.editable`, `owner.apply` |
| A card signed on its own node | A changed copy, a new key taking over the card, or the hub booking or editing it | `POST /api/hive/cards/signed` needs `X-Owner-Token` and a valid signature; the first version pins the key and later ones must match it. The hub holds no private key for the card and refuses to mint one, so it cannot edit or book it. The agent dials `contact.mcp` only from a card that passed the pin check, only on a public address unless `NODE_ALLOW_PRIVATE` is on, and accepts only a receipt signed by the pinned key | `hive.accept_signed`, `agent.node_url` |
| A real business shown without its consent | Misrepresenting it, or someone editing its card | The example cards hold public company information only, no people; each says it is unclaimed, with source and date; owner edits refuse unclaimed cards; an approved action only links to the business's own site and sends it nothing | `domains/examples.py`, `owner._owned`, `explore.approve` |
| A person on the hub | Being found is one thing; being contacted without a yes is another | A person is in `hive_discover` now, found by what they offer and need like any entity, and that is all: a person card holds no contact details at all, a result cannot invent one, an unflagged person card defaults to `confirm` so an introduction waits for them, and no `missed_demand` row is ever written against a person — demand is a signal a business asked for, and against a person it would be a record of the times they were passed over | `domains/hr.py`, `hive.NO_MISSED_DEMAND`, `hive.CONSENT_FIRST_KINDS`, `hub._entity_default` |
| The scout fetching what it should not, or inventing a business | Server-side request forgery; a made-up card | Only http(s) to hosts that resolve to public addresses, checked on every redirect; 6 s timeouts, size cap, at most 5 candidates and 200 compiled cards; a card only when the site answers, carries the name and is not closed; only facts found on the page; the model's own words never reach the card; model rate limit on the endpoint | `domains/scout.py` |
| The person asking | Profiling from questions or mood | The mood is set by the person, never inferred; only the mood, the cards asked about and the count of answers are logged, never the question text; the model, if any, only phrases items already selected from cards, which it is told are data | `explore.ask`, `explore.phrase` |
| The traveller's money | An agent booking on its own, an edited or replayed approval | The agent holds `hive_book` server-side under a one-time id until the traveller approves; approval books exactly what was held, once. The demo's rules-off run stores no hold, so nothing it shows can be approved | `agent.approve` |
| The traveller's agent | Prompt injection through card text | Every tool result is scanned before the agent reads it, and text addressed to agents (EN, DE, FR, IT rules) is withheld, shown to the human and logged for the card's owner; the agent verifies each card against the owner's pinned key itself instead of trusting the source's claim, and never pins keys from extra sources; tool results are passed as data and the system prompt says so; every tool call is shown to the human; a separate verifier agent checks the pick against the signed card, and can only warn, never book | `injection.py`, `agent.HiveConnections`, `agent.SYSTEM`, `second_opinion.py`, the agent trace |
| The demo's API budgets | Someone draining the Claude or OpenAI key | Calls that may reach either are rate-limited per client IP and in total (`LLM_CALLS_PER_CLIENT_HOUR`, `LLM_CALLS_TOTAL_HOUR`), on REST and on MCP alike: `POST /api/ask/scout` and the `hive_scout` MCP tool spend one limiter and the refusal happens before the web search, not after. `POST /api/agent` spends the run's budget once at the door, so the agent's own in-process tool calls are not charged a second time; agent turns are capped | `guard.py`, `AGENT_MAX_TURNS`, `POST /api/ask` |
| A recruiter reading a person's folder | A company's agent getting a CV the person never agreed to share, or being steered by what the CV says | Nothing opens without the person: the folder policy is `agent.md`, `ask` when absent, and `ask` records an `intro_request` and reads nothing. No tool has an approval argument, so the asking agent can not say yes for the person. A yes opens a folder link and grants only files the person admitted, and an answer may quote exactly what `folders.can_read` allows that recruiter: `private` and `hidden` files and `contact.md` are never read, and an answer built from nothing says so. Folder text is matched against and quoted, never obeyed: scoring is rules over words, and a model, when one is used, only widens search terms (`hr_shortlist` / `hr_interview` with `expand`, charged to `llm_calls` per address before the call). The recruiter is an unauthenticated string, which `LIMITS.md` says | `interview.CandidateAgent.consent`, `interview.CandidateAgent.open_for`, `talent.widen`, `domains/recruit.py` |
| An entity this hub should not carry | A card that turned out to be a front, or a person who asked to be taken off | An operator withdraws it with a required reason: gone from `hive.list_cards`, so gone from discovery (out of the matches *and* out of the excluded list), and `hive.book` and `hive.check_availability` refuse it. Never a delete: every signed version stays, so a receipt can still prove what was promised | `removals.py`, `hive.list_cards`, `hive.carried` |
| A change to the hub nobody can account for | A peer or an entity quietly removed, and no record of why | Every peer change and every removal is appended to `hub_admin_log` with its time, subject, reason and which credential was used. Nothing in it is ever rewritten; an undone removal is its own row | `audit.py` |
| Running the hub | Someone else editing the blocklist, admitting entities, or brute-forcing the way in | Admin writes need `X-Admin-Token`: either the static `ADMIN_TOKEN` for curl and CI, or a session token a person gets by posting `ADMIN_PASSWORD` to `/api/admin/login`. Neither configured means every admin write is refused (503), never open. The password is compared with `secrets.compare_digest`, never logged, and has no default in the repo. The login endpoint is limited to 5 attempts per client IP and 30 for the whole backend per 15 minutes, and a lockout says how many seconds to wait. Session tokens are signed with the password plus a per-process secret, expire after `ADMIN_SESSION_MINUTES`, and die on a restart, a password change or a sign-out | `guard.require_admin`, `guard.admin_logins`, `main.admin_login` |
| A folder a peer was linked to | Reading a file the owner never granted, mapping a folder by the shape of the refusals, or a stolen database becoming a stolen folder | A read needs a secret bound to one folder link: 32 bytes from `secrets`, returned exactly once, stored only as SHA-256, never logged. Owner and viewer come from that secret, so the endpoints take no handle and there is nothing to enumerate; the link's state is re-read on every request, so revoking the link stops its reads on the next call. `private` and `hidden` paths are never served, grant or no grant, and a hidden file, an ungranted file and a file that never existed are the identical 404 with the identical sentence. A grant names one path and one handle; `*` is not a path. Reads are capped at `FOLDER_READ_MAX_BYTES`, have no `Range`, are rate-limited **per link** rather than per address, and every served read is a `folder.read` row in the ledger naming the handle that made it | `folder_keys.py`, `folders.can_read`, `main.folders_file`, `guard.folder_reads` |
| A candidate's CV, and the organisation's Hiring Hub key | A second door handing over what the folder read route refuses, or any MCP caller creating positions and starting paid CV extraction | `hr_read_cv` and `hr_submit_cv` apply the read route's rules: `folders.SERVED`, the link's read budget, the size limit, one refusal, and a `folder.read` ledger row. `hr_grant_cv` takes one path, never the whole folder. `hr_create_job` and `hr_submit_cv` need the organisation's key in `X-Hiring-Hub-Key`, and refuse everyone while it is unset | `domains/hr.py` |
| A pending application to join | An unrelated caller withdrawing it, and the ledger crediting the applicant for it | An application id is a lookup, not authority: `GET /api/hub/register/{id}` hands it to anybody. Withdrawal takes a **signed action** under the key the application registered — the application id, the action, a nonce and an expiry, signed with the private half, good for `WITHDRAW_WINDOW_S` — or, for an application whose key the hub holds, a **capability**: 32 bytes from `secrets`, returned exactly once by the submission, stored only as SHA-256 and named in no `SELECT`, so no queue, status page or log can leak it. It travels in `X-Application-Key` rather than a body field or the URL, for the reason the owner token does. No proof means the row is untouched: this route **fails closed**, since there is no secret here that could be "unset". An operator withdrawal is a separate route behind `X-Admin-Token`, credited to the operator with "not by the applicant" in the reason. The transition is conditional on `state = pending` inside its own transaction, so admission and withdrawal have one winner and a replayed proof is inert | `registration.withdraw`, `registration._applicant_proof`, `main.admin_withdraw` |
| An introduction's consent, and its one final score | An unrelated caller faking the owner's yes, or spending the requester's single score | A connection id is in the answer that made it and in the queues any agent reads, so it is a lookup and not authority. **Accept/decline** needs authority over the target: the target's side of this row's folder link (`Authorization: Bearer <link secret>`), a signature under the key the target registered binding connection + action + nonce + expiry, or this hub's `X-Owner-Token` — which is hub-wide and proves the holder may answer for *an* entity here, never for this one, so the row records which proof it was. **Scoring** needs the requester's own link secret and accepts nothing hub-wide, because one person's one report must not be available to whoever holds a shared token; `hub.connect` returns that secret once, on a pending link too, since the requester's only chance to be handed a credential is the answer to its own request. Both doors fail closed and both are the same function behind REST and MCP; a transport carrying no headers (stdio, in-process) proves nothing and is refused. An operator can act through `/api/admin/connections/...`, recorded as the operator's act. Each transition is conditional on the state it came from, inside its own transaction, so two racing callers have one winner | `hub.decide`, `hub.score`, `hub._party_by_link`, `folder_keys.party_of`, `connections._only_from` |
| This hub as a forwarder | A caller using `target_hub` to make this hub send requests somewhere of its choosing | The peer's URL is looked up in this hub's own peer book by hub id — configuration or an admin-authenticated change (`peers.py`) — and a hub id with no URL there is not called at all. One forward, never a chain: the receiving hub is passed `forward=false`, so a forward cannot forward again. Capped at `FORWARD_TIMEOUT_S` and best effort, so a slow peer cannot hold the requester's answer or undo the local record | `hub._peer_url`, `hub._forward`, `main.ConnectBody.forward` |
| Demo data | Wiping or flooding it | Reset needs `X-Demo-Token` when `DEMO_RESET_TOKEN` is set; simulated traffic is rate-limited | `main.py` |
| The server | Oversized or malformed input | Request models bound every string and count; dates, stay length (30 nights), guests (20) and text sizes are checked in the Hive core, so MCP calls get the same checks as REST. Every field, list and total size a Card or an application may carry has a published ceiling, enforced at both doors — `registration.apply` for a new entity and `hive.publish` for every version after — and refused with the limit and the actual size. A request body over 1 MiB is refused with 413 before it is parsed into objects, which neither FastAPI nor uvicorn does on its own, and a card that nests more than 12 levels is refused before anything walks it | `main.py`, `hive.py`, `limits.py` |
| The database | SQL injection, file access | Parameterised queries only; DuckDB runs with `enable_external_access=false` | `db.py` |
| Keys for optional services | A stored key read back, logged, or leaking through an error | Write-only: a key goes into `hub_service_keys` and no endpoint, log or error message returns one. An interface sees presence, a SHA-256 fingerprint (12 hex) and the last four characters, nothing else; `/api/health` and `/api/admin/settings` carry neither. A vendor error is scrubbed of the key before it is stored, because vendors echo a bad key back. Setting, clearing and testing all need `X-Admin-Token` and fail closed | `services.py` |
| Secrets | Keys in git | The OpenAI and Claude keys live in `.env` locally, in the Render dashboard in the cloud, or — set by an operator — in this hub's own database (`services.py`); `.env` and the DuckDB file are git-ignored; no secrets in the repo or its history, and CI scans every push with gitleaks | `.gitignore`, `render.yaml`, `ci.yml`, `services.py` |
| Personal data | The public repo exposing people | Team members are not named (head count only); no emails, phone numbers, account ids, device names, local paths or photo EXIF; whiteboard photos are downscaled, EXIF-stripped, with the Wi-Fi password and handwritten names pixelated | `CONTRIBUTING.md`, `assets/` |
| Ranking | A ruleset that quietly favours a business or hides its effect | Rulesets are signed by their authors and checked against keys pinned in `/.well-known/hive.json`; only additive rules are accepted (require tags, require attestations, show fewer), so none can boost or loosen the floor; every answer names the ruleset and what it changed, and each business it left out says why | `rulesets.py` |
| A card that arrives over another Hive | A relaying hub forging, tampering with or substituting a card | A federated result is verified at the destination, never taken from the carrier: the key comes from the card's own hub registry, fetched directly from that hub, and the card must match `hive.verify_pinned` exactly like a local one. A card that fails is dropped, named in `federation.rejected` with the hub that carried it, and costs that hub trust. A relaying hub can therefore withhold or delay a card, never change one | `federation._verified`, `reputation.record_invalid` |
| An introduction to an entity on another hub | A caller inventing a stranger, or substituting its own copy of a real card, to get a connection recorded against it | The card arrives with the request and is verified here exactly as a relayed search result is: the pinning key comes from the entity's **own** hub's registry, which this hub fetched itself from a URL on its own peer list, so nothing about the key comes from the request. Unsigned, altered, stranger-signed, for a different id, or from a hub whose registry this hub cannot read — all refused with a reason, never admitted with a note. A card this hub carries itself always wins over one a caller brings. `sharing` and the blocklist still decide, so a remote `push` entity cannot be asked for and a blocked entity or hub is still blocked. This hub never says yes on a remote owner's behalf: a remote `confirm` connection is recorded and `connections.confirm` refuses it | `hub._verified_remote`, `federation.pinned_keys_of`, `connections.confirm` |
| The connection ledger calibration reads | A stranger manufacturing introductions, and later scores against them, in the evidence that ranks hubs | Not protected, and recorded as such rather than implied away. `requester` is an unauthenticated string and this hub has no accounts to check it against (#135). What was fixed is the lie: `requester_hub` no longer defaults to the hub *receiving* the request, so a visitor from another hub is no longer written into this hub's ledger as one of its own members. Every row carries `requester_proof` — `member` when this hub carries an entity by that id, `claimed` when the caller named a hub, `none` when nobody said anything — and it is never `member` because of anything in the request. It gates nothing: a gate keyed on an unauthenticated string would refuse honest callers and admit anyone who guessed its shape. See *Known limits* | `hub.requester_origin`, `connections.BY_MEMBER` |
| Rank in a federated answer | A hub buying rank for its members, or inflating its own scores | No hub can boost another's result: the rank is `local_relevance x hub_path_trust x hop_decay`, all three factors in `score_breakdown` with every hub's trust and reasons in the answer. A hub's trust is this hub's own, never a global score; declaring paid placement, missing deadlines or relaying cards that fail verification only lowers it | `federation.py`, `reputation.hub_trust` |
| This hub as an amplifier | A stranger using `radius` to make this hub flood its peers | Peer URLs come from configuration or from an admin-authenticated change (`peers.py`, behind `Depends(admin_only)`), never from the request; the radius is capped at 3 hops and 4 peers per hop, the whole query runs on one time budget, and a search above radius 0 is rate-limited per client and in total **over both transports** — `GET /api/hive/discover` and the `hive_discover` MCP tool spend one limiter, as do `POST /api/hub/connect` and `POST /api/hub/register` and their MCP twins, so exhausting it through one refuses the other. An MCP caller is charged to the peer address the ASGI server observed, never to a tool argument; a call arriving on a transport with no address at all (this repo's own in-process agent) is charged to one named principal rather than exempted | `guard.federated`, `federation.MAX_RADIUS` |
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

- **A node's address is checked by name, not pinned.** With `NODE_ALLOW_PRIVATE` off, the agent checks that a
  card's `contact.mcp` resolves to a public address when it reads the card and again just before connecting, but the
  MCP client resolves the name itself. A name that changes its answer in that moment could still reach a private
  address. Publishing that card takes the owner token and a valid signature. Connecting to the checked IP is the fix.
- **Key custody.** The server holds a signing key for every card except one published from a hotel's own node, so a server compromise could sign the rest. An
  application may bring a `public_key`, which proves who applied and is recorded as `custody: "owner"` with
  `owner_public_key`, but the card version is still signed by the hub's own key and that is the key in
  `owner_keys` that every check uses. The real design moves signing to the owner (a wallet or their Adobe
  account).
- **Trust in the registry.** Agents trust the keys a Hive publishes for its own cards. A forger who controls the Hive
  itself is not caught by this; the real design anchors owner keys outside it (a city or association registry).
- **Owner identity.** One shared owner token protects all cards in the demo; production needs per-owner accounts.
  That is as true of the three `hive_owner_*` MCP tools as of the REST routes: the token proves the holder may
  edit *a* card on this hub, never that they own *this* one, so holding it is holding every card
  ([#135](https://github.com/reactbias/Adobee-Hive/issues/135)).
  The same gap is why `POST /api/folders/keys` takes the hub's admin token: it mints a link secret *on behalf
  of* a handle, which is the operator of a single-operator hub acting for it and is not proof of that handle's
  own identity. The doors that do speak for a party are `POST /api/hub/connect` (for the requester it names)
  and, when it exists, the accept route (for the owner saying yes).
- **A forwarded introduction is an unauthenticated hub-to-hub claim.** When this hub records an
  introduction for one of its members to an entity a peer carries, it tells that peer and names
  itself as the requester's hub. It cannot prove that: `/.well-known/hive.json` publishes per-entity
  `owner_keys` and nothing for the hub itself, so there is no hub identity key to sign the call with.
  The receiving hub therefore records `requester_hub` as `claimed` — which is what it should, and
  which is strictly more honest than what it recorded before, when the requester asserted a name and
  the peer filed it as one of its own members. Anyone who can reach the peer's port can send the same
  call naming any hub. It is the same unanchored hub id named below, reached from the other side, and
  the fix is the same: anchoring hub ids. The peer URL this hub *sends* to is always from its own
  peer list, never from the request, so a caller cannot use `target_hub` to make this hub call an
  address of its choosing.

- **A connection requester is not authenticated, and the ledger it writes is the trust model's own
  input.** `POST /api/hub/connect` and the `hub_connect` MCP tool take `requester` as a free string.
  Anyone who can reach the port can create an introduction under any name, and later score it, in
  the `hub_connections` rows that `calibration.py` reads and that order a hub in the directory and
  in `GET /api/hub/standing`. This is the sharpest gap in the product and it is named here rather
  than dressed up: the trust model's input is writable by strangers.

  What exists is honesty about it, not a fix. `requester_proof` on every row says what the hub
  established — `member` only when it carries an entity by that id, which is a check on the *name*
  and not on the caller — so a reader can discount a row instead of being misled by one. The
  default that made a visitor look like a member is gone. Nothing is gated on the proof, because a
  gate on an unauthenticated string is a gate that is not there. The fix is per-owner
  authorization ([#135](https://github.com/reactbias/Adobee-Hive/issues/135)), and the step before
  it is an agent asking its *own* hub, which can vouch for its member
  ([#159](https://github.com/reactbias/Adobee-Hive/issues/159)).
- **A withdrawal capability is a bearer secret, and over MCP it is handed out in a transcript.**
  The applicant's own route reads it from a header, so it stays out of URLs and proxy logs — but the
  submission has to hand it over once, and when an agent applies on its person's behalf that answer
  is written into the agent's transcript and its client's logs. `hub_connect` already returns a
  folder link secret the same way. Anything that can read those logs can withdraw that application
  until it is decided. An application that brings its own `public_key` has no capability at all and
  is the stronger path for exactly this reason. What neither path proves is that the *person* holds
  the key or the secret: the hub checks a proof, never an identity.

  Nothing is ever revoked, either. A capability lives as long as the application is pending, and
  there is no route to roll one over if its holder thinks it leaked; the operator's own withdrawal
  is the way out.
- **A link secret proves a side, not a person.** It is what makes an introduction's two decisions
  checkable at all, and it is a bearer secret: minted once, handed to the requester in the connect
  answer, and over MCP that answer lands in the agent's transcript and its client's logs. Anything
  that can read those can score that introduction. `POST /api/folders/keys` also mints one *on
  behalf of* a handle behind the admin token, so on a single-operator hub the operator can mint
  either side's credential — which is the honest shape of a hub with no per-owner accounts (#135),
  not a separate hole.

- **An owner token answers for any entity on the hub.** For accept/decline it is accepted as the
  weakest of three proofs, and the row says `owner token` rather than `link secret` so a per-entity
  yes and a hub-wide one stay distinguishable afterwards. A card that registered its own key can be
  answered with a signature instead, which is per-entity and which this hub cannot forge; a card
  whose key the hub holds has no such option and is told so. It is refused for scoring outright.

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
- **A service key an operator stores is kept in the clear.** It goes into the hub's DuckDB file, which
  means it is as protected as that host's disk and no more: there is no envelope encryption and no secret
  manager. Nothing reads it back out over HTTP and nothing logs it, but a reader of the database file has
  it. The admin panel says exactly this next to the field rather than implying a protection that was not
  built; an operator who needs more should keep using the deployment's environment, which this still
  honours as the seed. Per-hub envelope encryption is the fix.
- **Five `/api/admin/*` reads need no credential.** `overview`, `settings`, `neighbours` and `blocklist` are open
  on purpose: what a hub blocks, who it peers with and how it describes itself is what it should be willing to say
  out loud, and the public node view is built from two of them. `GET /api/admin/applications` is in that set and
  should not be — it carries each applicant's id, name, public key and the checks that ran. Every admin **write**
  fails closed.
- **Open by design.** Reading cards, searching, checking availability and booking are public, for agents and people
  alike, as on any booking site. CORS is `*` for the same reason. MCP host-header checks are off because the host
  serves the public domain; the MCP surface exposes only these public actions.
- **Payments** are out of scope: bookings say "pay at the property".
