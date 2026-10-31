# Federation

How Hives find each other, how far a search reaches, and how trust is scored.

One Hive answers for the businesses on it. This page is about what happens when there are many: a Hive per town,
per association, per trade body. It is the backend half of the story in [VISION.md](VISION.md) — the half a
traveller never sees, and the half that decides whether the index can be owned by anyone.

**Status: design.** What runs on `main` today is a single Hive; `radius` is not served yet. Implementation is in
progress on a branch. The pitch film in [`assets/hive-federation.mp4`](../assets/hive-federation.mp4) shows this
page at work — the hives a search visits, each one's calibration, and the `provenance.path` the answer carries —
and the stills under [`assets/slides/`](../assets/README.md) are the same beats for a deck.

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
| `3` | Cap | — |

`radius=0` is the default, so every call that exists today keeps behaving exactly as it does today. Reach is opt-in.

What each hop does:

- **Decrement and forward.** A hop subtracts one from the radius, appends its own Hive id to a `seen` list, and
  forwards only to peers not already in `seen`. The peer graph has cycles; without `seen` a search would circle
  forever. This is the one rule that must never be got wrong.
- **Carry a deadline.** The query holds a millisecond budget. Each hop subtracts what it has spent and refuses to
  forward when too little is left. A peer that misses the deadline is dropped from the answer, and the answer says
  it was dropped. A slow Hive degrades a search; it never fails one.
- **Cap the breadth.** At most a handful of peers per hop, chosen by trust. Otherwise reach two is a broadcast
  storm.
- **Deduplicate by digest.** The same card arrives by several routes. It is one card, kept at its shortest hop
  count.
- **Verify at the end, not along the way.** The searching agent checks the owner's signature itself. Nothing is
  trusted because a Hive passed it on.

Every result carries its **provenance**: the ordered chain of Hives it travelled, and the hop count. A person can
see that an answer came from two Hives away, and through which.

## Two levels of trust

A Hive is rated. So is a business. They are different questions and they are kept apart.

### The Hive

How well does it vet its members, and how honestly does it rank? Signals:

- the verification level it declares, against what peers actually observe,
- its ranking policy — a Hive that sells placement is **downgraded**, not delisted, and the policy is published so
  an agent can refuse it,
- availability and latency,
- how often cards it relayed failed a signature check or were disputed.

This score is **local and subjective**. Each Hive judges its peers for itself. There is no global number and no
consensus protocol, because a global reputation score is a thing to capture. New peers start low and earn trust
slowly.

### The business

What did it actually deliver? These signals already exist on `main` and keep their meaning:

- reviews only from a signed booking receipt — no stay, no review,
- attestations from third parties, each signed,
- nothing purchasable.

This travels **with the business**. Move to another Hive and the receipts come along, because they are signed by
the counterparties, not by the Hive. No aggregator allows that today, and it is the reason a business can leave.

### How they combine

```
rank  =  what was asked for  ×  trust in the Hives it came through  ×  distance
```

All three factors are reported separately in the score breakdown, so **open ranking** still holds: every result says
why it won, and every excluded one says why it lost. Distance discounts confidence in a long carrier chain. It is
not a claim that far-away businesses are worse.

The incentive this sets up is the point. A Hive that carries forged or disputed cards loses its peers' trust, and
every business on it then ranks lower everywhere. Vetting honestly is the cheapest strategy available to a Hive
operator.

## What changes in the API

Additive only. Nothing is renamed or removed, because the app depends on today's shape.

| Change | Where | Note |
| --- | --- | --- |
| `radius` parameter, default `0` | discover, over REST and MCP | absent or `0` is today's behaviour |
| `provenance`, `hops` on each result | discover response | new fields, old ones untouched |
| Hive trust and distance in the score breakdown | discover response | alongside the existing factors |
| A peer list, and a key registry per peer | configuration | reuses the existing multi-Hive URL setting |

Proposed modules, not yet on `main`: a federation module for the hop-limited query, and a reputation module for
the two scores. Both land with their tests and a row in [DIAGRAMS.md](DIAGRAMS.md) and
[ARCHITECTURE.md](ARCHITECTURE.md), as [CONTRIBUTING.md](../CONTRIBUTING.md) requires.

## For the pitch

Three lines, if the question comes up:

1. *The person chooses how far to search. One town, a region, or a country.*
2. *A Hive is rated for how honestly it ranks. A business is rated for what it delivered. The two are separate.*
3. *A Hive can withhold a card. It can never forge one, so the operator is replaceable.*

The jury question this answers is "who owns the Hive?" — nobody alone, and the architecture is what makes that
true rather than a promise.
