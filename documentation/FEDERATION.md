# Federation

How Hives find each other, how far a search reaches, and how trust is scored.

One Hive answers for the businesses on it. This page is about what happens when there are many: a Hive per town,
per association, per trade body. It is the backend half of the story in [VISION.md](VISION.md) — the half a
traveller never sees, and the half that decides whether the index can be owned by anyone.

**Status: built.** `radius` is served on `GET /api/hive/discover` and on the `hive_discover` MCP tool, and the
modules behind it are [`federation.py`](../code/backend/app/federation.py),
[`reputation.py`](../code/backend/app/reputation.py), [`calibration.py`](../code/backend/app/calibration.py) and
[`connections.py`](../code/backend/app/connections.py). What is not built is the second hub: a single backend has
no peers unless `HIVE_PEER_URLS` names some, so on the deployed demo every search is a radius-0 search and the
hop machinery is exercised by `tests/test_federation.py` rather than by two live hubs. What each gap is, exactly:
[LIMITS.md](LIMITS.md).

The pitch film in [`assets/hive-federation.mp4`](../assets/hive-federation.mp4) shows this page at work — the
hives a search visits, each one's calibration, and the `provenance.path` the answer carries — and the stills
under [`assets/slides/`](../assets/README.md) are the same beats for a deck.

How someone gets into a hub in the first place is [REGISTRATION.md](REGISTRATION.md), and the two are the
same argument seen from different ends: admission is strict because calibration measures what admission let in.
Worked examples of the Card, and the manifest that shows what it deliberately leaves out, are in
[cards/](cards/README.md). Those files are the reference; where this page and a file disagree, the file wins.

## Why federate at all

An index that one company owns is an index that one company ranks, prices and closes. That is the aggregator, and
it is what the challenge asks us to replace rather than rebuild. So no Hive may be necessary: a business publishes
one signed card, any Hive may carry it, and leaving a Hive means republishing one file.

This only works if a relaying Hive cannot change what it relays. It cannot: the card carries the *owner's* Ed25519
signature, and the agent at the end of the search verifies it against the owner's key, pinned in a key registry it
fetches itself. A Hive in the middle can withhold a card or delay it. It can never forge one.

## How far to look: the radius

A search carries a **radius** — how many Hive-to-Hive hops it may travel. The person chooses it; it is not a
tuning constant.

| Radius | Reaches | Roughly |
| --- | --- | --- |
| `0` | This Hive only | one town |
| `1` | This Hive and its direct peers | a region |
| `2` | And their peers | a country |
| `3` | Cap (`federation.MAX_RADIUS`) | — |

`radius=0` is the default, so every call that exists today keeps behaving exactly as it does today. Reach is opt-in.
A query above 0 also costs this hub outbound calls to its peers, so it is rate-limited (`guard.federated`).

What each hop does:

- **Decrement and forward.** A hop subtracts one from the radius, appends its own Hive id to a `seen` list, and
  forwards only to peers not already in `seen`. The peer graph has cycles; without `seen` a search would circle
  forever. This is the one rule that must never be got wrong.
- **Carry a deadline.** The query holds a millisecond budget (`budget_ms`, 2500 by default). Each hop subtracts
  what it has spent and refuses to forward when fewer than 150 ms are left. A peer that misses the deadline is dropped from the answer, and the answer says
  it was dropped. A slow Hive degrades a search; it never fails one.
- **Cap the breadth.** At most `federation.PEERS_PER_HOP` peers per hop — four — chosen by hub reputation.
  Otherwise reach two is a broadcast storm. Peers left out are named in `federation.dropped` with the reason.
- **Deduplicate by digest.** The same card arrives by several routes. It is one card, kept at its shortest hop
  count.
- **Verify at the end, not along the way.** The searching agent checks the owner's signature itself. Nothing is
  trusted because a Hive passed it on.

Every result carries its **provenance**: the ordered chain of Hives it travelled, and the hop count. A person can
see that an answer came from two Hives away, and through which.

## Two levels of trust

A Hive is rated. So is a business. They are different questions and they are kept apart, in two modules that
never read each other.

### The Hive: reputation, and calibration

Two separate measurements, because a hub can be reliable and dishonest, or honest and slow.

**Reputation** ([`reputation.py`](../code/backend/app/reputation.py)) is how this hub has found a peer to behave.
Signals:

- the verification level it declares (`signed`, `attested`), against what this hub has actually observed,
- its ranking policy — a Hive that declares paid placement is **downgraded**, not delisted, and the policy is
  published so an agent can refuse it,
- availability and latency,
- how many cards it relayed failed verification here (`reputation.record_invalid`).

A new peer starts at `NEW_PEER_TRUST`, 0.35, and earns 0.03 per clean exchange up to 0.25, so trust takes many
exchanges to build. Declaring paid placement costs 0.4 on its own. Every factor and the sentence behind it ride
along in the answer.

**Calibration** ([`calibration.py`](../code/backend/app/calibration.py)) is the sharper question: did the peer
tell the **truth** about its members? For every scored introduction the hub keeps what the peer published at the
moment of introduction and what our own person reported after the real meeting.

```
error  =  published − realised          (tenths of a star, so 25 is two and a half stars)
```

Lower is better and the sign carries meaning: positive is over-promising, negative is a hub that undersold what
it offered. The mean is recency-weighted with a 90-day half-life, and a hub with fewer than three scored
introductions is reported as **unproven** rather than guessed at — a mean over two meetings is noise wearing a
number's clothes. A hub cannot move this by anything it publishes about itself, because every input comes from
our own users.

Both scores are **local and subjective**. Each Hive judges its peers for itself. There is no global number and no
consensus protocol, because a global reputation score is a thing to capture.

### The business

What did it actually deliver? These signals already exist on `main` and keep their meaning:

- reviews only from a signed booking receipt — no stay, no review,
- attestations from third parties, each signed,
- nothing purchasable.

The design intent is that this travels **with the business**: move to another Hive and the receipts come along,
because they are signed by the counterparty rather than by the Hive. In the prototype the counterparty's signing
key is held by the hub (see [LIMITS.md](LIMITS.md)), so portable receipts are the direction, not yet the fact.

### How they combine

```
rank  =  what was asked for  ×  trust in the Hives it came through  ×  distance
```

in code, `local_relevance × hub_path_trust × hop_decay`, where `hub_path_trust` multiplies the reputation of every
hub that carried the card and `hop_decay` is 0.85 per hop. All three factors are reported separately in the score
breakdown, so **open ranking** still holds: every result says why it won, and every excluded one says why it lost.
Distance discounts confidence in a long carrier chain. It is not a claim that far-away businesses are worse.

Calibration is **not yet a factor in that product.** It is what `GET /api/hub/standing`, the neighbours table and
the hub directory are ordered by, and it is what a person choosing a hub reads; wiring it into the search rank is
listed in [LIMITS.md](LIMITS.md) rather than claimed here.

The incentive this sets up is the point. A Hive that carries forged or disputed cards loses its peers' trust, and
every business on it then ranks lower everywhere. Vetting honestly is the cheapest strategy available to a Hive
operator.

## What it added to the API

Additive only. Nothing was renamed or removed, because the app depends on today's shape.

| Addition | Where | Note |
| --- | --- | --- |
| `radius`, `budget_ms`, `seen` | `GET /api/hive/discover`; `radius` on `hive_discover` | absent or `0` is the old behaviour, byte for byte |
| `provenance`, `hops` on each result | the discover answer above radius 0 | the ordered chain of hubs, its origin, and the other routes the same card arrived by |
| `local_relevance`, `hub_path_trust`, `hop_decay` | `score_breakdown` | alongside the existing factors |
| a `federation` report | the discover answer above radius 0 | which peers were asked, which were dropped and why, which cards were rejected and by whom |
| `federation` block in `/.well-known/hive.json` | discovery document | `hub_id`, name, description, declared `verification`, `admission`, entity count, `paid_placement`, `max_radius` |
| `GET /api/hub/standing`, `GET /api/hub/directory`, `hub_standing`, `hub_directory` | REST and MCP | what this hub makes of its neighbours, and the list a person picks a hub from |
| `HIVE_PEER_URLS`, `HIVE_HUB_ID`, `HIVE_VERIFICATION`, `PEER_ASK_SECONDS` | configuration | peers are configured, never taken from a request |

Every row above has tests, a box in [DIAGRAMS.md](DIAGRAMS.md) and a row in [ARCHITECTURE.md](ARCHITECTURE.md),
as [CONTRIBUTING.md](../CONTRIBUTING.md) requires. The honest gaps are in [LIMITS.md](LIMITS.md).

## For the pitch

Three lines, if the question comes up:

1. *The person chooses how far to search. One town, a region, or a country.*
2. *A Hive is rated for how honestly it ranks. A business is rated for what it delivered. The two are separate.*
3. *A Hive can withhold a card. It can never forge one, so the operator is replaceable.*

The jury question this answers is "who owns the Hive?" — nobody alone, and the architecture is what makes that
true rather than a promise.
