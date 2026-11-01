# Known limits

What Adobee Hive does not do, stated before anybody has to find out. Every line below was checked against the
code on `main`; where a page elsewhere promises more than this, that page is wrong and this one is right.

The repository already names its security gaps in [SECURITY.md](../SECURITY.md#known-limits) and will not repeat
them here. This page is the product's gaps: the places where a reviewer could reasonably believe something works
better than it does.

## Discovery

**Matching gets you just over half at first place, not five out of five.** `app/semantic.py` is a score
component in `hive.discover` now, so "haircut" does find *"Cut, wash and finish"*. Measured against the answer
key in [`testdata/`](../testdata/README.md) — 41 queries, none sharing a searchable word with its target —
that is **24/41 first and 33/41 in the top three**, against `0/41` for the substring matching it replaced.
Seventeen of the forty-one are still not first. The provider is hand-built (accent-folded stems, a
four-language concept table, German compound splitting, character trigrams, cosine above a named floor), so a
trade nobody has written a card for yet matches only by stem or trigram.

**The semantic component pays per query word covered, so ties are the normal case.** A match is worth a whole
number of points per word of the question it covers, up to `SEMANTIC_CAP`, and how *close* it was does not
enter the score. Nine lodgings cover "hostel, bunk, beds" identically and all collect the cap. Closeness now
breaks those ties in the sort, which is a weak signal rather than a strong one: for "hostel with bunk beds for
a school group" it puts the actual hostel at 9th, because `Mehrbettzimmer A` normalises worse than
`Courtyard single`. A query whose answer is a cap-saturated tie is not really being ranked.

**There is no embedding provider.** `semantic._embedding_provider()` returns `None` on purpose rather than half
an implementation, so a hub with an API key searches exactly as well as one without, and `GET /api/health`
reports `semantic: offline` either way. What is built is the seam: a `Provider` subclass with a name, an
`available()` that reads its key through `config`, and an `encode()` that caches per card version.

**The stopword list is hand-built, so a filler word nobody listed is still evidence.** Both search paths now
tokenise with `semantic.content_words` and share the single `semantic.STOPWORDS`, which is folded so that
"für" and "fuer" are one entry. That closed the cases two user tests found — interrogatives, possessives and
the inflected forms of light verbs in all four languages — but the list is a list: a filler word in a
language or register nobody typed at it is a scoring term until somebody adds it. There is no frequency
analysis over the corpus behind it.

**Room intent is conservative.** The REST discovery door recognises explicit hotel/room language and reuses
the stay parser for stated constraints, excluding a declared guest name from ranking. Explicit parameters win;
absent dates are not filled with the planner's default weekend. Generic transport, service and needs requests
stay generic. This is a lexical intent boundary, not a general parser; API/MCP callers should supply structured
constraints when available.

**Reputation is still paid without a relevance test; it can no longer pass for an answer.** A match's score
adds `reputation.business_points` — verified reviews and attestations — whatever the query was, so four Basel
hotels score 1-2 on every query there is, including a nonsense one. The doors no longer present those rows as
results: `GET /api/hive/discover` and `hive_discover` filter on `hive.relevance`, the five components the ask
itself earned, and report `matched` over `considered`. What is **not** fixed is the ranking *among* entities
that did earn something — a well-reviewed one still gets its points on top, so it can outrank a less-reviewed
one that offers more of what was asked for. `hive.discover()` in-process is also unfiltered by design: the eval
tools and `federation.py`'s scorer read the whole ranked list.

**"Nothing matched" only tests the words when nothing else was asked.** Any `near`, date, price or feature that
earns points counts as an answer, so `asdfghjkl` near Basel SBB still returns three hotels. The agent's own run is
unfiltered too and still offers a "best fit" for a nonsense request. A query naming only a place is treated as a
browse without checking that the hub's cards are in that place, so "Basel" on the Bern hub lists Bern.

**Identity stripping is a REST-door rule, so the MCP door does not get it.** `_discovery_stay` in `main.py`
parses an explicit stay request and removes a declared guest name before ranking, which is what stopped a Kenya
safari winning a Basel hotel booking because the guest was called Mara (#95). `hive.discover` itself does not:
it has no notion of a requester, so the words of a name are ordinary query terms to it. **`hive_discover` over
MCP calls the core directly**, so there the guest's own name still earns points — measured, `x-bekenya` takes 10
for *"offers mara"* on the Basel hotel request. The right hotel still ranks first, so this is a mis-scored row
rather than a wrong answer, but the rule belongs in the tokeniser where both doors inherit it.
`tests/test_discover_identity.py` pins the REST behaviour, including that varying only the fictional guest name
changes neither which hotels are eligible nor their order.

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

**The hub holds a signing key for every card that joined through it, including the ones that brought their own.** The only exception is a card published from a hotel's own node ([below](#separate-nodes)). The onboarding panel
generates an Ed25519 keypair in the browser, offers the private half as a download and signs the application's
canonical JSON with it (`lib/signing.ts`), so `custody: "owner"` is reachable without a terminal. That proves the
applicant holds the private half, and it is recorded on the card as `owner_public_key`, which a peer can see. The card version itself is still signed
by a key `hive.publish` generates and keeps in `hive_keys`, and that is the key published in
`/.well-known/hive.json` under `owner_keys` and used by every signature check. So the jury answer is still *the
server, for the demo* — registration narrows the gap by pinning who applied, it does not close it. Owner-held
signing keys are in [VISION.md](VISION.md#beyond-the-weekend).

**An introduction can be asked for through your own hub, but your own hub cannot prove it is itself.**
An agent that finds something a peer carries can ask *its* hub for the introduction, and that hub
tells the peer on its member's behalf
([#159](https://github.com/reactbias/Adobee-Hive/issues/159)). The point is the record, not the
mechanism: the row calibration reads stays on the hub whose search found the match, with the carrying
hub's claim frozen on it, and the peer learns that a member of another hub asked. Walking to the peer
instead was always possible — `GET /api/hub/directory` gives every peer a working URL — and it is
exactly what loses the hub the only evidence it ever gets about that peer.

What the forward cannot do is prove who is calling. There is no hub identity key to sign it with, so
the receiving hub records `requester_hub` as a claim and anyone who can reach its port can send the
same call naming any hub. That is the unanchored hub id already in SECURITY.md, seen from the other
side. The forward is also best effort by design: a peer that is down leaves `forwarded` saying so and
never costs this hub the record of what its own member asked for.

**Nobody has to prove who is asking for an introduction.** `requester` is a string on
`POST /api/hub/connect` and on the `hub_connect` MCP tool, and this hub has no accounts to check it
against. So an introduction can be created under any name by anyone who can reach the port, and the
rows that result are the input `calibration.py` reads — the measurement that orders the hub
directory. A hub's own evidence is writable by strangers, and that is worth saying before a jury
rather than after.

What changed with [#158](https://github.com/reactbias/Adobee-Hive/issues/158) is that the ledger
stopped claiming more than it knows. `requester_hub` used to default to `config.HIVE_HUB_ID` — the
hub *receiving* the request — so an agent from Zurich asking Basel was recorded as a Basel member.
Now the hub records `requester_proof`: `member` when it carries an entity by that id, `claimed` when
the caller named a hub, `none` when nobody said anything, and never `member` because of something in
the request. The proof gates nothing, deliberately: a gate keyed on an unauthenticated string would
refuse honest callers and admit anybody who guessed its shape. Per-owner authorization is
[#135](https://github.com/reactbias/Adobee-Hive/issues/135); the step that makes the question
answerable at all is a hub vouching for its own member
([#159](https://github.com/reactbias/Adobee-Hive/issues/159)), because a hub can vouch for a member
and cannot vouch for a string.
**Withdrawing an application is proved; being the person who applied is not.** An application id is
a lookup and no longer a mutation credential
([#108](https://github.com/reactbias/Adobee-Hive/issues/108)): withdrawal takes a signed action under
the key the application registered, or a capability the submission returned once for an application
whose key the hub holds, or the operator through their own route — and the row credits whichever of
the three it actually was, so it can no longer read "withdrawn by the applicant" about an act the
applicant knew nothing about.

What is proved is key possession or secret possession, which is not identity. A signature says
whoever holds that private key asked; a capability says whoever read the submission's answer asked.
The capability is the weaker half and is honest about it: over MCP the submission's answer lands in
the agent's transcript, so anything that can read that transcript can withdraw the application until
it is decided. There is no revocation and no rollover — bringing your own `public_key` avoids the
problem rather than mitigating it, and the operator's route is the way out if it happens.
**An introduction's two decisions are authorised; the people behind them are not identified.** The
owner's yes and the requester's score used to need nothing at all, so a caller who knew a connection
id could fake a consent and spend somebody else's one final score
([#107](https://github.com/reactbias/Adobee-Hive/issues/107)). Both doors now fail closed, and what
they take is the strongest thing this hub has: a secret bound to one side of the folder link the row
stands on, a signature under the key the target registered, or — for a decision only, never a score
— this hub's hub-wide owner token.

None of that is identity. A link secret says whoever holds it is that side of that link; a signature
says whoever holds that private key answered. The secret is minted once and handed over in the
connect answer, which over MCP means it is written into the agent's transcript, so anything that can
read the transcript can score the introduction. The owner token is one secret for the whole hub, so
it is recorded on the row as `owner token` rather than as the owner's own yes, and it buys nothing at
the scoring door. Per-owner accounts
([#135](https://github.com/reactbias/Adobee-Hive/issues/135)) are the fix for the last of those.

**Calibration does not reach the search rank.** A federated result is ranked
`local_relevance × hub_path_trust × hop_decay`, and `hub_path_trust` comes from `reputation.py` — declared versus
observed vetting, paid placement, availability, latency, cards that failed verification here. The sharper
measurement, `calibration.py`'s published-minus-realised error, orders `GET /api/hub/standing`, the neighbours
table and the hub directory, and is what a person choosing a hub reads. It is not a factor in that product yet.

**On a cold cache, the breadth cap is filled in arrival order.** Peers are ranked by trust only among
those whose discovery documents are in together; a cached document is in at once, so a warm hub ranks
exactly. When documents still have to be fetched, a quick low-trust peer can take one of the
`PEERS_PER_HOP` slots before a slower trusted one has answered. The trade is deliberate: waiting for every
registry to rank them is how one slow peer used to spend the whole budget (#112).

**Hub reputation resets; hub calibration needs evidence a hackathon weekend barely produces.**
`reputation.py` keeps its observations in a module-level dict, so a restart returns every peer to trust on first
use. Calibration does persist — it is computed from the `hub_connections` table — but a verdict needs
`MIN_EVIDENCE`, three scored introductions, and a score only exists after a person has gone to a real meeting and
come back to say how it went. On a fresh hub every peer therefore reads **unproven**, which is honest and is also
most of what the directory shows.

Until [#164](https://github.com/reactbias/Adobee-Hive/issues/164) that was worse than slow, it was impossible for
the hub you are standing on: an introduction to one of its *own* members was written with `published_rating NULL`,
because `hub.connect` read the stored card body and a signed body carries no `trust` block. `rated_via` drops a
row with no claim, so the home row in a hub's own directory read `unproven` with "no introductions through this
hub yet" however many it had had. `hub.connect` now reads `hive.get_card` for a local entity — the same body the
cross-hub branch always received — and records this hub as the one that carried it, so a hub can be measured by
its own members' meetings. What is still true: an entity nobody has reviewed has no claim to measure, so its
introductions stay uncounted, and that is the honest answer rather than a number.

## The folder link

**It links two folders on one disk.** `app/folders.py` is the step between the index and the booking, and it is
real: a link is handle to handle and carries no content, a linked peer sees the `shared` files the Card never
mentioned, a grant is per path, and `private` and `hidden` paths are counted and never named — not in a manifest,
not in a refusal. What it is not is two machines. The only implementation today is `LocalFolderLink`, which links
the folders in [`testdata/vaults/`](../testdata/README.md) inside this process with its links and grants in
DuckDB, so no key is exchanged and nothing is encrypted. `FOLDER_LINK=claudeconnect` is accepted and falls back to
local with the reason in `GET /api/health`, because the adapter for the real library is not built yet.

**A client can open a link, read the manifest and read a granted file; it cannot yet drive the rest.**
`GET /api/folders/manifest` and `GET /api/folders/file` are built, authenticated by a secret bound to the
link ([FOLDER_API.md](FOLDER_API.md)), and `POST /api/hub/connect` hands the requester that secret in the same
answer. What has no endpoint yet is claiming a handle, and requesting or accepting a link by
hand: those can still only be done from Python. Giving and revoking a grant **do** have endpoints
(`POST`/`GET /api/folders/grants`, `DELETE /api/folders/grants/{id}`), so the demo's grants are made by the
seeder only not by an owner clicking. Issue #116 has the shape; the routes are the remaining slice.

**The read surface serves less than the link admits.** A linked peer *sees* a `shared` file in the manifest —
that is the folder link's whole point, since the Card never said it existed — but `GET /api/folders/file`
hands over bytes only for `public` and `public-summary` paths (`folders.SERVED`), so a read can never be the
first time a byte of a file left the folder. Granted `shared` reads are one constant away and are not switched
on.

## Reaching an entity on another hub

**It works, and the introduction is recorded here, but this hub cannot complete it.** A federated
search finds an entity on a peer and `POST /api/hub/connect` will now connect to it: the caller
passes the signed card the search returned, and this hub checks it against the key the entity's
*own* hub pinned for it, read from a registry this hub fetched itself from a URL on its own peer
list. A card that cannot be checked is refused with a reason, never admitted on the carrier's word.

Three honest limits on that. A remote `confirm` entity's connection stays `requested` for good as
far as this hub is concerned — `connections.confirm` refuses it, because the owner's yes happens
where the owner is, and this hub has no way to ask them or to hear the answer. The remote entity's
folder is on its own hub, so the manifest the link opens is empty; the link itself is a real local
fact and nothing more. And the card can only be checked when its hub is on this hub's peer list and
has already answered — an origin two hops away, or a hub in the first `PEER_ASK_SECONDS` of a fresh
stack, is refused rather than trusted.

## Separate nodes

**The agent can run as its own service, and the stage demo does not use it.** `render.yaml` defines `adobee-agent`,
which reaches the hub only over MCP, but `lan.sh` still runs the agent inside each hub. `/api/ask` and the scout
stay on the hub whichever is used. Activity from agent runs is recorded on the service that ran them, so the hub's
feed and a card's *shown* and *read* counts miss them.

**A hotel's own node covers one fictional hotel, and only booking.** Hotel Lindenhof keeps its key and bookings on
its node, and its card is signed there. Three things have not moved with it:

- **The owner's view.** The app's business screen reads the hub, so it shows no bookings for this hotel. They are
  on the node, at `GET /api/owner/{card_id}`.
- **Reviews.** `hive_review` works at the node, but a review left there does not reach the hub's rating.
- **Availability at the hub.** The hub cannot see the node's bookings, so its search can list this hotel for dates
  that are full. The agent's check at the node has the final word.

The hub's `POST /api/demo/reset` also removes the card, until the node publishes it again. An agent that reaches
the card over peer search rather than `HIVE_MCP_URLS` is not covered by a test.

**A folder is still not a node.** The folder link runs inside the hub ([above](#the-folder-link)).

**In the app, the owner's yes is the shared token.** The app's Accept and Decline send `X-Owner-Token`, so they work only on a hub that sets `OWNER_EDIT_TOKEN`, and that token covers every card. The hub also takes a per-party proof, but the app does not send one, and a hotel's own node does not answer introductions for its card.

## Item sharing

**What is enforced, and what the flags are not a promise of.** `hive.discover` withholds a `push` or
`never` entity from the matches and from the near-misses alike, on the path REST and MCP both serve;
`hive.publish` keeps a contact channel the owner closed out of the body it signs; `hive.public_contact`
drops one on the way out of an older card; and a held entity a peer relayed is withheld here too. That
is not a blanket promise that every public API redacts personal data — the index is public by design
(`GET /api/hive/cards` returns every signed card with no credential, `/.well-known/hive.json` publishes
every owner key), so these are rules about what the hub asserts about an entity that asked it not to,
not about secrecy of the cards. Use fictional fixtures, not real CVs.

**A card published before sharing was enforced can still carry a value its owner closed.**
`hive.publish` now drops a contact channel marked `push` or `never` before it signs, and
`hive.public_contact` drops one on the way out, so nothing is served from such a card — but the
value is still in the signed body of the stored version, and `hive.get_card` serves that body byte
for byte because a signature is checked against it. Redacting it in place would mean publishing a
card that no longer verifies, which is worse. Republishing the entity is the fix, and the owner
tools do it (`hive_owner_publish`, `POST /api/owner/{card_id}/publish`). Historical versions in
`hive_card_history` are kept on purpose, so an existing booking can still show what it was promised.

**A peer's exclusion rows are not checked against a sharing flag.** An exclusion carries no card
(`federation.MAX_PEER_EXCLUSIONS` rows of the peer's own prose), so there is nothing signed to read
a flag from. A match is checked after `hive.verify_pinned` and a held entity is withheld; a
near-miss a peer chose to name is carried as that peer's claim and nothing more. It is marked as
the peer's rather than presented as this hub's.

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

**One shared owner token, and two different doors.** `OWNER_EDIT_TOKEN` is one secret for every card on the hub:
it proves its holder may edit *a* card here, never that they own *this* one, so holding it is holding every card
([#135](https://github.com/reactbias/Adobee-Hive/issues/135)). On top of that the two surfaces guard it
differently, which is deliberate and worth knowing. The REST routes under `/api/owner/` treat an unset
`OWNER_EDIT_TOKEN` as "the check is off" and are open on a hub that has not set one — the owner studio on a
laptop, as it has always been. The three `hive_owner_*` MCP tools fail closed instead: with no token set they
publish nothing at all, and they refuse a wrong or missing one, because `/mcp/` can be reached from anywhere
`/.well-known/hive.json` can be read. So **a deployed hub sets `OWNER_EDIT_TOKEN`**, and a hub that has not set
one answers `hive_owner_card` and refuses the other two. Reading an owner's view needs no token on either
surface and shows guest names as initials without one.

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

- **The approval click belongs to our agent, not to the protocol.** `hive_book` over MCP books when called, and an
  outside client has to bring its own approval policy. The critic's or verifier's dissent is shown to the person, and
  it does not take Approve away.
- **"Two agents talking" is staged on the demo.** The hotel's agent there is its signed card behind the MCP server
  plus scripted roles, not a second model negotiating ([#125](https://github.com/reactbias/Adobee-Hive/issues/125)).
- **`Hiring Hub/` is a separate app, not part of this demo.** It needs an API key and its own Docker stack, has no
  offline fallback or translations, and CI does not run its tests.
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
