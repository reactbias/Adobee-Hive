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
| A business's card | Someone else editing it | Owner edits need `X-Owner-Token` when `OWNER_EDIT_TOKEN` is set (the AWS bootstrap generates one); identity fields stay locked; cards are capped at 64 kB | `guard.py`, `owner.apply` |
| A real business shown without its consent | Misrepresenting it, or someone editing its card | The example cards hold public company information only, no people; each says it is unclaimed, with source and date; owner edits refuse unclaimed cards; an approved action only links to the business's own site and sends it nothing | `domains/examples.py`, `owner._owned`, `explore.approve` |
| The person asking | Profiling from questions or mood | The mood is set by the person, never inferred; only the mood, the cards asked about and the count of answers are logged, never the question text; the model, if any, only phrases items already selected from cards, which it is told are data | `explore.ask`, `explore.phrase` |
| The traveller's money | An agent booking on its own, an edited or replayed approval | The agent holds `hive_book` server-side under a one-time id until the traveller approves; approval books exactly what was held, once. The demo's rules-off run stores no hold, so nothing it shows can be approved | `agent.approve` |
| The traveller's agent | Prompt injection through card text | Every tool result is scanned before the agent reads it, and text addressed to agents (EN, DE, FR, IT rules) is withheld, shown to the human and logged for the card's owner; the agent verifies each card against the owner's pinned key itself instead of trusting the source's claim, and never pins keys from extra sources; tool results are passed as data and the system prompt says so; every tool call is shown to the human; a separate sceptic agent checks the pick against the signed card, and can only warn, never book | `injection.py`, `agent.HiveConnections`, `agent.SYSTEM`, `second_opinion.py`, the agent trace |
| The demo's API budgets | Someone draining the Claude or OpenAI key | Calls that may reach either are rate-limited per client IP and in total (`LLM_CALLS_PER_CLIENT_HOUR`, `LLM_CALLS_TOTAL_HOUR`); agent turns are capped | `guard.py`, `AGENT_MAX_TURNS`, `POST /api/ask` |
| Demo data | Wiping or flooding it | Reset needs `X-Demo-Token` when `DEMO_RESET_TOKEN` is set; simulated traffic is rate-limited | `main.py` |
| The server | Oversized or malformed input | Request models bound every string and count; dates, stay length (30 nights), guests (20) and text sizes are checked in the Hive core, so MCP calls get the same checks as REST | `main.py`, `hive.py` |
| The database | SQL injection, file access | Parameterised queries only; DuckDB runs with `enable_external_access=false` | `db.py` |
| Secrets | Keys in git | The OpenAI and Claude keys live in `.env` locally and AWS Secrets Manager in the cloud; `.env` is git-ignored; no secrets in the repo or its history, and CI scans every push with gitleaks | `.gitignore`, `scripts/aws/bootstrap.sh`, `ci.yml` |
| Personal data | The public repo exposing people | Team members appear by name only; no emails, phone numbers, account ids, device names, local paths or photo EXIF; whiteboard photos are downscaled, EXIF-stripped, with the Wi-Fi password pixelated | `CONTRIBUTING.md`, `assets/` |
| Ranking | A ruleset that quietly favours a business or hides its effect | Rulesets are signed by their authors and checked against keys pinned in `/.well-known/hive.json`; only additive rules are accepted (require tags, require attestations, show fewer), so none can boost or loosen the floor; every answer names the ruleset and what it changed, and each business it left out says why | `rulesets.py` |
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
- **Rate limits** are kept in memory, which is fine because the backend runs as one instance (DuckDB on local disk).
- **Open by design.** Reading cards, searching, checking availability and booking are public, for agents and people
  alike, as on any booking site. CORS is `*` for the same reason. MCP host-header checks are off because App Runner
  serves the public domain; the MCP surface exposes only these public actions.
- **react-router 6.30.6** still has two moderate advisories that are fixed only in v7: one affects server-side
  rendering, which we don't use, and the other affects links built from untrusted paths, which we don't build. The
  move to v7 is scheduled for after the hackathon.
- **Payments** are out of scope: bookings say "pay at the property".
