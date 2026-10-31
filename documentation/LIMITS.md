# Known limits

What Adobee Hive does not do, stated before anybody has to find out. Every line below was checked against the
code on `main`; where a page elsewhere promises more than this, that page is wrong and this one is right.

The repository already names its security gaps in [SECURITY.md](../SECURITY.md#known-limits) and will not repeat
them here. This page is the product's gaps: the places where a reviewer could reasonably believe something works
better than it does.

## Discovery

**Similarity is bounded, not general language understanding.** Discovery combines literal matching with the
offline similarity provider (stems, a four-language concept table and character trigrams). The concept vocabulary
is hand-built; unseen language and inference can still miss. The optional embedding provider is not implemented.

**Room intent is conservative.** The REST discovery door recognises explicit hotel/room language and reuses
the stay parser for stated constraints, excluding a declared guest name from ranking. Explicit parameters win;
absent dates are not filled with the planner's default weekend. Generic transport, service and needs requests
stay generic. This is a lexical intent boundary, not a general parser; API/MCP callers should supply structured
constraints when available.

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

**Nothing drives it yet.** There is no `/api/folders/*` surface, and no caller inside the hub: a link and a grant
can only be made from Python. The booking path starts requiring a link in the change after this one, and the
endpoints a panel would need are proposed in issue #116.

## Running a hub

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
