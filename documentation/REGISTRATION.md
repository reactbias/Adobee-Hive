# Joining a hub

How a person or a business gets into a Hive, in one signed JSON document, and what the hub does
with it.

A registration is not an account. It is an **application**, and the hub may refuse it. That matters
more than it sounds, and the reason is in [FEDERATION.md](FEDERATION.md): a hub's standing with its
peers is measured by whether its published ratings survive contact with real people. A hub that
lets anyone in will publish claims it cannot stand behind, its calibration error will climb, and
*every* entity it carries will rank lower everywhere. **Vetting is self-interest, not altruism.** It
is why a federated directory can work without anybody in charge of it.

## Choosing a hub first

Before you can join a federated network you have to pick a door, and a list of names is not enough
to choose by. Mastodon solved this with instances.social, and `GET /api/hub/directory` does the
same job: every Hive we know of, with whether it is taking members, what it asks of them, what it
carries — and one column a Mastodon directory cannot offer, **how honest its ratings have turned
out to be**.

A hub here is not described only by what it says about itself. It is described by whether its
claims survived contact with other people's users.

`GET /api/hub/registration` then gives the rules of one hub, including the exact document to send,
so nobody writes an application for a hub that turns out to be invite-only.

## The journey

1. **Generate a keypair.** Ed25519. The private key never leaves the applicant's machine.
2. **Compose the application** and sign the canonical JSON of everything except `signature`.
3. **`POST /api/hub/register`**, or the `hub_register` MCP tool if an agent is doing it.
4. The hub runs its checks in order and stops at the first failure.
5. The admission policy decides: admitted at once, queued for a person, or refused.
6. On admission the entity is published into the index and is findable.

```json
{
  "entity": {
    "id": "cafe-neu",
    "kind": "stay",
    "name": "Café Neu",
    "description": "One line someone would recognise you by.",
    "sharing": "public"
  },
  "public_key": "<base64 Ed25519>",
  "proofs": [{ "type": "dns-txt", "subject": "cafe-neu.example" }],
  "invite": "<only when the hub is invite-only>",
  "signature": "<base64, over the canonical JSON of this document without `signature`>"
}
```

A refusal comes back as **200 with `state: "rejected"`**, not a 4xx. A refusal is an outcome, not a
transport error, and a client should read one shape either way. Every answer carries the checks
that ran, the reason, and `next` — what to do now. An answer with no next step is a dead end.

## The checks

In order, stopping at the first failure, so a malformed document gets one useful answer rather
than a pile of consequential ones.

| check | what it establishes |
| --- | --- |
| `shape` | The document is well formed. Ids are 2–63 characters, lower-cased on the way in |
| `signature` | The applicant holds the private key for the `public_key` they sent |
| `blocklist` | Neither the id nor any proof subject is blocked here |
| `availability` | The id is not already registered or applied for |
| `invite` | A token, when the hub is invite-only |

### What the signature proves, and what it does not

It proves the applicant holds that private key. That is all, and it is enough to **pin an
identity**: from then on the hub can tell this applicant from anyone claiming to be them.

It proves nothing about who they are in the world. That is what `proofs` are for, and they are
**recorded rather than trusted**. Nothing is checked over the network during registration — the
demo has to run offline, and a hub that blocks on a DNS lookup is a hub that falls over when a
registrar does. An unconfirmed proof raises nothing. A confirmed one would raise the entity's
`verification`, which peers weigh against what they actually observe, so overstating it is a bad
trade.

**Today nothing confirms one.** `verification_for()` returns `signed` when a valid signature arrived
with a key, and `none` otherwise, so the ladder's top two rungs — `domain` and `identity` — are
unreachable. The honest reading of any entity on this hub is "holds its key, and has claimed some
things nobody has verified". See [LIMITS.md](LIMITS.md#trust).

## Admission policy

Set with `ADMISSION_POLICY`. The default is **`vetted`**, for the reason at the top of this page.

| policy | what it means |
| --- | --- |
| `open` | anything that passes the checks is admitted at once |
| `vetted` | a person reads every application before it is admitted |
| `invite` | an invite token is required, then the checks apply as usual |
| `closed` | this hub is not accepting registrations |

A hub that is shut says so, with all the checks passing — the application was fine; the door is
closed. That distinction matters to someone deciding whether to fix something or go elsewhere.

An operator works the queue at `GET /api/admin/applications?state=pending` and decides with
`POST /api/admin/applications/{id}`. **A refusal needs a reason, and the applicant is told it.**

## Who holds the key

| | `custody: "owner"` | `custody: "hub"` |
| --- | --- | --- |
| How | bring a `public_key` and sign the application | omit the key |
| What the hub learns | the applicant holds this private half, pinned to their id from now on | nothing about who applied |
| On the card | `custody: "owner"` and `owner_public_key` | `custody: "hub"` |
| What a peer sees | that somebody holding a key applied for this id | that the hub vouches for itself |

**What bringing a key does not yet do.** It does not move the card's signature. `hive.publish`
generates and keeps a signing key per card in `hive_keys` either way, and it is that key — not
`owner_public_key` — that is published in `/.well-known/hive.json` under `owner_keys` and used by
every signature check, local or federated. So the jury answer stays **"the server, for the demo; in
the real thing, the owner"**: registration narrows the gap by pinning *who applied* and recording
custody honestly, and the step still missing is signing a card version with the owner's own key. It
is written down in [LIMITS.md](LIMITS.md#trust) and [VISION.md](VISION.md#beyond-the-weekend)
rather than claimed here.

A peer can tell the two columns apart, and should: a card whose signing key the hub holds is a card
the hub could have written.

## Leaving

Your card is yours. A hub carries it; it does not own it. Moving means republishing one file
somewhere else — which is the whole point of [the federation design](FEDERATION.md), and the
reason admission can be strict without being a trap.
