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
registrar does. An unconfirmed proof raises nothing. A confirmed one raises the entity's
`verification`, which peers weigh against what they actually observe, so overstating it is a bad
trade.

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
| How | bring a `public_key` and sign | omit the key |
| Private half | never leaves the applicant | generated and held by the hub |
| What a peer sees | the owner's pinned key | that the hub vouches for itself |

The hub-held path is what the demo does today, and it is recorded honestly rather than dressed up.
A peer can tell the difference, and should: a card whose key the hub also holds is a card the hub
could have written. The jury answer "the server, for the demo; in the real thing, the owner" is
exactly this field, and bringing a key is how an owner takes that back.

## Leaving

Your card is yours. A hub carries it; it does not own it. Moving means republishing one file
somewhere else — which is the whole point of [the federation design](FEDERATION.md), and the
reason admission can be strict without being a trap.
