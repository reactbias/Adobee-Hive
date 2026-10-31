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

**In this model `rating` is tenths of a star, not stars.** `43` → `4.3 / 5`. Divide by 10 for
display. The resolution is deliberate: 4.3 is a real answer and integers do not drift when averaged.

**The live backend does not serve this field in tenths yet.** `GET /api/hive/discover` and
`GET /api/admin/entities/{id}` return `rating` as the verified-review average on the 1-to-5 scale a
review is left on (`4.33`, or `null`), because `hive.review` takes 1 to 5. Tenths is already the
unit everywhere a *hub* is involved — a connection score (`hub_score`,
`POST /api/hub/connections/{id}/score`, 0 to 50) and a calibration error are tenths, and
`hub._published_rating` multiplies the review average by ten to record one. Two scales, both
correct, and converting in the wrong direction is the bug to watch for.

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

## How this relates to what runs today

The live backend serves a simpler card (`code/backend/app/hive.py`) and is converging on this.

| In this model | On `main` today |
| --- | --- |
| `name`, `description`, `rating_count` | served, same meaning |
| `rating` as tenths, 0–50 | served as the 1-to-5 review average, or `null`. See the two scales above |
| `contact` always present, `email` and `phone` always inside it | served, and guaranteed by `hive.with_contact`, which fills the keys without inventing values |
| `contact_sharing`, per-item sharing flags | served. `sharing.py` resolves the entity default against the item's own flag, stricter wins |
| `offers` / `needs` as both sides of one market | **this is the live index.** `hive.discover` searches both and `looking_for` picks a side; the field shapes here are richer than what is stored |
| `keys`: `sig` Ed25519 **and** `kex` X25519 | **not built.** Only the Ed25519 signing key exists; nothing in the backend does key exchange, and the `kex` entry in the two card files above is model, not code |
| `id` as `hive:<hub>/<entity>` | a plain lower-case id (`hotel-krafft`), with the hub named separately in a result's `provenance` |
| `seq`, `structure`, portable `attestations`, `policy.handshake` | still design |

So: **build against `name`, `description`, `rating_count`, `contact` and `contact_sharing` now** —
they are served today — and read `rating`'s scale off the endpoint you called. Treat the rest as the
direction of travel. [FEDERATION.md](../FEDERATION.md) is the architecture, and
[LIMITS.md](../LIMITS.md) is what is honestly not there. How an entity gets a Card in the first
place is built: [REGISTRATION.md](../REGISTRATION.md).
