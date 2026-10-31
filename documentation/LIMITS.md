# Known limits

What Adobee Hive does not do, stated before anybody has to find out. Every line below was checked against the
code on `main`; where a page elsewhere promises more than this, that page is wrong and this one is right.

The repository already names its security gaps in [SECURITY.md](../SECURITY.md#known-limits) and will not repeat
them here. This page is the product's gaps: the places where a reviewer could reasonably believe something works
better than it does.

## Discovery

**Matching is literal.** `hive.discover` scores a card by substring: a query term appears in the card's name,
tagline, description, features, `offers` or `needs`, or it does not. So "haircut" misses *"Cut, wash and
finish"*, and "hotel" misses *"Gästehaus"*. The corpus in [`testdata/`](../testdata/README.md) is built to show
exactly where this gives up, with an answer key of queries that share no word with their target.

**Semantic search is built and not connected.** `app/semantic.py` is a working similarity provider — accent-folded
stems, a four-language concept table, character trigrams, cosine above a named floor, no key and no network — with
its own tests. Nothing in `app/` imports it. It is not a score component in `hive.discover`, and `GET /api/health`
does not report which provider is in use. Wiring it in is one change in `discover`, and until that lands the
sentence to say out loud is "the module is there, the search does not use it yet".

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

**The hub holds a signing key for every card, including the ones that brought their own.** Bringing a
`public_key` to `POST /api/hub/register` proves the applicant holds the private half, and it is recorded on the
card as `owner_public_key` with `custody: "owner"`, which a peer can see. The card version itself is still signed
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
through an in-process transport), but `https://adobee-hive.onrender.com` has no `HIVE_PEER_URLS`, so every search
against the live backend is a radius-0 search whatever the reach control says. Three peered hubs on one machine is
what [`lan.sh`](../lan.sh) is for; see [DEVELOPER.md](DEVELOPER.md#three-hubs-on-one-machine-lansh).

## The deployed demo

**An https page cannot call an http hub.** The frontend's backend URL is `VITE_API_URL`, baked in at build time.
The GitHub Pages build is served over https, so it can only talk to an https backend — a hub on a LAN address or
on plain http is unreachable from it, and the browser blocks the request rather than reporting it. That is why
`lan.sh` serves the app over http from `vite preview` with the hub proxied same-origin instead of pointing a
hosted page at it.

**Choosing a Hive in the finder does not change which backend answers.** `InstanceFinder` reads
`GET /api/hub/directory` and remembers the pick in `sessionStorage`, and the page says on screen that this build
talks to one backend whatever you pick. Picking a hub is the right screen and the right data; routing the app at
the hub you picked is not built.

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
