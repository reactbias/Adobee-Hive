# Known limits

What Adobee Hive does not do, stated before anybody has to find out. Every line below was checked against the
code on `main`; where a page elsewhere promises more than this, that page is wrong and this one is right.

The repository already names its security gaps in [SECURITY.md](../SECURITY.md#known-limits) and will not repeat
them here. This page is the product's gaps: the places where a reviewer could reasonably believe something works
better than it does.

## Discovery

**Matching gets you two out of five, not five out of five.** `app/semantic.py` is a score component in
`hive.discover` now, so "haircut" does find *"Cut, wash and finish"*. Measured against the answer key in
[`testdata/`](../testdata/README.md) — 41 queries, none sharing a searchable word with its target — that is
**19/41 first and 30/41 in the top three**, against `0/41` for the substring matching it replaced. Twenty-two
of the forty-one are still not first. The provider is hand-built (accent-folded stems, a four-language concept
table, German compound splitting, character trigrams, cosine above a named floor), so a trade nobody has
written a card for yet matches only by stem or trigram.

**There is no embedding provider.** `semantic._embedding_provider()` returns `None` on purpose rather than half
an implementation, so a hub with an API key searches exactly as well as one without, and `GET /api/health`
reports `semantic: offline` either way. What is built is the seam: a `Provider` subclass with a name, an
`available()` that reads its key through `config`, and an `encode()` that caches per card version.

**The literal half of the scoring only knows German umlauts.** `hive.discover` tokenises a query with
`[a-zäöü]+` and keeps terms longer than three characters, so `café` and `crème` tokenise to nothing and a
French or Italian query scores zero on both `text_relevance` and `offers_needs`. Semantic search answers it
anyway, because it accent-folds — but the literal components are blind to two of the four languages the corpus
is written in. `hive.STOPWORDS` is 21 words to `semantic.STOPWORDS`' several hundred, for the same reason:
filler words like *where* and *someone* are scoring query terms and earn offer points off any card whose prose
happens to contain them.

**Reputation is paid without a relevance test.** A match's score adds `reputation.business_points` — verified
reviews and attestations — whatever the query was. An entity that fails no hard constraint can therefore rank on
review points alone, above a less-reviewed entity that actually offers the thing asked for. The constraint
component was fixed for the same class of bug (it is now earned, never granted); this one is not.

**The app exposes neither `kind` nor `looking_for`.** Both are real parameters of `GET /api/hive/discover` and
`hive_discover`, and both matter: `kind` narrows, and `looking_for` chooses which side of the market to search.
The web app sends neither. On the traveller page the only search controls are the free-text box and the three-step
reach. To search by need rather than offer today you call the API or the MCP tool.

## Trust

**`verification` never rises above `signed`.** The ladder in `registration.py` is `none`, `signed`, `domain`,
`identity`. `verification_for()` returns only `signed` or `none`, because `signed` is exactly what a valid
signature establishes, and nothing in the hub confirms a proof: a `dns-txt`, `rel-me` or `email` proof is recorded
unverified and raises nothing. That is deliberate — a hub that blocks on a DNS lookup falls over when a registrar
does — but it means the top two rungs of the ladder are unreachable today.

**The hub holds a signing key for every card, including the ones that brought their own.** The onboarding panel
generates an Ed25519 keypair in the browser, offers the private half as a download and signs the application's
canonical JSON with it (`lib/signing.ts`), so `custody: "owner"` is reachable without a terminal. That proves the
applicant holds the private half, and it is recorded on the card as `owner_public_key`, which a peer can see. The card version itself is still signed
by a key `hive.publish` generates and keeps in `hive_keys`, and that is the key published in
`/.well-known/hive.json` under `owner_keys` and used by every signature check. So the jury answer is still *the
server, for the demo* — registration narrows the gap by pinning who applied, it does not close it. Owner-held
signing keys are in [VISION.md](VISION.md#beyond-the-weekend).

**Calibration does not reach the search rank.** A federated result is ranked
`local_relevance × hub_path_trust × hop_decay`, and `hub_path_trust` comes from `reputation.py` — declared versus
observed vetting, paid placement, availability, latency, cards that failed verification here. The sharper
measurement, `calibration.py`'s published-minus-realised error, orders `GET /api/hub/standing`, the neighbours
table and the hub directory, and is what a person choosing a hub reads. It is not a factor in that product yet.

**Hub reputation resets; hub calibration needs evidence nothing in the demo produces.** `reputation.py` keeps its
observations in a module-level dict, so a restart returns every peer to trust on first use. Calibration does
persist — it is computed from the `hub_connections` table — but a verdict needs `MIN_EVIDENCE`, three scored
introductions, and a score only exists after a person has gone to a real meeting and come back to say how it went.
On a fresh hub every peer therefore reads **unproven**, which is honest and is also most of what the directory
shows.

## The folder link

**It links two folders on one disk.** `app/folders.py` is the step between the index and the booking, and it is
real: a link is handle to handle and carries no content, a linked peer sees the `shared` files the Card never
mentioned, a grant is per path, and `private` and `hidden` paths are counted and never named — not in a manifest,
not in a refusal. What it is not is two machines. The only implementation today is `LocalFolderLink`, which links
the folders in [`testdata/vaults/`](../testdata/README.md) inside this process with its links and grants in
DuckDB, so no key is exchanged and nothing is encrypted. `FOLDER_LINK=claudeconnect` is accepted and falls back to
local with the reason in `GET /api/health`, because the adapter for the real library is not built yet.

**Nothing in the app drives it.** There is no `/api/folders/*` surface. A link is made by `POST /api/hub/connect`,
which does the handshake itself and returns the manifest it opened; a grant can only be given from Python. The
endpoints a panel would need are proposed in issue #116.

## Running a hub

**A federated search in the first half minute of a fresh `lan.sh up` comes back local-only, and the peers do not
recover.** Each hub asks its peers who they are at startup, before the corpus is seeded, and caches a profile
whose `owner_keys` is empty. `federation._profile` reuses that cache until the background refresh replaces it
(`PEER_ASK_SECONDS`, 30 s), so until then every relayed card fails `hive.verify_pinned` — and `_verified` charges
each failure to the carrier through `reputation.record_invalid`. Because reputation is a module-level dict, that
verdict lasts for the life of the process: a peer reads `trust 0.05` with "41 of 82 relayed cards failed
verification here", and the same match's `federated_score` drops from 4.39 to 0.36. Poll
`GET /api/hub/directory` until a peer's `entities` is non-zero before the first federated search, or restart the
hubs if it has already happened. Reproduced twice; see
[SEARCH_API.md](SEARCH_API.md#where-the-docs-and-the-code-disagree).

**One shared password, no audit trail.** `ADMIN_PASSWORD` is a single secret for the whole hub, like the owner
token. There are no operator accounts, so an admitted or refused application records `decided_by: "admin"` and
nothing about which person decided it. Sessions are bearer tokens in `sessionStorage`.

**Five admin reads need no credential.** `GET /api/admin/overview`, `/api/admin/settings`, `/api/admin/neighbours`,
`/api/admin/blocklist` and `/api/admin/applications` are served to anyone. Three of them are open on purpose — what
a hub blocks, who it peers with and how it describes itself is what it should be willing to say out loud, and the
public node view is built from two of them. The admission queue is the one that does not belong in that set: it
carries each applicant's id, name, public key and the checks that ran. Every admin **write** does fail closed.

**There is no second deployed hub.** The hop machinery is real and tested (`tests/test_federation.py` drives it
through an in-process transport), but `https://adobee-hive.onrender.com` has no `HIVE_PEER_URLS`, so a search
against the live backend stays local whatever the reach control says. Three peered hubs on one machine is
what [`lan.sh`](../lan.sh) is for; see [DEVELOPER.md](DEVELOPER.md#three-hubs-on-one-machine-lansh).

## The deployed demo

**An https page cannot call an http hub.** Picking a Hive in the finder does now move the app: the hub's base URL
is stored for the tab and `api.ts` resolves its base per call. The one pick that cannot be honoured is a hub on
plain http, because a browser will not let an https page call one — so the GitHub Pages build can only reach https
hubs, and the finder refuses such a row with that reason rather than appearing to switch. `VITE_API_URL` is the
hub a visitor talks to before they pick one. A LAN demo is unaffected, because `lan.sh` serves the page over http
too, with the hub proxied same-origin.

**One instance, in memory.** Rate limits, held bookings, held hand-offs and hub reputation live in the process:
they reset on a restart and would not be shared between two instances. DuckDB on local disk with a Postgres
snapshot pins the backend to one instance anyway. Fine for a demo, and the reason a redeploy clears an admin
lockout.

## Not built

- **Payments.** A booking says "pay at the property". Nothing is charged.
- **Restaurant tables.** The café card carries no units, so it is findable and not bookable.
- **Claiming an unclaimed card.** The scout compiles cards from public websites and marks them unclaimed; there is
  no flow for the business to take one over.
- **The injection guard is a rule set, not a proof.** New phrasings can slip past it, which is why it is one layer
  of several (see [SECURITY.md](../SECURITY.md#known-limits)).

## Why this page exists

A prototype that names its own gaps can be checked. One that does not has to be taken on trust, which is the
opposite of the thing being built here. If you find a claim anywhere in `documentation/` that this page
contradicts, the code decides — and the claim is a bug worth an issue.
