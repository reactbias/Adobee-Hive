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
| The traveller's money | An agent booking on its own, an edited or replayed approval | The agent holds `hive_book` server-side under a one-time id until the traveller approves; approval books exactly what was held, once | `agent.approve` |
| The traveller's agent | Prompt injection through card text | Tool results are passed as data and the system prompt says so; every tool call is shown to the human; a separate sceptic agent checks the pick against the signed card, and can only warn, never book | `agent.SYSTEM`, `second_opinion.py`, the agent trace |
| The demo's API budgets | Someone draining the Claude or OpenAI key | Calls that may reach either are rate-limited per client IP and in total (`LLM_CALLS_PER_CLIENT_HOUR`, `LLM_CALLS_TOTAL_HOUR`); agent turns are capped | `guard.py`, `AGENT_MAX_TURNS` |
| Demo data | Wiping or flooding it | Reset needs `X-Demo-Token` when `DEMO_RESET_TOKEN` is set; simulated traffic is rate-limited | `main.py` |
| The server | Oversized or malformed input | Request models bound every string and count; dates, stay length (30 nights), guests (20) and text sizes are checked in the Hive core, so MCP calls get the same checks as REST | `main.py`, `hive.py` |
| The database | SQL injection, file access | Parameterised queries only; DuckDB runs with `enable_external_access=false` | `db.py` |
| Secrets | Keys in git | The OpenAI and Claude keys live in `.env` locally and AWS Secrets Manager in the cloud; `.env` is git-ignored; no secrets in the repo or its history | `.gitignore`, `scripts/aws/bootstrap.sh` |
| Errors | Leaking internals | Agent failures are logged server-side; the client gets a plain message | `main.run_agent` |
| Travellers' privacy | Profiling, names leaking | Searches and missed demand are logged as structured features only, never the free-text request (it can hold a name); bookings store only the guest name, dates and price, and the owner overview shows names only with the owner token, initials otherwise. The second opinion sends OpenAI the request text and the public card with `store=false` | `hive.py`, `second_opinion.py` |

The container runs as a non-root user. Dependencies are pinned to exact versions, and CI runs on every push.

## Known limits

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
