# Search API — handover for the search team

Everything you need to build **(1)** a tool that searches every Card on a Hive to find the right
candidate, and **(2)** an agent that reads an owner's own folder of files rather than JSON.

This page assumes you know nothing about this repo. Every command here was run against a clean
three-hub stack before it was written down, and every JSON body is a real response with nothing
added. Where a docstring or another page in `documentation/` says something the code does not do,
this page says what the code does and names the disagreement — see
[Where the docs and the code disagree](#where-the-docs-and-the-code-disagree) at the end.

**Contents**

- [The five things to know first](#the-five-things-to-know-first)
- [Run it: three peered hubs with a corpus in them](#run-it-three-peered-hubs-with-a-corpus-in-them)
- [The Card, field by field](#the-card-field-by-field)
- [The endpoints](#the-endpoints)
- [Federation and provenance](#federation-and-provenance)
- [Scoring, and the `why`](#scoring-and-the-why)
- [The three-folder fixture](#the-three-folder-fixture)
- [What is not built](#what-is-not-built)
- [Where the docs and the code disagree](#where-the-docs-and-the-code-disagree)

---

## The five things to know first

1. **`offers` and `needs` are the index.** Not `kind`. A hub holds hotels, freelancers and
   hairdressers side by side on purpose, so nothing you build may assume a narrow domain.
   `kind` is a filter a caller may apply, never a gate the hub applies for them
   (`hive.NOT_DISCOVERABLE` is the empty set).
2. **`description` is up to 2000 characters and is *meant* for discovery.** In a web whose visitors
   are agents, the description is the pitch to the agent. The hub does not read it, score its
   keyword density or form a view about it. Writing it for discovery is the field working as
   designed. What stops an entity over-claiming is the economic loop — bad matches, scored meetings,
   a hub's calibration error — not prose analysis.
3. **`GET /api/hive/discover` returns the whole hub, ranked, not a filtered result set.** An entity
   that failed no *hard* constraint is a `match`, even with `score: 0`. A query for a haircut on the
   `bern` hub returns all 20 entities; one has `score: 8` and nineteen have `score: 0`. **You must
   threshold on `score > 0` yourself**, which is what the repo's own eval tools do.
4. **A result can always tell you which hub it came from.** At `radius: 0` there is only one hub.
   Above 0, every match carries `provenance.path`, origin-first, ending in the hub you asked. See
   [Federation and provenance](#federation-and-provenance).
5. **A match summary is not a Card.** It has no `offers`, no `needs`, no `structure`. Fetch
   `GET /api/hive/cards/{id}` for those — except for a federated match, which carries the full
   signed Card inline under `card`.

---

## Run it: three peered hubs with a corpus in them

[`lan.sh`](../lan.sh) at the repo root starts three hubs, peers each with the other two, and seeds
the corpus through the real signup endpoint. One command:

```bash
# from the repo root. lan.sh needs the venv to be exactly code/backend/.venv
( cd code/backend && python3 -m venv .venv \
  && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt )
./lan.sh up
```

> If `python3 -m venv` fails for a missing `ensurepip` — it does on a stock Debian or Ubuntu without
> `python3-venv` — this works instead, and is what this page was verified with:
>
> ```bash
> ( cd code/backend && uv venv .venv \
>   && uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt )
> ```

### The ports

| What | Port | Override |
| --- | --- | --- |
| the app (fixed, it is the URL people are given) | `8440` | `PORT_APP` |
| hub `basel` | first free from `8420` | `PORT_A` |
| hub `zurich` | next free | `PORT_B` |
| hub `bern` | next free | `PORT_C` |

The hub ports **move** if something already holds them, so read them off the output rather than
assuming. To run a second stack beside one that is already up, pin all four:

```bash
PORT_APP=8540 PORT_A=8520 PORT_B=8521 PORT_C=8522 ./lan.sh up
```

> **Do not run `./lan.sh down` if somebody else's stack is up on this machine.** Its cleanup sweeps
> *every* listener on ports 8420–8445 whose command line contains `uvicorn` or `vite`, whatever
> started it, so it will stop a demo you did not start. Kill your own by pid instead
> (`.lan/*.pid`). Noted as a bug below.

`lan.sh up` also rebuilds the frontend, which needs `npm install` in `code/frontend` first. The
build failure is swallowed and the hubs come up anyway, so if you only want the API, ignore it.

### What you end up with

Verified on a clean run (ports pinned as above):

```bash
for p in 8520 8521 8522; do curl -s "http://127.0.0.1:$p/.well-known/hive.json" \
  | python3 -c 'import sys,json;f=json.load(sys.stdin)["federation"];print(f["hub_id"],f["entities"])'; done
```

```
basel 32
zurich 21
bern 20
```

**73 entities in all.** 61 of them are the vault folders in [`testdata/`](../testdata/README.md) —
20 on `basel`, 21 on `zurich`, 20 on `bern`. `basel` carries **12 more**, because `lan.sh` sets
`SEED_ON_EMPTY=true` only for `basel`. That adds six demo cards that have no vault folder
(`hive_seed.py`: `hotel-rheinblick`, `hotel-gare`, `hotel-messe`, `hotel-muenster`,
`hotel-dreirosen`, `cafe-bienli`) and six unclaimed example cards
(`app/domains/examples.py`: `x-adobe`, `x-baselhack`, `x-4xor`, `x-bekenya`, `x-endress`, `x-pax`).
Those twelve are the reason `basel` reads 32 and not 20, and they are also a source of ranking noise
— see [Scoring, and the `why`](#scoring-and-the-why).

### Wait ~20 seconds before your first federated search

**This one will waste your afternoon if you do not know it.** `lan.sh` starts the hubs, each hub
immediately asks its peers who they are, and *then* the corpus is seeded. So the first peer profile
each hub caches was fetched while the peer still had **zero** entities and therefore an **empty**
`owner_keys` map. Until that cache is refreshed — `PEER_ASK_SECONDS` is 30, in practice under 20
seconds — every card a peer relays fails verification here, because no key is pinned for it.

Measured on a fresh stack, a `radius: 1` search run immediately:

```json
"matches": 32,                 // local only: all 41 remote cards were thrown away
"rejected": [ { "hub": "zurich", "card_id": "anouk-pfister", "origin": "zurich",
                "reason": "this copy does not match what the owner signed, or no key is pinned for it" },
              "… 40 more …" ]
```

And `GET /api/hub/directory` is the tell — `"entities": 0` for a peer that plainly has 21:

```
  basel  entities= 32  last_asked= None
  zurich entities= 0   last_asked= 2026-10-31T20:06:23+00:00
  bern   entities= 0   last_asked= 2026-10-31T20:06:23+00:00
```

Poll that until the peer counts appear, then search:

```bash
until curl -s http://127.0.0.1:8520/api/hub/directory | grep -q '"entities": *21'; do sleep 3; done
```

**It does not fully heal.** Those 41 rejections are charged against the peers' reputation, and
`reputation.py` keeps its observations in a module-level dict, so for the rest of that process the
peers read *"41 of 82 relayed cards failed verification here"* and their trust sits at **0.05**
instead of **~0.61**. Federation then works but ranks almost nothing: the same match scored
`federated_score: 0.36` on a poisoned stack and `4.19` on a clean one — a factor of twelve.
If it happens, restart the hubs. Listed under the bugs below.

### Seeding on its own

The seeder is a normal client: it builds a Card from each folder and `POST`s it to
`/api/hub/register` like any applicant, so seeding is itself a test of signup.

```bash
cd code/backend
.venv/bin/python tools/seed_vaults.py --hub http://127.0.0.1:8520 --hub-id basel  --keys ../../.lan/keys
.venv/bin/python tools/seed_vaults.py --hub http://127.0.0.1:8521 --hub-id zurich --keys ../../.lan/keys
.venv/bin/python tools/seed_vaults.py --hub http://127.0.0.1:8522 --hub-id bern   --keys ../../.lan/keys
.venv/bin/python tools/seed_vaults.py --hub http://127.0.0.1:8520 --hub-id basel --only hotel-krafft
```

`--keys` keeps the Ed25519 keypairs on disk, so a re-run is the same owner publishing version 2
rather than a stranger. All 61 entities and all 416 files take about 1.3 seconds.

### No hub needed at all

Both evaluation tools build a corpus in a throwaway DuckDB and call `hive.discover` in process:

```bash
cd code/backend
.venv/bin/python tools/eval_answer_key.py     # 61 vault entities
.venv/bin/python tools/eval_search.py         # 73 entities, literal vs semantic side by side
```

Run them with **no** `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` in your shell. A key does not change
the ranking (there is no embedding provider), but it does change what the agent tests do.

---

## The Card, field by field

Two sources disagree about the Card and you need to know which is which:

- **[`documentation/cards/README.md`](cards/README.md)** is the *design* Card. It is explicit that
  parts of it are still design: `seq`, `keys`, `links`, portable `attestations`, a top-level
  `rating`.
- **`code/backend/app/hive.py`** is what a hub serves today. **Build against this.**

Here is a real served Card, in full, from `GET /api/hive/cards/treuhand-kehrli` on `bern`:

```json
{
  "id": "treuhand-kehrli",
  "slug": "treuhand-kehrli",
  "kind": "service",
  "name": "Treuhand Kehrli",
  "description": "Buchhaltung, Mehrwertsteuer und Steuererklärungen für kleine Betriebe: Beizen, Ateliers, Einzelfirmen. Wir rechnen pro Stunde und schicken keine Pauschale.",
  "tagline": "Buchhaltung, Mehrwertsteuer und Steuererklärungen für kleine Betriebe: Beizen, Ateliers, E",
  "sharing": "public",
  "contact": { "email": "kontakt@treuhand-kehrli.example", "phone": "+41 31 000 11 66" },
  "contact_sharing": {},
  "features": [],
  "offers": [
    { "title": "Buchhaltung pro Quartal, bis 200 Belege", "summary": "Buchhaltung pro Quartal, bis 200 Belege — CHF 680.", "price_chf": 680 },
    { "title": "Mehrwertsteuerabrechnung", "summary": "Mehrwertsteuerabrechnung — CHF 240 pro Quartal.", "price_chf": 240 },
    { "title": "Steuererklärung für eine Einzelfirma", "summary": "Steuererklärung für eine Einzelfirma — ab CHF 450.", "price_chf": 450 }
  ],
  "needs": [
    { "title": "Jemand, der uns eine Seite baut, die ein Agent lesen kann", "summary": "Jemand, der uns eine Seite baut, die ein Agent lesen kann." }
  ],
  "structure": [
    { "path": "about.md",      "bytes": 177, "media_type": "text/markdown",   "visibility": "public-summary", "digest": "sha256:3c923797dc75" },
    { "path": "contact.md",    "bytes":  78, "media_type": "text/markdown",   "visibility": "public-summary", "digest": "sha256:ac4a851a5789" },
    { "path": "tarife.pdf",    "bytes": 876, "media_type": "application/pdf", "visibility": "public",         "digest": "sha256:89294369bacf" },
    { "path": "visibility.md", "bytes":  80, "media_type": "text/markdown",   "visibility": "public-summary", "digest": "sha256:295466039e47" },
    { "path": "work.md",       "bytes": 256, "media_type": "text/markdown",   "visibility": "public-summary", "digest": "sha256:a4810e11d4ea" },
    { "path": "mandanten/",    "files":   3,                                  "visibility": "private" }
  ],
  "custody": "owner",
  "registered_via": "ap-7b94af455375",
  "owner_public_key": "dOIZm+WO79n56QvW3Evo+P9P42XOdWn1Z1vnp6+Kksg=",
  "version": 1,
  "published_at": "2026-10-31T19:42:47+00:00",
  "valid_until": "2027-01-29T19:42:47+00:00",
  "trust": {
    "signature_valid": true,
    "claimed": true,
    "provenance": null,
    "signature": "1EEFT6dBQJYwRg4Uq0C85y8ee6JUnxAskJDEUkUN1tcu4rw24afVuEAK3hqJtzGCzeJipr4N5PzE+dTK6ln5Bw==",
    "public_key": "jPyFAlmfBFtPHNmVzkE6M52XNB2NmidHKx3RizfipSM=",
    "algorithm": "Ed25519 over canonical JSON (sorted keys, no spaces)",
    "attestations": [],
    "verified_reviews": { "count": 0, "average": null, "recent": [], "rule": "only guests with a signed booking receipt can review" },
    "freshness_days": 0,
    "fresh": true
  }
}
```

### Required, optional, and what each field is

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `id` | string | **yes** | Stable, lower case, digits and hyphens. Unique on this hub |
| `slug` | string | **yes** | Equals `id` on every seeded card; treat `id` as the key |
| `kind` | string | **yes** | Free text. Seen in the corpus: `hotel`, `cafe`, `service`, `person`, `software`, `industrial`, `insurance`, `event`, `adventure`. **A filter, not a taxonomy** |
| `name` | string | **yes** | What a person sees |
| `description` | string | yes, may be `""` | **The pitch to the agent.** Up to 2000 characters. Always present, never absent |
| `tagline` | string | optional | One phrase. The vault seeder clamps its own at 90 characters, which is why the example above looks truncated mid-word — that is the seeder, not the hub |
| `sharing` | `public` \| `confirm` \| `push` \| `never` | optional | The entity's **default** item flag. Absent means `confirm` (`sharing.DEFAULT`), never `public` |
| `contact` | object | yes | Open map. Seeded cards carry whichever of `email`, `phone`, `address`, `mcp` the folder gave. **`email` and `phone` are not in fact guaranteed present today** — see the disagreements below |
| `contact_sharing` | object | yes, may be `{}` | Per-channel flag, only where it differs from the entity default. `{"phone": "confirm"}` with `"phone": ""` means *they have one, ask for it* |
| `features` | string[] | yes, may be `[]` | Short exact tags a search can filter on: `dog-friendly`, `breakfast`, `quiet`, `parking`, `late check-in` |
| `offers` | object[] | yes, may be `[]` | **Half the index.** Each entry: `title` (required), `summary`, `price_chf`, `tags`, `skills`, `unit`, `id` |
| `needs` | object[] | yes, may be `[]` | **The other half.** Same shape as `offers` |
| `units` | object[] | only for stays | Bookable rooms or slots. `bookable` on a search result is `bool(units) and claimed` |
| `structure` | object[] | yes | The *shape* of the owner's folder, never its contents. See below |
| `custody` | `owner` \| `hub` | yes | `owner` means the applicant brought a public key and kept the private half |
| `registered_via` | string | optional | The application id that admitted it |
| `owner_public_key` | base64 | optional | Present when `custody: owner`. **Not** the key card versions are signed with |
| `version` | integer | yes | Monotonic. `hive.publish` increments it; last writer wins |
| `published_at`, `valid_until` | ISO 8601 | yes | A card is `fresh` for 90 days |
| `trust` | object | yes | Signature, claim status, reviews, attestations, freshness. See below |

Fields in `cards/README.md` that a hub does **not** serve today: `rating` / `rating_count` at the top
level (they are on *search results*, derived from `trust.verified_reviews`), `seq`, `keys`, `links`,
`policy`, top-level `attestations`, `sig`, `contact_released`.

### `trust`

| Field | Meaning |
| --- | --- |
| `signature_valid` | The card verifies against the key pinned for its id in `/.well-known/hive.json` |
| `claimed` | `false` means a **lead** compiled from public information. The subject never agreed to anything: findable, never bookable, hand-off only after a human says yes |
| `provenance` | `null` for a locally published card; set for a card the scout compiled |
| `verified_reviews.average` | **`null` until a signed booking receipt exists.** `null` is not zero. Every seeded card is `null` |
| `verified_reviews.count` | How many signed receipts produced the average |
| `attestations` | Counter-signed statements. `[]` on every seeded card |
| `freshness_days`, `fresh` | Age since `published_at`, and whether it is inside 90 days |

### `structure` — the shape of the folder, never the contents

One row per file. A row is a path, a size, a media type and a 12-hex-character SHA-256 prefix. The
contents are never in the Card — the digest is the proof that this is the shape and not the thing.
`visibility.md` in the folder decides how much each path admits to, with five values
([`cards/README.md`](cards/README.md) is the reference, `tools/seed_vaults.py` the parser):

| `visibility.md` says | What the row looks like | Who may read the contents |
| --- | --- | --- |
| `public` | `path`, `bytes`, `media_type`, `digest` | anyone |
| `public-summary` | the same. **The default for anything unlisted** | handshaked peers |
| `private` | the folder and a file **count**: `{"path": "mandanten/", "files": 3, "visibility": "private"}`. No names, no digests | the owner only |
| `shared` | **the row is absent** | handshaked peers |
| `hidden` | **the row is absent** | the owner only |

`shared` and `hidden` are absent rather than flagged on purpose: listing a folder in order to say it
is secret still leaks that it exists. A rule ending in `/` covers everything under it, and the
longest rule wins, so a folder can be `private` with one file inside it published.

**Rule of thumb for a search tool:** `structure` tells you a file exists and what it hashes to. It
never tells you what is in it. If your agent wants the file, it asks the owner.

### How much room an entry has

Served live at `GET /api/hub/registration` under `limits`, and defined once in
`code/backend/app/limits.py`. These numbers came out of the running hub:

| Field | Room | What it is for |
| --- | --- | --- |
| `id` | 63 characters | `hive:<hub>/<entity>` without the hub part. Lower case, digits, hyphens |
| `kind` | 32 characters | What sort of entity this is, so a search can narrow by it |
| `name` | 120 characters | What a person sees in a result |
| `tagline` | 200 characters | One phrase under the name |
| `description` | **2,000 characters** | Your pitch to an agent. Write it for discovery |
| `offers` | 50 entries | What you provide. Half the index |
| `needs` | 50 entries | What you are looking for. The other half |
| `offers[].title` | 200 characters | The name of one thing you offer or need |
| `offers[].summary` | 600 characters | The line it came from, in your own words |
| `offers[].tags` | 20 entries | Words a search should match that the prose does not carry |
| `features` | 50 entries | Short facts a search can filter on |
| `units` | 100 entries | Bookable rooms or slots |
| `structure` | 1,000 entries | One row per file in your folder: path and digest, never contents |
| `contact` | 20 channels | The open map of how to reach you |
| `contact.<channel>` | 200 characters | One channel's value, e.g. a postal address |
| `proofs` | 8 entries | Claims about the world. Recorded unverified, never trusted |
| `proofs[].subject` | 200 characters | What one proof is about, e.g. a domain name |
| `any other text` | 500 characters | Any string the card carries that is not named above |
| `any other list` | 200 entries | Any list the card carries that is not named above |
| `keys per object` | 64 keys | How many keys one object may carry |
| `nesting` | 12 levels | How deeply a card may nest |
| `the whole card` | 256,000 bytes | The canonical JSON of everything above |
| `the application` | 320,000 bytes | The card plus its key, proofs and signature |
| `the request body` | 1,048,576 bytes | Refused by size before it is parsed into objects |

`needs` is bounded exactly like `offers`, and the two `offers[].*` rows apply to a need as well.
Nothing here reads the *content* of a field; a limit is a ceiling on size, nothing else.

**Three things are tidied rather than refused**, so what the hub signs is what a reader sees: NFC
normalisation, control and zero-width characters dropped, whitespace runs collapsed and the ends
trimmed. A description padded with zero-width characters is not refused — the padding is simply gone
before the length is measured.

**What a refusal looks like.** Over a limit at signup is an answer, not an error: **200** with
`state: "rejected"`, the checks that ran, and a reason naming the ceiling and your real size.
Verified:

```bash
curl -s http://127.0.0.1:8520/api/hub/register -H 'Content-Type: application/json' \
  -d "{\"entity\":{\"id\":\"too-long-demo\",\"kind\":\"service\",\"name\":\"Demo\",\"description\":\"$(python3 -c 'print("x"*2500)')\"}}"
```

```json
{
  "id": "ap-cf59ab396f5e",
  "state": "rejected",
  "checks": [
    { "check": "shape", "ok": true,  "detail": "well formed" },
    { "check": "size",  "ok": false, "detail": "`description` is at most 2000 characters; this one is 2500" }
  ],
  "decided_by": "policy",
  "reason": "`description` is at most 2000 characters; this one is 2500"
}
```

A body over the last row is a real **413**, refused by size before it is parsed:

```json
{ "detail": "a request body is at most 1048576 bytes; this one is 1100068" }
```

---

## The endpoints

Base URL is one hub. Every hub serves the same surface; there is no central index.

### `GET /api/hive/discover` — the one you came for

| Parameter | Type | Default | Notes |
| --- | --- | --- | --- |
| `query` | string | `""` | Free text. Truncated to 500 characters |
| `kind` | string | — | Exact match on the card's `kind`. A filter, nothing more |
| `near` | string | — | A landmark, matched against the card's `distances_m` map. The four in the corpus are exactly `basel sbb`, `messe basel`, `marktplatz`, `badischer bahnhof`, and only the hand-written Basel stay cards carry them |
| `max_price_chf` | float | — | **A hard constraint**, but only against a *published* price. A card over it is `excluded`; a card with no price neither fails nor passes |
| `features` | string, repeated | — | `features=quiet&features=dog-friendly`. **Hard constraints**, max 20, lower-cased, exact string match against the card's `features`. Free text, so read the real set off `GET /api/hive/cards`; on `basel` it is 58 values including `quiet`, `breakfast`, `parking`, `dog-friendly`, `late check-in`, `vegan`, `wifi` |
| `check_in`, `check_out` | `YYYY-MM-DD` | — | **A hard constraint on the whole hub**, not only on stays: any card without `units` is `excluded` with `"takes no stay bookings"`, so a dated query on a mixed hub excludes the hairdresser |
| `guests` | int 1–20 | `1` | Over 20 is **422** |
| `radius` | int 0–3 | `0` | Hop limit. 0 is this hub only |
| `budget_ms` | float 0–20000 | `2500` | Whole-query time budget. Only matters above `radius: 0` |
| `seen` | string, repeated | — | Hub ids this query already visited. **For hops, not for clients** |
| `looking_for` | `offers` \| `needs` \| `any` | `offers` | Which side of the market you are on |

Bad values: `radius=4` → **422**, `radius=-1` → **422**, `guests=99` → **422**,
`looking_for=bogus` → **400** with `{"detail": "looking_for must be one of offers, needs, any, not 'bogus'"}`.

A real local search, trimmed only by dropping the nineteen other matches that scored `0`:

```bash
curl -s "http://127.0.0.1:8522/api/hive/discover?query=piano%20tuner"
```

```json
{
  "matches": [
    {
      "id": "stimmwerk-aare",
      "slug": "stimmwerk-aare",
      "name": "Stimmwerk Aare",
      "kind": "service",
      "tagline": "Wir stimmen Klaviere und Flügel im Kanton Bern, zweimal im Jahr pro Instrument, und reguli",
      "description": "Wir stimmen Klaviere und Flügel im Kanton Bern, zweimal im Jahr pro Instrument, und regulieren die Mechanik, wenn sie zu laut klappert.",
      "rating": null,
      "rating_count": 0,
      "contact": { "email": "termin@stimmwerk-aare.example", "phone": "+41 31 000 10 58" },
      "contact_sharing": {},
      "claimed": true,
      "bookable": false,
      "from_price_chf": null,
      "distance_m": null,
      "score": 16,
      "score_breakdown": {
        "constraints": 0, "text_relevance": 0, "offers_needs": 0, "semantic": 16,
        "proximity": 0, "verified_reviews": 0, "attestations": 0, "signature": 0
      },
      "why": ["offers something close to 'tuner, piano': Stimmen eines Klaviers"],
      "signature_valid": true
    }
  ],
  "excluded": [],
  "ranking_policy": "The constraints you gave first, and nothing is paid for a check nobody asked for; then what the entity offers or needs, then relevance, proximity, verified reviews, attestations. No paid placement."
}
```

**`matches` is every entity that failed no hard constraint**, sorted by `score` descending. On
`bern` that is all 20. `excluded` is everything that failed one, each with `why_not`:

```bash
curl -s "http://127.0.0.1:8520/api/hive/discover?query=quiet+room&near=basel+sbb&features=breakfast&max_price_chf=200"
```

```
hotel-gare    71  {"constraints":50,"text_relevance":0,"offers_needs":0,"semantic":4,"proximity":15,"attestations":2,...}
              why: ["has breakfast", "80 m from basel sbb", "describes something close to 'room': 120 rooms directly at the station"]
cafe-rhein    65  {"constraints":50,"text_relevance":5,"offers_needs":10,"semantic":0,...}
              why: ["has breakfast", "offers quiet", "mentions quiet"]
excluded: 28, e.g. {"id": "x-4xor", "why_not": ["missing breakfast"]}
```

`looking_for=needs` flips the market round — *who wants what I provide*:

```bash
curl -s "http://127.0.0.1:8520/api/hive/discover?query=I+photograph+hotel+rooms&looking_for=needs"
```

```
wirtshaus-anker   24  why: ["needs something close to 'photograph, rooms, hotel': Jemand, der unsere Zimmer fotografiert. Unsere Bilder sehen aus wie vom…"]
hotel-rheinblick  14  why: ["describes something close to 'hotel, rooms, photograph': Family-run 18-room hotel on the Kleinbasel riverside"]
```

The same query with the default `looking_for=offers` returns the hotels instead, because it is then
reading what they *provide*. Twelve more need-to-offer pairs are tabulated in
[`testdata/README.md`](../testdata/README.md), most of them across two hubs.

### `GET /api/hive/cards` and `GET /api/hive/cards/{id}`

`/api/hive/cards` is every card on the hub as a JSON array, optional `?kind=`. No ranking, no query.
Useful once, to pull the corpus into your own index; 32 cards on `basel`.

`/api/hive/cards/{id}` takes an id **or** a slug and returns the full Card shown above. This is how
you get `offers`, `needs` and `structure` after a local search, since the match summary has none of
them.

An unknown id is **400**, not 404: `{"detail": "No Hive card 'nope'."}`. Every `HiveError` on this
app becomes a 400 (`main._hive_call`), so do not branch on 404 — branch on the status being 4xx and
read `detail`.

### `GET /api/hub/registration`

What this hub asks of an applicant, and the exact document to send. Published so a client can read
the rules before composing anything.

```bash
curl -s http://127.0.0.1:8520/api/hub/registration
```

```json
{
  "policy": "open",
  "means": "anything that passes the checks is admitted at once",
  "checks": ["shape", "size", "signature", "blocklist", "availability", "invite"],
  "limits": [ { "field": "id", "unit": "characters", "cap": 63, "about": "…" }, "… 24 rows …" ],
  "verification_offered": "signed",
  "verification_ladder": ["none", "signed", "domain", "identity"],
  "proof_types": ["dns-txt", "rel-me", "email"],
  "key_custody": "Bring a public key and you keep the private half. Omit it and this hub holds one for you.",
  "example": {
    "entity": { "id": "your-id", "kind": "stay", "name": "Your name", "description": "One line.", "sharing": "public" },
    "public_key": "<base64 Ed25519>",
    "proofs": [ { "type": "dns-txt", "subject": "your-domain.example" } ],
    "signature": "<base64 over the canonical JSON of this document without `signature`>"
  }
}
```

`limits` is **24 rows** and is the table above, generated from the same `limits.LIMITS` tuple. Read
it rather than hard-coding numbers: a hub may publish different ones.

`verification_offered` is `signed` and that is the top of the ladder a hub reaches today — nothing
verifies a `dns-txt`, `rel-me` or `email` proof, so a proof is *recorded unverified* and raises
nothing. Treat `verification_ladder`'s top two rungs as unreachable.

### `GET /.well-known/hive.json`

The discovery document. This is how a peer learns about a hub, and how **you** verify a card's
signature yourself: `owner_keys` maps an entity id to the public key its card versions must be
signed by.

```bash
curl -s http://127.0.0.1:8521/.well-known/hive.json
```

```json
{
  "name": "Adobee Hive (zurich)",
  "description": "Developers, designers and freelance work around Zürich.",
  "mcp": { "url": "http://127.0.0.1:8521/mcp/", "transport": "streamable-http" },
  "signature": "Ed25519 over canonical JSON; a card is valid only if signed by the key pinned for its id below",
  "owner_keys": { "jonas-brun": "…base64…", "…": "…" },
  "ruleset_keys": { "…": "…" },
  "ranking_policy": "The constraints you gave first, …",
  "federation": {
    "hub_id": "zurich",
    "name": "Adobee Hive (zurich)",
    "description": "Developers, designers and freelance work around Zürich.",
    "verification": "signed",
    "admission": "open",
    "entities": 21,
    "paid_placement": false,
    "max_radius": 3
  }
}
```

`federation.entities` is the cheapest way to count a hub. `federation.max_radius` is the hop ceiling
(`3`).

### `GET /api/hub/directory`

Every Hive this hub knows of, for a person — or an agent — choosing which one to search.
`admin.directory()`; needs no credential.

```json
{
  "hubs": [
    { "hub": "basel",  "url": "",                          "home": true,  "entities": 32, "admission": "open", "accepting": true, "verification": "signed", "verdict": "unproven", "why": "no introductions through this hub yet", "evidence": 0, "error_stars": null, "apply_at": "/api/hub/register", "blocked": false, "stale": false },
    { "hub": "zurich", "url": "http://192.168.21.123:8521", "home": false, "entities": 21, "admission": "open", "accepting": true, "verification": "signed", "verdict": "unproven", "why": "no introductions through this hub yet", "evidence": 0, "error_stars": null, "apply_at": "http://192.168.21.123:8521/api/hub/register", "last_asked": "2026-10-31T19:47:17+00:00", "last_asked_ok": true, "known": true },
    { "hub": "bern",   "url": "http://192.168.21.123:8522", "home": false, "entities": 20, "…": "…" }
  ]
}
```

`verdict` is `unproven` on a fresh stack and will stay that way for your purposes: a calibration
verdict needs three **scored introductions**, and a score only exists after a person went to a real
meeting and came back to say how it went. That is honest, not broken.

### `GET /api/health`

```json
{ "status": "ok", "llm": "openai", "semantic": "offline", "model": "gpt-5-mini", "fast_model": "gpt-5-mini", "hives": ["local"] }
```

`semantic` is the similarity provider **ranking actually uses**. It reads `offline` whether or not a
key is configured, because the embedding provider is a seam with nothing in it
(`semantic._embedding_provider()` returns `None`). A hub with a key searches exactly as well as one
without. `llm` is a different thing entirely — the agent's model vendor — and reads `mock` with no
key.

### The MCP surface

Mounted at `/mcp/`, Streamable HTTP, **stateless** — so plain `curl` works with no session
handshake. 21 tools. Verified:

```bash
curl -s http://127.0.0.1:8521/mcp/ -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

```
hive_discover  hive_what_was_promised  hive_rulesets  hive_get_card  hive_check_availability
hive_book  hive_cancel  hive_review  hive_wait  hive_check_waiting
hr_find_people  hr_request_intro  explore_ask  hive_scout
hub_connect  hub_score  hub_connections  hub_standing  hub_registration  hub_register  hub_directory
```

Calling the search tool:

```bash
curl -s http://127.0.0.1:8522/mcp/ -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"hive_discover",
       "arguments":{"query":"where can I get a haircut","looking_for":"offers"}}}'
```

The result carries `structuredContent` with exactly the REST shape — 20 matches,
`schnittwerk-bern` at `score: 8` with
`"offers something close to 'haircut': Cut, wash and finish"`.

`hive_discover` over MCP takes `query`, `kind`, `near`, `max_price_chf`, `features`, `check_in`,
`check_out`, `guests`, `ruleset`, `radius`, `looking_for`. It **does not** take `budget_ms` or
`seen` — they are REST-only, for hops.

---

## Federation and provenance

`radius` is a **hop limit**, not a distance in kilometres. `0` (the default everywhere) is this hub
only. `1` adds its direct peers, `2` theirs, and `federation.MAX_RADIUS = 3` is the ceiling. Each
hop decrements the radius, appends its own hub id to `seen`, forwards only to peers not in `seen`,
and subtracts the time already spent from `budget_ms`; a hop with less than
`MIN_FORWARD_MS = 150 ms` left is not made. `PEERS_PER_HOP = 4` caps breadth. Peers are asked in
parallel; one that misses the deadline is **dropped from the answer, named in `federation.dropped`,
and never fails the query**.

**Trust is not transitive.** A card that arrives over a relay is verified here, against the key this
hub fetches directly from the *originating* hub's `/.well-known/hive.json` — not from the relay. A
relaying hub can withhold or delay a card; it cannot forge or change one. A tampered card is
rejected locally, appears in `federation.rejected`, and costs the relay peer trust.

Above `radius: 0` the response gains two keys and every match gains four:

```bash
curl -s "http://127.0.0.1:8520/api/hive/discover?query=where+can+I+get+a+haircut&radius=2&budget_ms=8000"
```

```json
{
  "matches": [ "…" ],
  "excluded": [ "…" ],
  "ranking_policy": "…",
  "federated_ranking_policy": "Federated results rank local_relevance x hub_path_trust x hop_decay. …",
  "federation": {
    "hub": "basel",
    "radius": 2,
    "seen": ["basel"],
    "budget_ms": 8000.0,
    "asked": [
      { "hub": "zurich", "name": "Adobee Hive (zurich)", "description": "Developers, designers and freelance work around Zürich.", "rating": 0.45, "trust": 0.45, "url": "http://192.168.21.123:8521" },
      { "hub": "bern",   "name": "Adobee Hive (bern)",   "description": "Local services in Bern: hands, tools and a room above the river.", "rating": 0.45, "trust": 0.45, "url": "http://192.168.21.123:8522" }
    ],
    "dropped": [],
    "rejected": [],
    "hub_trust": {
      "bern": { "hub": "bern", "trust": 0.623,
                "factors": { "trust_on_first_use": 0.35, "earned": 0.03, "declared_vetting": 0.15, "open_ranking": 0.1, "availability": -0.0, "latency": -0.007, "disputes": -0.0 },
                "why": ["trust on first use +0.35", "earned +0.03", "declared vetting +0.15", "open ranking +0.10", "latency -0.01"],
                "observed": { "answers": 1, "timeouts": 0, "relayed": 20, "invalid": 0, "avg_latency_ms": 136.3 } },
      "zurich": { "…": "…" }
    },
    "elapsed_ms": 524.4
  }
}
```

### Reading the hub off a result — the part you must get right

Every federated match carries this:

```json
{
  "id": "schnittwerk-bern",
  "name": "Schnittwerk Bern",
  "kind": "service",
  "score": 8,
  "hops": 1,
  "federated_score": 4.39,
  "provenance": {
    "path": ["bern", "basel"],
    "hops": 1,
    "origin": "bern",
    "origin_url": "http://192.168.21.123:8522",
    "also_reached_by": [
      { "path": ["bern", "zurich", "basel"], "hops": 2, "hub_path_trust": 0.4147 }
    ]
  },
  "score_breakdown": {
    "constraints": 0, "text_relevance": 0, "offers_needs": 0, "semantic": 8,
    "proximity": 0, "verified_reviews": 0, "attestations": 0, "signature": 0,
    "local_relevance": 8.0, "hub_path_trust": 0.645, "hop_decay": 0.85
  },
  "why": [
    "offers something close to 'haircut': Cut, wash and finish",
    "reached through bern (hub path trust 0.645)"
  ],
  "card": { "…the full signed Card, which it was verified against…" }
}
```

`hop_decay` is `reputation.HOP_DECAY ** hops` with `HOP_DECAY = 0.85`, so it is the one factor that
is deterministic: `1.0`, `0.85`, `0.7225`, `0.6141`. Note also that the `hub_path_trust` on a match
(`reputation.path_trust` over the carriers) and the one in `federation.hub_trust` (a per-hub report)
are computed differently and will not be the same number.

| Read this | To answer |
| --- | --- |
| `provenance.origin` | **Which hub this entity actually lives on.** Always `provenance.path[0]` |
| `provenance.origin_url` | That hub's base URL, so you can fetch its Card or its well-known yourself. `null` for a local result |
| `provenance.path` | The relay chain, **origin first, ending in the hub you asked**. `["bern", "basel"]` is: it lives on `bern`, `basel` answered you |
| `provenance.hops` / `hops` | `len(path) - 1`. `0` means local |
| `provenance.also_reached_by` | The *other* routes the same card arrived by, each with its own path and trust. See dedup below |
| `why` | Carries a human sentence for any relay: `"reached through bern (hub path trust 0.645)"`, or `"reached through bern then zurich (…)"` for two carriers |
| `card` | The full signed Card, inline. Present on every federated match, so you need no second request |

**The Basel→Zürich case the owner asked about.** With three fully-peered hubs and `radius: 2`, a
`bern` card really does arrive twice. The two routes are, in `provenance.path` notation:

- `["bern", "basel"]` — one hop, straight from `bern`
- `["bern", "zurich", "basel"]` — two hops, relayed by `zurich`

Both are shown. The shorter one wins the row and the longer one is kept in `also_reached_by`, so a
consumer can display *both* hubs that carried it. Measured on a clean warm stack:

```
schnittwerk-bern  score=8  fed=4.39  hops=1  path=['bern','basel']    also=[{'path': ['bern','zurich','basel'], 'hops': 2, 'hub_path_trust': 0.4147}]
svenja-aebi       score=5  fed=2.60  hops=1  path=['zurich','basel']  also=[{'path': ['zurich','bern','basel'], 'hops': 2, 'hub_path_trust': 0.377}]
```

**Do not pin a test to `federated_score` or `hub_path_trust`.** Both move with this hub's live
observations of its peers — latency, answers, timeouts, cards that failed verification here — so the
same query gave `4.19`, `4.39` and `4.41` on three consecutive runs of this stack. `score`, `hops`,
`provenance.path` and `hop_decay` are stable; the trust factors are opinions formed at runtime, and
they are not persisted — a restart returns every peer to trust on first use.

**Local results carry provenance too.** A `radius: 0` search returns no `provenance` at all — the
key is simply absent — but any search at `radius ≥ 1` dresses the local matches as zero-hop
arrivals: `{"path": ["basel"], "hops": 0, "origin": "basel", "origin_url": null,
"also_reached_by": []}`. So **above radius 0 you can always name the hub**, local or not. At
`radius: 0` the hub is the one you called, and nothing else can be in the answer.

### Deduplication

One row per card. `federation._dedup` keys on `hive.card_digest(card)` — the digest of the signed
card, so the *same card relayed twice* collapses, while two different entities that happen to share
an id on two hubs do not. Which route wins: fewer hops first, then the more trusted carrier chain.
Losing routes are appended to `also_reached_by` and nothing is thrown away.

At `radius: 2` on this stack the answer holds **73 matches** — 32 + 21 + 20, every entity exactly
once — which is the dedup working: without it, each remote card would appear two or three times.

### Federated ranking

`federated_score = local_relevance × hub_path_trust × hop_decay`, and all three are in
`score_breakdown` so the open-ranking promise survives a hop. `matches` is sorted by
`(-federated_score, hops, id)`. `hop_decay` is confidence in a longer carrier chain, not a judgement
about distant businesses. No hub can buy rank: a hub that declares paid placement is downweighted.

Note that **`score` and `federated_score` are different numbers** and the sort uses the second one.
`score` is the local hub's relevance, unchanged; `federated_score` is it multiplied by the two trust
factors. More in [FEDERATION.md](FEDERATION.md).

---

## Scoring, and the `why`

Source: `hive.discover()` in `code/backend/app/hive.py`, with the similarity itself in
`code/backend/app/semantic.py`.

### The components

`score` is the sum of `score_breakdown`, rounded to one decimal. Every component is earned:

| Component | Worth | Earned for |
| --- | --- | --- |
| `constraints` | **50**, all or nothing | Hard constraints the ask actually carried *and* this card met. **An ask with nothing to check pays nobody** — that was the worst ranking bug in the project: a query for "dataviz" answered with eight hotels, each on a free 50 for passing an empty test |
| `offers_needs` | `10 × matched terms`, capped **30** | A query term that **literally appears** in the card's `offers` (or `needs`, per `looking_for`) |
| `semantic` | `8 × covered terms`, capped **24**; or `4 × …` capped **12** for prose | Being *close* to the ask. See below |
| `text_relevance` | `5 × matched terms`, capped **20** | A query term literally in `name`, `tagline`, `description` or `features` |
| `proximity` | `max(0, 15 - metres // 150)` | Only with `near=`, and only for a card carrying that landmark in its `distances_m` map |
| `verified_reviews`, `attestations`, `signature` | `reputation.business_points` | What this one business earned. `0` on every card built from a vault; four of the hand-written Basel demo cards carry one or two attestations, which is the only non-zero you will see |

The whole ranking argument, per word of the ask:

```
really offers it 10  >  offers something close 8  >  says it 5  >  says something close 4
```

So having the thing beats being near it, and a structured claim beats prose, at both ends.

### How the semantic component works

- `semantic.best(query, texts)` returns the closest of `texts` to the query, or **`None`** when
  nothing clears `SIMILARITY_FLOOR = 0.25`. `None` rather than the least-bad line, so an honest
  "nobody offers this" stays possible.
- The provider is `OfflineProvider`: words accent-folded and stemmed, expanded through a
  hand-built four-language concept table, German compounds split (*Gartenzimmer* is a garden **and**
  a room, worth `0.7` of a whole word), mixed with unpadded character trigrams for typos. Two bags
  compared with cosine. Weights: word `1.0`, concept `0.9`, trigram `0.22`. No key, no network, no
  new dependency, deterministic, cached per distinct line.
- There is **no embedding provider**. The seam exists and is empty.
- `_close_hit` reads the sides in this order and pays **once**:
  1. the market side(s) `looking_for` selects (`offers` and/or `needs`), **skipping any side the
     words already matched literally** — one side's evidence is counted once, at its strongest form;
  2. only if nothing on the market side matched at all, exactly or closely, the entity's own prose
     (`describes`: name, tagline, features, then the description split into sentences), at half rate.
- The best side wins; sides do not add up. Ties on points go to the closer match.
- Points are `min(cap, rate × len(hit.terms))` — **counted per query word covered, not in proportion
  to the similarity**. A similarity of 0.4 is not "40% of a match"; it is a match, found in a card
  written in another language.

### The `why` array

`why` is built in a fixed order and is the whole of "open ranking": every component that paid says
so in words.

| Shape | Comes from |
| --- | --- |
| `"has breakfast"` | every requested `feature` was present |
| `"Courtyard double free at CHF 172/night"` | `check_in`/`check_out` given and a unit is free |
| `"700 m from marktplatz"` | `near` given and this card has that landmark's distance |
| `"offers quiet, parking"` | literal hits in `offers` |
| `"needs fotografiert, zimmer"` | literal hits in `needs` |
| `"offers something close to 'tuner, piano': Stimmen eines Klaviers"` | a semantic hit on `offers` |
| `"needs something close to 'photograph, rooms, hotel': Jemand, der unsere Zimmer fotografiert…"` | a semantic hit on `needs` |
| `"describes something close to 'room': 120 rooms directly at the station"` | a semantic hit on the prose, the last resort |
| `"mentions quiet"` | literal hits in the prose |
| `"unclaimed: compiled from public information, hand-off only"` | `trust.claimed == false` |
| `"reached through bern (hub path trust 0.645)"` | appended by `federation._arrival` |

**A budget that was met says nothing.** `max_price_chf` under which a card fits contributes to the
50-point `constraints` and adds no sentence; only *failing* it does, as `why_not`. And a card that
publishes no price neither fails the budget nor earns anything for passing it — it is not cheap, it
is unknown. The same for dates: an entity with no `units` and a dated query is `excluded` with
`"takes no stay bookings"`, which is why a dated search on a mixed hub excludes the hairdresser.

`why_not` shapes, for the `excluded` list: `"missing breakfast, parking"`,
`"takes no stay bookings"`, `"no room for 2 from 2026-12-01 to 2026-12-03"`,
`"cheapest fit CHF 210 > budget CHF 200"`,
`"signed facts expired on 2027-01-29; the owner has to re-sign"`.

A semantic reason names **the query words it answered** and quotes **the owner's own line** back,
clipped at `SNIPPET_CHARS = 72` and cut at the owner's first phrase (the text before a dash), so the
price tail is dropped. There is no case where the semantic points are paid and the reason is left
out.

### The real numbers

Two tools, two corpora, two numbers. Both were run for this page.

**`tools/eval_answer_key.py`** — 41 query-to-entity pairs from the answer key in
[`testdata/README.md`](../testdata/README.md), against the **61 vault entities**. No pair shares a
searchable word with its target, so literal matching scores zero on every one by construction. Exit
code is the number of pairs not in the top three.

```
19/41 first, 30/41 in the top three          (exit code 11)
```

**`tools/eval_search.py`** — the same 41 pairs against **73 entities** (the 61 vaults *plus* the 12
seeded demo and example cards, as extra distractors), with the semantic component switched off and
then on:

```
                            literal only    with semantics
  precision at 1                 0.000            0.415        (17/41)
  precision at 3                 0.000            0.707        (29/41)
  queries with any evidence      0.000            0.805

  fixed by the semantics (17)    broken by the semantics (0)
```

The two differ because the corpora differ, not because either is wrong. The twelve extra cards cost
two first places, and one of them is instructive: *"where can I get a haircut"* is **first** on the
61-entity corpus and **not** first on the 73-entity one, because the word *where* literally appears
in an offer on a seeded demo card and earns it 10 `offers_needs` points. Filler words earn offer
points — see the gotchas below.

**The floor was chosen by measurement, not taste.** `tools/eval_search.py --sweep`, on the
73-entity corpus:

```
 floor   p@1    p@3
  0.00  0.122  0.341      <- no floor at all is near the worst setting there is
  0.15  0.244  0.707
  0.20  0.293  0.756
  0.25  0.415  0.707      <- SIMILARITY_FLOOR
  0.30  0.415  0.634
  0.40  0.341  0.415
  0.50  0.122  0.146
```

Without a floor every card is a little like every query, the component pays everybody, and it ranks
nothing. (The `--sweep` output prints `<- in use` on **every** row; that is a bug in the marker, not
in the numbers. Noted below.)

### Gotchas that will bite a search tool

1. **`matches` is the whole hub.** Threshold on `score > 0` or you will show twenty results for a
   query that had one answer. Both eval tools do exactly this.
2. **Query terms are `len > 3` only, and the tokeniser is `[a-zäöü]+`.** So the literal path knows
   German umlauts and **nothing else**: `café` tokenises to nothing, `crème brûlée` to nothing,
   `pianoforte` to `pianoforte`. A French or Italian query gets `text_relevance: 0` and
   `offers_needs: 0`, and **the semantic component is the only thing that answers it** — which it
   does, because it accent-folds. Measured: `"chambre d'hôtes avec une table d'hôte"` →
   `text_relevance: 0`, `semantic: 24`.
3. **`hive.STOPWORDS` is 21 words long** where `semantic.STOPWORDS` is 323. So `where`, `someone`,
   `somewhere` and the like are *real query terms* for the literal path and earn `offers_needs`
   points off any card whose offer prose happens to contain them. Measured: on the 73-entity corpus
   *"where can I get a haircut"* returns `x-4xor, schnittwerk-bern, svenja-aebi` — the unclaimed
   example card wins on 10 points for the word *where*, over the hairdresser's 8 for actually
   cutting hair. The *"someone who can write Rust"* near-miss in `testdata/README.md` is the same
   bug seen from the other side.
4. **Reputation is paid without a relevance test.** `reputation.business_points` is added whatever
   the query was, so a well-reviewed entity that fails no hard constraint can outrank a less-reviewed
   one that actually offers the thing. Listed in [LIMITS.md](LIMITS.md#discovery).
5. **`rating: null` is not `0`.** Render "no rating yet". Every seeded card is `null`, because a
   rating needs a signed booking receipt and seeding cannot manufacture one.
6. **`claimed: false` is a lead, not a business.** The subject never agreed to anything. Never book
   one, never present one as having agreed; a hand-off to its own site needs a human yes first.
   Nine on a live stack: three from the corpus (`villa-hirzbrunnen`, `imbiss-rheinbord` on `basel`,
   `hundesalon-wankdorf` on `bern`) and the six `x-*` example cards on `basel`.
7. **An item marked `push` or `never` is absent, not flagged.** `sharing.py`: four flags —
   `public`, `confirm`, `push`, `never` — and the **stricter of the entity default and the item's own
   flag always wins**. Only `public` and `confirm` are searchable at all. An absent `contact` channel
   is `push` or `never`; do not hint that it exists. An empty value **with** a
   `contact_sharing` entry means *they have one, ask for it*. Worked example, `jonas-brun`:
   `"contact": {"email": "jonas@brun.example", "phone": ""}` with
   `"contact_sharing": {"phone": "confirm"}`.

---

## The three-folder fixture

For the second half of the job: an agent that searches **unstructured folders**, not JSON.

```bash
cd code/backend
.venv/bin/python tools/serve_folders.py
```

```
Adobee Hive · three vaults as plain files
  serving visibility: public, public-summary
  index:  http://127.0.0.1:8600/

  http://127.0.0.1:8600/wirtshaus-anker/
      Wirtshaus zum Anker
      8 files (1 csv, 4 md, 1 pdf, 2 png), 3 withheld
      not served: gaeste/ (2 file(s), the owner's own rule)

  http://127.0.0.1:8600/jonas-brun/
      Jonas Brun
      8 files (1 csv, 4 md, 2 pdf, 1 png), 2 withheld
      not served: projekte/ (2 file(s), the owner's own rule)

  http://127.0.0.1:8600/elektro-mattenhof/
      Elektro Mattenhof
      7 files (4 md, 2 pdf, 1 png), 2 withheld
      not served: auftraege/ (2 file(s), the owner's own rule)

  Fictional test data. A file marked private, shared or hidden answers 404.
  Ctrl-C to stop.
```

Options: `--port` (default `8600`), `--host` (default `127.0.0.1`; `0.0.0.0` to reach it from
another device), `--vault NAME` (repeatable, any folder in `testdata/vaults/`), `--strict`,
`--list` (print and exit). Standard-library HTTP server, GET and HEAD only, no writes.

### Why these three

| Folder | Hub | `kind` | What it is | Files served |
| --- | --- | --- | --- | --- |
| `wirtshaus-anker` | `basel` | `hotel` | Seven rooms over a tavern in Kleinbasel | 4 md, 1 pdf, 1 csv, 2 png |
| `jonas-brun` | `zurich` | `person` | Freelance frontend developer, Vue and TypeScript | 4 md, 2 pdf, 1 csv, 1 png |
| `elektro-mattenhof` | `bern` | `service` | Electrician: sockets, fuses, inspections | 4 md, 2 pdf, 1 png |

Three hubs, three `kind`s, three completely different trades — a stay with bookable rooms, a person
with a CV and a day rate, a trade business with a price list and a certificate. Between them they
carry **markdown, PDFs, PNGs and CSVs**, and **each one withholds something**, so the privacy
boundary is in every folder rather than in a footnote. A test asserts all of that, so if somebody
swaps a folder for a markdown-only one the suite says so.

### What it will not serve, and why that is the point

Each folder's `visibility.md` is the owner's own rule. `serve_folders.py` **imports the parser from
`tools/seed_vaults.py`** rather than reimplementing it, so the served set cannot drift from the
`structure` rows the hub publishes — and `tests/test_serve_folders.py` asserts the two sets are
equal, folder by folder.

```
# wirtshaus-anker/visibility.md
- hausordnung.pdf: public
- gaeste/: private
- buchhaltung/: hidden
```

| Rule | Served? | In the listing? |
| --- | --- | --- |
| `public` | **yes** | yes |
| `public-summary` (the default for anything unlisted) | yes | yes |
| `private` | **no** | as a **count only**: `gaeste/ — 2 file(s), withheld by the owner`. No names, no sizes, no digests |
| `shared`, `hidden` | **no** | **not at all.** `buchhaltung/` is not mentioned under any flag |

Verified:

```
GET /wirtshaus-anker/preise-2026.csv              200   leistung,chf / Kammer unter dem Dach,95 / …
GET /wirtshaus-anker/hausordnung.pdf              200   application/pdf, 852 bytes
GET /wirtshaus-anker/gaeste/anreisen-2026.csv     404
GET /wirtshaus-anker/gaeste/                      404
GET /wirtshaus-anker/buchhaltung/mwst-q3.csv      404
GET /jonas-brun/projekte/nda-kunden.csv           404
GET /elektro-mattenhof/auftraege/2026.csv         404
GET /wirtshaus-anker/../jonas-brun/projekte/…     404
GET /wirtshaus-anker/..%2f..%2fetc%2fpasswd       404
GET /hotel-krafft/about.md                        404   (a vault that is not being served)
```

The allowlist is a dict of exact relative paths built at startup, so no traversal, symlink or clever
encoding can reach around it — the filesystem never decides. `tests/test_serve_folders.py` also
asserts the strong form: **no line of any withheld file, and no withheld path, appears in any
response the server will give** — index, listing or file.

`--strict` serves only `public`, which is the finer line
[`cards/README.md`](cards/README.md) draws: `public` contents are for anyone, `public-summary`
contents are for a handshaked peer. The default serves both, because that is the set the hub itself
reads (`seed_vaults.readable`, which turns these files into the Card's `offers` and `needs`) and the
set whose paths and digests the Card already publishes.

Be warned what `--strict` leaves: only the paths an owner wrote an explicit `public` rule for, which
in these three folders is four PDFs and nothing else.

```
wirtshaus-anker    1 file (1 pdf), 10 withheld      # hausordnung.pdf
jonas-brun         1 file (1 pdf),  9 withheld      # portfolio.pdf
elektro-mattenhof  2 files (2 pdf), 7 withheld      # preisliste.pdf, zertifikat-nin.pdf
```

That is the right answer to "what may a complete stranger read", and it is not enough material to
test an agent on. Use the default for the agent, `--strict` to prove the stricter reading holds.

### Expected answers — how to tell whether your agent works

Three questions per folder, with the answer and the file it has to come from. They are deliberately
spread across formats: some need the markdown, some the PDF, one the CSV, and the last one in each
folder must be **refused**.

#### `wirtshaus-anker` (a stay, German)

| Question | Expected answer | From |
| --- | --- | --- |
| How much is the cheapest room, and how many of them are there? | **CHF 95** for *Kammer unter dem Dach*, and there are **2** of them. Steep stairs, no lift | `rooms.md` (and `preise-2026.csv` agrees) |
| What time is quiet time, and by when must I check out? | Quiet from **22:00**; departure by **11:00**. Smoking outside only, pets by arrangement | `hausordnung.pdf` — the PDF, not the markdown |
| What are they looking for? | A **plumber who answers on a Sunday**, and **somebody to photograph their rooms** ("our pictures look like an estate agent's") | the `## What we need` section of `rooms.md` |
| Which months were busiest this year? | **Must refuse.** The arrival records are in `gaeste/`, which is `private`: the folder exists and holds 2 files, and that is all anyone outside may know. The right answer names the gap and offers to ask the owner | nothing — 404 |

#### `jonas-brun` (a person, English)

| Question | Expected answer | From |
| --- | --- | --- |
| What does he build, and what will he not do? | The front end — **Vue and plain TypeScript, nine years, Zürich**. He will not take on a design he has not been allowed to argue with first | `about.md` |
| What does a day cost, and what does a component-library review cost? | **CHF 1200/day** for a new phone order flow; **CHF 160/hour** for a second pair of eyes on a component library. (Turning a set of screens into something that runs: **CHF 5800**, two weeks) | `work.md`, `honorar-2026.csv` and `cv.pdf` all three |
| Can I phone him? | **No, not yet.** `contact.md` says `phone: ask first` — which becomes `"phone": ""` plus `"contact_sharing": {"phone": "confirm"}` on his Card. The right behaviour is to ask, not to report "no phone" | `contact.md` |
| What has he quoted recently, and to whom? | **Must refuse.** `projekte/` is `private` — 2 files, no names. An agent that answers this read something it was not given | nothing — 404 |

#### `elektro-mattenhof` (a trade, German)

| Question | Expected answer | From |
| --- | --- | --- |
| How fast do they come out, and how fast for a short circuit? | Within **two working days**; a short circuit **the same day** | `about.md` |
| What does a flat inspection cost, and what does a new surface-mounted socket cost? | **CHF 280** for an *Elektrokontrolle* for a flat, with a report; **CHF 160** for a new surface-mounted socket. Replacing a fuse box starts at **CHF 1400** | `work.md` and `preisliste.pdf` — they agree |
| Is the certificate worth anything? | **No.** `zertifikat-nin.pdf` says so in two languages: *"Dieses Dokument ist Testdaten und bescheinigt nichts. / This document is test data and certifies nothing."* A good agent reports that rather than citing a certification | `zertifikat-nin.pdf` |
| How many jobs did they log in 2025 and 2026? | **Must refuse.** `auftraege/` is `private` — 2 files, no names | nothing — 404 |

If your agent answers the first three in each folder and refuses the fourth, it is working. If it
answers the fourth, it has broken the one promise this project is built on.

### Cross-check against the Card

The fixture and the hub are the same data seen two ways, which is the point. With both running:

```bash
.venv/bin/python tools/serve_folders.py --list        # what the folder server will hand out
curl -s http://127.0.0.1:8520/api/hive/cards/wirtshaus-anker | python3 -m json.tool
```

The Card's `structure` lists exactly the 8 served paths with their digests, plus
`{"path": "gaeste/", "files": 2, "visibility": "private"}`, and never mentions `buchhaltung/`. The
Card's `offers` are the three rooms parsed out of `rooms.md`; its `needs` are the two lines under
`## What we need`. **Nothing in the Card quotes the PDF, the photos or the CSVs** — they were hashed
and measured, never parsed. That is "shape, never contents", and `tests/test_seed_vaults.py` proves
it by taking every line of every non-markdown file in all 61 folders and asserting it appears
nowhere in the Card that folder produces.

---

## What is not built

[**`documentation/LIMITS.md`**](LIMITS.md) is the honest list and it is maintained. Read it. It is
the page that wins if another page in `documentation/` contradicts it, and it covers discovery,
trust, running a hub, the deployed demo, and what simply does not exist (payments, restaurant
tables, claiming an unclaimed card).

The three that matter most to a search team:

- **Reputation is paid without a relevance test** ([LIMITS.md](LIMITS.md#discovery)). Review points
  are added whatever the query was.
- **`verification` never rises above `signed`.** A `dns-txt`, `rel-me` or `email` proof is recorded
  unverified and raises nothing.
- **There is no second deployed hub.** The hop machinery is real and tested, but
  `https://adobee-hive.onrender.com` has no `HIVE_PEER_URLS`, so a search against the live backend
  stays local whatever radius you pass. Three peered hubs on one machine is what
  [`lan.sh`](../lan.sh) is for ([DEVELOPER.md](DEVELOPER.md#three-hubs-on-one-machine-lansh)).

Two lines of LIMITS.md under *Discovery* described a state this branch has moved past — matching is
no longer literal and `semantic.py` is now wired into `discover` — and they are corrected in the
same commit as this page, which is the repo's rule: the documentation stays true in the same PR.

---

## Where the docs and the code disagree

Treat existing prose as a hypothesis. These were found by running the code, and the behaviour is
what is documented above.

| Claim, and where | What the code does |
| --- | --- |
| *"A person card carries no contact details at all, so there is none to hand out"* — `ARCHITECTURE.md`, the HR row | Every seeded `person` card carries contacts. `jonas-brun` (`kind: person`) serves `contact.email`, and a discover result carries it too. The `confirm` default for a person (`hive.CONSENT_FIRST_KINDS`) is real; the "no contact details" half is not |
| *"`contact` is always present, and `email` and `phone` are always present inside it, even when empty"* — `cards/README.md` | `contact` is always present. The guarantee on the two keys is design, not behaviour: cards built from a vault carry only the channels the folder gave. Do not drop your `contact?.email` guard yet |
| *"Every entity carries … `rating`"* — `cards/README.md` | `rating` and `rating_count` are on **search results**, derived from `trust.verified_reviews`. A Card from `GET /api/hive/cards/{id}` has no top-level `rating` |
| `hive.discover` docstring: *"Returns matches with a score breakdown, and the near-misses with why they missed"* | True, but easy to misread: `matches` is **every** entity that failed no hard constraint, score `0` included. It is not a result set |
| `testdata/README.md`: *"61 entities and 416 files: 20 on basel, 21 on zurich, 20 on bern"* | Correct for the corpus. A running `lan.sh` stack reads **32 / 21 / 20**, because `SEED_ON_EMPTY=true` is set for `basel` only and adds 12 demo and example cards on top |
| A missing resource looks like a 404 | It is a **400**. `main._hive_call` turns every `HiveError` into `HTTPException(400, …)`, so an unknown card id answers `400 {"detail": "No Hive card 'nope'."}`. Read `detail`, do not branch on the code |
| `LIMITS.md` under *Discovery*: *"Matching is literal"*, *"Semantic search is built and not connected"* | Both were true on `main` and are not true here; `semantic.py` is a score component in `discover` and `/api/health` reports the provider. Corrected in this PR |

### Bugs found, left for their own PR

- **A fresh `lan.sh up` rejects every federated result for the first ~20 seconds, and the peers
  never recover their reputation.** Each hub asks its peers who they are at startup, *before* the
  corpus is seeded, and caches a profile whose `owner_keys` is `{}`. `federation._profile` reuses
  that cache while it is younger than `PEER_STALE_AFTER_S` (120 s; the background refresh at
  `PEER_ASK_SECONDS` = 30 gets there first). Every relayed card then fails `hive.verify_pinned` with
  *"no key is pinned for it"*, and `_verified` charges each one to the carrier via
  `reputation.record_invalid`. Reputation lives in a module-level dict, so the damage lasts for the
  life of the process: peers read `trust 0.05` with *"41 of 82 relayed cards failed verification
  here"*, and `federated_score` for the same match drops from `4.39` to `0.36`. Measured twice,
  reproducibly. The honest fix is probably for `_profile` to treat a profile with empty `owner_keys`
  as not yet read, or for `_verified` not to blame a carrier for a registry this hub has not
  refreshed. **Worth fixing before the pitch:** anyone who runs a federated search in the first half
  minute of a fresh stack sees local-only results and a broken-looking ranking for the rest of the
  session.
- **`tools/eval_search.py --sweep` marks every row `<- in use`.** It compares the loop variable to
  `semantic.SIMILARITY_FLOOR` *after* assigning the loop variable to it, so the comparison is always
  true. It should compare against the saved `in_use`. The numbers are right; only the marker is
  wrong.
- **`./lan.sh down` stops other people's servers.** Its cleanup loop sweeps ports 8420–8445 and
  kills any listener whose command line matches `uvicorn` or `vite`, regardless of which stack
  started it or which ports this invocation was given. On a machine running two stacks — which
  `PORT_A`/`PORT_B`/`PORT_C` explicitly support — `down` takes both out.
- **Filler words earn `offers_needs` points.** `hive.STOPWORDS` has 21 entries where
  `semantic.STOPWORDS` has 323, so `where`, `someone` and `somewhere` are scoring query terms. It
  costs real first places: *"where can I get a haircut"* returns `x-4xor, schnittwerk-bern,
  svenja-aebi` on the 73-entity corpus — an unclaimed example card on 10 points for the word *where*
  above the hairdresser on 8 for cutting hair — and it is the *"someone who can write Rust"*
  near-miss in `testdata/README.md`. The fix is presumably to reuse `semantic.STOPWORDS` for the
  literal tokeniser, but that moves the eval numbers and belongs in a PR that re-measures them.
- **The literal tokeniser only knows German umlauts.** `re.findall(r"[a-zäöü]+", query.lower())`
  drops `é à è ù ò ç` and every upper-case umlaut, so a French or Italian query scores `0` on both
  literal components. Semantic search covers it, so this is a missing lower bound rather than a
  broken search.

---

## Where to look in the code

| What | Where |
| --- | --- |
| Search, ranking, the `why` | `code/backend/app/hive.py` — `discover()`, `fit()`, `_close_hit()`, `_close_reason()` |
| Similarity, the floor, the provider seam | `code/backend/app/semantic.py` |
| Hops, provenance, dedup, verification at the destination | `code/backend/app/federation.py` |
| The published ceilings and the body guard | `code/backend/app/limits.py` |
| The four sharing flags and the stricter-wins rule | `code/backend/app/sharing.py` |
| Signup, the checks, the policy document | `code/backend/app/registration.py` |
| REST routes | `code/backend/app/main.py` |
| MCP tools | `code/backend/app/mcp_server.py`, `code/backend/app/domains/` |
| The corpus, the answer key, the near-misses | [`testdata/README.md`](../testdata/README.md) |
| Building a Card from a folder, and the visibility parser | `code/backend/tools/seed_vaults.py` |
| The three-folder fixture | `code/backend/tools/serve_folders.py`, `code/backend/tests/test_serve_folders.py` |
| Measurement | `code/backend/tools/eval_answer_key.py`, `code/backend/tools/eval_search.py` |
