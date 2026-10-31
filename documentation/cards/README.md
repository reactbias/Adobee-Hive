# The Card

What a hub carries, and what an agent gets back. **These four files are the reference.** If the
prose and a file here disagree, the file wins.

| File | What it is |
| --- | --- |
| [hotel-krafft.card.json](hotel-krafft.card.json) | A business. Rated: `43`, which is 4.3 of 5 |
| [lena-designer.card.json](lena-designer.card.json) | A person. **Unrated**: `rating: null`, not `0` |
| [manifest-after-handshake.json](manifest-after-handshake.json) | The *same vault* seen by a connected peer. Proves what the public Card leaves out |
| [example-prepared-transcript.md](example-prepared-transcript.md) | A prepared transcript, with its consent and redaction log |

## Every entity carries three fields

A hub is an entity. A business is an entity. A person is an entity. They read the same way, so one
component renders all three.

| Field | Type | Notes |
| --- | --- | --- |
| `name` | string | Always present. What a person sees in a result |
| `description` | string | One line. May be empty, never absent |
| `rating` | integer or **null** | **Tenths of a star, 0–50.** `43` is 4.3 out of 5 |
| `rating_count` | integer | How many signed receipts produced it |

### Two things to get right

**`rating` is tenths of a star, not stars.** `43` → `4.3 / 5`. Divide by 10 for display. The
resolution is deliberate: 4.3 is a real answer and integers do not drift when averaged.

**`rating: null` means not rated yet. It is not zero.** Render "no rating yet", never an empty star
row and never `0.0`. A business nobody has reviewed is not a bad business, and showing it as one
would be the most damaging bug in the product. `rating_count: 0` always accompanies it.

A rating only exists after a **signed booking receipt** or a **scored introduction** — a real thing
that actually happened. There is nothing to buy and nothing to fake.

## `contact` — always there, keys guaranteed, values may be empty

How you actually reach an entity. **`contact` is always present, and `email` and `phone` are always
present inside it**, even when empty. That is the point: a frontend should never have to guard
`contact?.email?` — the key is there, and an empty string means "not published", which is a thing
you can render.

```jsonc
"contact": {
  "email":   "hallo@hotelkrafft.example",
  "phone":   "+41 61 690 91 30",
  "mobile":  "",                              // exists, but gated — see contact_sharing
  "address": "Rheingasse 12, 4058 Basel, CH",
  "mcp":     "https://hotelkrafft.example/mcp"
},
"contact_sharing": { "mobile": "confirm" }    // only where it differs from the entity default
```

It stays an **open map**: `email` and `phone` are guaranteed, and any other channel may be added —
`mobile`, `address`, `mcp`, `whatsapp`, whatever the entity actually uses. Render the ones you know
and list the rest rather than dropping them.

### An empty value does not always mean the same thing

| What you see | What it means | What to render |
| --- | --- | --- |
| `"email": "hallo@…"` | published | the address |
| `"phone": ""` and no `contact_sharing` entry | not published, nothing to ask for | "not provided" |
| `"phone": ""` with `contact_sharing.phone = "confirm"` | **they have one; ask for it** | "available on request" and a way to ask |
| key absent entirely | `push` or `never` — not your business | nothing. Do not hint at it |

That last row is the same rule as `structure`: a channel the owner marked `never` is **absent**, not
listed as withheld, because listing it in order to say it is private announces that it exists.

`contact_sharing` only carries keys that differ from the entity's default, so an absent entry means
"inherits", not "public".

### After a handshake

`manifest-after-handshake.json` shows the other half: a connected peer sees `contact_released`, where
`mobile` now has the value the public Card showed as empty. Same entity, more trust, more contact —
which is the whole shape of the product in one field.

## The rest of a Card

| Field | What it is |
| --- | --- |
| `id` | `hive:<hub>/<entity>`. Stable, lower-case |
| `seq` | Monotonic, signed. Last writer wins |
| `keys` | `sig` is Ed25519 for signatures, `kex` is X25519 for key exchange. Two keys, two jobs — X25519 cannot sign |
| `links` | Each carries a `proof`: `dns-txt`, `rel-me`, or `none`. **`none` is a claim, not a verification** — show it differently |
| `offers` / `needs` | Both sides of the market in one file. A hotel's `offers` make it bookable; its `needs` make it an employer |
| `structure` | The *shape* of the owner's folder: paths, counts, digests, visibility. Never the contents |
| `contact` | Always present; `email` and `phone` always present inside it, possibly empty. See above |
| `policy` | `handshake` and `human_in_loop` — the threshold above which a person must say yes |
| `attestations` | Counter-signed statements. Portable: they move with the entity between hubs |
| `sig` | Ed25519 over the canonical JSON of everything else |

### `structure.visibility` — five values

| Value | In the Card | Synced to peers | Who reads the contents |
| --- | --- | --- | --- |
| `public` | path · summary · digest | plaintext | anyone |
| `public-summary` | path · summary · digest | encrypted | handshaked peers |
| `shared` | **omitted entirely** | encrypted | handshaked peers |
| `private` | path · count, no digest | no | owner only |
| `hidden` | **omitted entirely** | no | owner only |

`hidden` and `shared` folders are **absent** from `structure`, not listed with a flag. Listing a
folder in order to say it is secret leaks its existence.

That is why `manifest-after-handshake.json` is in this folder. It is the same vault queried by a
connected peer: two prepared transcripts appear that the public Card never mentions, plus 252 files
withheld without naming them. Diff the two files and the privacy model is right there.

## How much room you have

Write the Card first, then check it against this. Every number here is what a hub will accept, and
the hub publishes the same table at `GET /api/hub/registration` so a client can read it before it
composes anything. Nothing on this page is about *what* you write — only how much of it there is.

**`description` is your pitch to an agent, and 2000 characters is room to make it.** In a web whose
visitors are agents, the description is the thing they read, so writing it for discovery is the
point of the field rather than something to apologise for. Name what you do, name the words a
person would actually type, name the things you are good at. A hub does not read your prose, score
its keyword density or form a view about your style.

What stops an entity describing itself as something it is not was never prose analysis — it is the
economic loop. Over-promise, and you get matched to people you cannot help; they meet you, they
score the introduction, and the hub carrying you publishes a rating that turns out to be wrong. Its
calibration error rises ([FEDERATION.md](../FEDERATION.md), `calibration.py`), and *every* entity
on that hub ranks lower everywhere. An honest description is the cheapest thing in the system.

The ceilings exist because an unbounded field is an index that can be flooded, a database that can
be filled and a signed document that stops fitting in a request. They are set from the real corpus
in `testdata/vaults/` with a lot of room to spare, because a limit that refuses a legitimate hotel
is worse than one slightly too generous.

<!-- room -->

| What | Room | What it is for |
| --- | --- | --- |
| `id` | 63 characters | `hive:<hub>/<entity>` without the hub part. Lower case, digits, hyphens |
| `kind` | 32 characters | What sort of entity this is, so a search can narrow by it |
| `name` | 120 characters | What a person sees in a result |
| `tagline` | 200 characters | One phrase under the name |
| `description` | **2000 characters** | Your pitch to an agent. Write it for discovery |
| `offers` | 50 entries | What you provide. Half the index |
| `needs` | 50 entries | What you are looking for. The other half |
| `offers[].title` | 200 characters | The name of one thing you offer or need |
| `offers[].summary` | 600 characters | The line it came from, in your own words |
| `offers[].tags` | 20 entries | Words a search should match that the prose does not carry |
| `features` | 50 entries | Short facts a search can filter on |
| `units` | 100 entries | Bookable rooms or slots |
| `structure` | 1000 entries | One row per file in your folder: path and digest, never contents |
| `contact` | 20 channels | The open map of how to reach you |
| `contact.<channel>` | 200 characters | One channel's value, e.g. a postal address |
| `any other text` | 500 characters | Any string the card carries that is not named above |
| `any other list` | 200 entries | Any list the card carries that is not named above |
| `keys per object` | 64 keys | How many keys one object may carry |
| `nesting` | 12 levels | How deeply a card may nest |
| `the whole card` | 256,000 bytes | The canonical JSON of everything above |
| `the application` | 320,000 bytes | The card plus its key, proofs and signature |
| `the request body` | 1,048,576 bytes | Refused by size before it is parsed into objects |

<!-- /room -->

`needs` is bounded exactly like `offers`, and the two `offers[].*` rows apply to a need as well —
the two sides of the market have the same shape and the same room.

### Three things are tidied, not refused

A hub normalises these on the way in and publishes what it kept, so what it signs is what a reader
sees:

- **Unicode to NFC**, so two spellings of the same character are one string and one digest.
- **Control and zero-width characters out** — ZWSP, word joiner, soft hyphen, the bidi overrides.
  They are invisible to a reader, count against nothing, and change the signature over the
  canonical JSON for no reason anybody can see.
- **Runs of whitespace to a single space**, and the ends trimmed. A Card's text fields are one line
  of prose each.

So a description padded with zero-width characters is not refused; the padding is simply not there
any more, and what is left is measured.

### What a refusal looks like

Over a limit at signup is an answer, not an error: `POST /api/hub/register` returns **200** with
`state: "rejected"`, the checks it got through, and a reason that names the ceiling and your actual
size — `` `description` is at most 2000 characters; this one is 7412 `` — so you can fix it without
guessing. The same ceilings apply to every version after, through `hive.publish`: an entity cannot
join politely and then grow unbounded on its next update. A request body over the last row is
refused with **413** before it is parsed at all.

## How this relates to what runs today

The live backend serves a simpler card (`code/backend/app/hive.py`) and is converging on this. Already
landed: `name`, `description`, `rating`, `rating_count`, per-item sharing flags, and the two-key
split. `contact` is served today as an open map — this page adds the guarantee that `email` and
`phone` are always present, and `contact_sharing` alongside it. Still design: `seq`, `structure`, `offers`/`needs` as modelled here, and portable
`attestations`.

So: **build against the three entity fields now** — they are served today. Treat the rest as the
direction of travel. [FEDERATION.md](../FEDERATION.md) is the architecture. How an entity gets a Card in the first place is
registration, which is in flight.
