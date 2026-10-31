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

## The rest of a Card

| Field | What it is |
| --- | --- |
| `id` | `hive:<hub>/<entity>`. Stable, lower-case |
| `seq` | Monotonic, signed. Last writer wins |
| `keys` | `sig` is Ed25519 for signatures, `kex` is X25519 for key exchange. Two keys, two jobs — X25519 cannot sign |
| `links` | Each carries a `proof`: `dns-txt`, `rel-me`, or `none`. **`none` is a claim, not a verification** — show it differently |
| `offers` / `needs` | Both sides of the market in one file. A hotel's `offers` make it bookable; its `needs` make it an employer |
| `structure` | The *shape* of the owner's folder: paths, counts, digests, visibility. Never the contents |
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

The live backend serves a simpler card (`code/backend/app/hive.py`) and is converging on this. Already
landed: `name`, `description`, `rating`, `rating_count`, per-item sharing flags, and the two-key
split. Still design: `seq`, `structure`, `offers`/`needs` as modelled here, and portable
`attestations`.

So: **build against the three entity fields now** — they are served today. Treat the rest as the
direction of travel. [FEDERATION.md](../FEDERATION.md) is the architecture. How an entity gets a Card in the first place is
registration, which is in flight.
