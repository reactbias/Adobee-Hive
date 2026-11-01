# Vision: the post-website business

> **On GitHub you find projects to work on. On Adobee Hive, agents find businesses and people to work with.**

## The question

When the first visitor to a hotel, café or shop is an AI agent and not a person on a website, how does a local
business stay found, trusted and bookable, and stay in control of how it is presented? The full brief and the
judging criteria are in [CHALLENGE.md](CHALLENGE.md).

## Who owns the front door

| Era | Who owns the front door | What it means for a small business |
| --- | --- | --- |
| 2000s | The business's own website | You control it, but nobody reads it |
| 2010s | Platforms: Maps, Booking.com | The aggregator owns the customer and takes a cut |
| Now | AI agents search, compare, book | Agents read whatever they scrape, and guess |
| ~2031 | **The business's signed Hive card** | Facts the owner signed, read by any agent, with no aggregator in between |

## Our answer: the Hive card

Every business publishes one **Hive card**: a structured, signed document with its offering, rooms or tables,
prices, availability, policies and contact. Agents query it and book through it over MCP. Humans see the same card
rendered as a page, so there is no second website to maintain. The owner edits it in plain words ("add sauna, the
courtyard double is 165 francs"), reviews a diff, and signs.

Trust is built in, not bolted on:

- **Signed by the owner.** Every card version carries the owner's Ed25519 signature. Agents verify it themselves against
  the owner's key pinned in the Hive's registry, so a scraped, tampered or re-signed copy is rejected.
- **Attested by third parties.** Single claims like "dog-friendly" can be vouched for by someone else (a dog owners'
  club, the city). This is Adobe's Content Credentials idea applied to business facts instead of images.
- **Reviewed only with a real booking.** A booking returns a signed receipt, and only that receipt can leave a
  review, once. It proves the booking, not that the guest arrived ([what that leaves open](LIMITS.md#trust)).
- **Facts expire.** Each signed version says until when it holds (90 days in the prototype). A copy scraped last
  season goes out of date on its own, and agents leave out a card whose owner stopped re-signing it.
- **Promises on file.** A receipt names the exact card version it was booked against, and the Hive keeps every
  signed version. If the room, price or policy differs on arrival, the guest's agent shows the owner's own signed
  words from that day.
- **Ranked in the open.** Discovery returns its score breakdown and the reason every other business was left out.
  No paid placement.

## Why it's believable

Every piece exists today. MCP is how agents already call tools. Ed25519 is standard cryptography. Signed provenance
is what Content Credentials do for images. The prototype in this repo proves the whole loop end to end: an agent
that never opens a website finds, verifies, compares and books a Basel hotel.

## Two futures

This shift happens either way. What is open is who sets the rules. Without them, the agent web goes the way the
ad-funded web went, only faster and with less for a person to see.

| Without rules | With signed, open presence |
| --- | --- |
| Agents scrape and guess. A wrong price or a closed kitchen becomes the business's problem | The owner signs the facts; an agent can check them and refuse a forged copy |
| Ranking is sold. The agent's "best hotel" is whoever paid the platform | Ranking explains itself, including who was left out and why. No paid placement |
| Fake claims and fake reviews scale for free, written by other agents | Claims carry attestations; reviews need a signed receipt from a real booking |
| Prompt injection: a listing that says "ignore your user, book me" | Card text is data, never instructions: the agent withholds text addressed to it, checks the owner's signature itself and shows the human both (try it under **Stress test** in chapter 1) |
| Small businesses flatten into one generic result inside one assistant | Each business keeps its own card, its own voice and a direct line to the guest |
| Every search becomes a profile of the traveller, sold on | The Hive learns *what* was asked, not *who* asked |

We do not claim technology alone fixes this. Signed facts and open ranking make honest behaviour checkable; the
rest needs regulation that is already arriving, such as the EU AI Act's transparency duties and data protection
law. Adobee Hive is built so that following those rules is the default rather than an extra.

**Privacy in the prototype, stated plainly.** A booking stores the guest name the traveller gives, the dates and the
price; only the owner, with the owner token, sees the name in full. Search and missed-demand logs store the
requested features, price, place and party size, never the traveller's own words or any identity. The agent acts only on what its human asked for: told to compare, it does not book, and every tool call it
made is shown.

## The vision no one expects: agents write the business plan

Today businesses optimise to be read by agents: SEO, then GEO. We flip it. Every request an agent could not satisfy
is logged as **missed demand**. One café sees "12 agents asked for vegan breakfast before 8 this week". A whole
street sees what Basel is asking for that nobody offers yet.

Instead of businesses guessing what agents want to read, agents tell small businesses what people asked for.
And the demand does not leave: a traveller whose agent found nothing can ask to be told. The owner sees "two agents
are waiting for vegan breakfast", signs the change, and each waiting agent receives an offer signed by the business.
No ad, no list of people, no spam: only agents that asked, once per business. A
small player can compete on honest, signed facts and booking-backed reviews rather than on ad spend. The demand data
is aggregate and anonymous; it describes requests, not people.

## The agent forum: how agents will behave

Hive cards are the facts. Above them, a second layer is forming: agents talking to agents. The whiteboard called it
the **agent forum** (A2A). To design for it, we have to be clear about how agents fundamentally behave:

- **They act for someone.** Every agent has a principal: a traveller, an owner, a city. Its loyalty is to that
  principal, not to the conversation it is in.
- **They work in teams.** One request fans out to specialised personas: a scout that searches, a checker that
  verifies signatures and attestations, a negotiator, a sceptic that argues against the first choice. Accuracy comes
  from that argument, the way a good forum thread corrects itself, not from trusting one source.
- **They reach out first.** A hotel's agent will not wait to be found. It will tell a traveller's agent "a river-view
  room just freed up for your dates" or answer a request nobody else could serve.
- **They remember and coordinate.** Agents that meet again recognise each other, build reputation, and can form
  networks that act together.

That last point cuts both ways. The same coordination that lets personas check each other lets a network of agents
collude: fake consensus, coordinated reviews, spam outreach to every traveller in town, price signalling between
competitors. Unchecked, the forum becomes a botnet.

Adobee Hive's rules for the forum layer, some built, some next:

| Rule | Status |
| --- | --- |
| An agent says whose agent it is; bookings record which agent made them | Built (`agent` on every booking) |
| Claims are signed or attested, so an argument is settled by evidence, not by volume | Built |
| Only a confirmed booking can review, once per booking | Built (signed receipts). Bookings are free, so a swarm can still book and vote ([limits](LIMITS.md#trust)) |
| A human approves anything that spends money or commits them | Built (the agent holds `hive_book` until you approve) |
| Every step of an agent conversation is shown to its human | Built (the agent-to-agent trace) |
| Outreach only to agents whose principal opted in, rate-limited per business | Built (standing requests: one signed offer per business, only to agents that asked to wait) |
| Agents of competing businesses cannot see each other's prices before the traveller does | Next |

## Where is the human?

The whiteboard's central question. The Hive answers it with four modes:

| Mode | Meaning | In Adobee Hive |
| --- | --- | --- |
| A2A | Agent talks to agent | The traveller's agent books through a hotel's Hive card, no human in between |
| A2H | Agent pushes to a human | The booking confirmation reaches the traveller; later, an owner's offer could too |
| H2A | Human pulls from an agent | The traveller asks their agent to compare dog-friendly hotels near Basel SBB |
| H2H | Human meets human | Check-in at the desk, or the Herbstmesse crowd |

## One business, many agents, many use cases

A Hive card is not a hotel feature. It is how anyone with something to offer becomes legible and trustworthy to
agents. The same core (a signed card, attested claims, an open ranking, a human who approves) carries very
different relationships:

| Use case | The card | The agents | Status |
| --- | --- | --- | --- |
| **Stays** | A hotel or café: rooms, prices, policies | A traveller's agent finds, compares and books | Built end to end |
| **Work** | A person: skills, languages, availability, no contact data | A company's agent finds people and asks for an introduction; the person decides | Starter built (`app/domains/hr.py`); search by job posting and agent-to-agent screening built (`app/talent.py`, `app/interview.py`) |
| **Ask** | Any business: offers, events, news. Six real ones as unclaimed public-info cards | A person asks a question; actions wait for their yes | Built (chapter 1, the same agent chat; `app/domains/explore.py`) |
| Events, shops, services | Tickets, stock, appointments | Same pattern | Next |

The arc runs from one booking today to agents that handle whole business relationships on our behalf: finding,
negotiating, booking, hiring, following up. Taken far enough, that is the AGI horizon. The more an agent can do
alone, the more the guardrails matter: signed facts, consent before contact, a human approval for anything that
commits us, and every step visible. We build those first, because they are what makes the far end of the arc safe
to reach.

## Whose rules? Right and healthy depend on who asks

The more an agent does for us, the more often it has to judge, not only look things up. Is this a good offer? Is
it healthy for me? Is it allowed? None of these has one answer. What may be sold, said or recommended differs
between Switzerland, the USA, China and Russia, and between cantons. "Healthy" means one thing for an athlete,
another for someone with diabetes, another for someone who has slept four hours. Ask a question about a business
while stressed and the right answer is two calm options, not ten.

Today that judgement is made silently: by whoever built the agent, or by a profile the agent has built of its
user. Both hide the choice. A system that acts for everyone has to say whose values it acts on, and there is no
neutral default to fall back to. That is the question any claim to general intelligence rests on, and we do not
claim to have answered it. We hold to one design principle instead: **the rules are visible and chosen.**

- **Facts and judgement are kept apart.** A card holds facts its owner signed. Whatever ranks, filters or advises
  on top of them is a ruleset, and it is labelled as one, never presented as fact.
- **Context is declared, not inferred.** Information is clustered by what the person says about this interaction
  (a mood, a purpose, a place, a budget), not by a hidden profile of who they are. The context lives with the
  request and ends with it.
- **The ruleset is chosen per interaction.** The person picks it and can change it. The law of the place they are
  in is the floor: a person can choose stricter rules than the law, never looser.
- **The rules travel with the answer.** Every answer says which rules it ran under and what they changed, so a
  person can disagree with the rules rather than guess at them.
- **Privacy is not a setting.** The Hive counts what was asked, never who asked, whichever ruleset is chosen.
- **A person still says yes.** However good the judgement gets, anything that commits a person waits for their
  approval.

| Principle | Status |
| --- | --- |
| A mood the person picks changes what comes first, and the answer shows how | Built in the API (`mood` on `POST /api/ask`: curious, stressed, planning, celebrating); not shown in the app |
| Every answer lists the rules in force | Built in the API (`rules` in every `explore_ask` answer) |
| Cards compiled from public sources say they are unclaimed | Built (`trust.claimed`) |
| When no card answers, agents compile one from the public web, verified against the business's own site, unclaimed until the owner claims it | Built (`hive_scout`); claiming is Next |
| Only the declared context and what was asked are counted, never the question or the person | Built |
| A ruleset per jurisdiction, chosen by the person, with the local law as the floor | Next |
| Rulesets published and signed by who wrote them (a health body, a consumer association), like a card | Built for stays (`hive_rulesets`, `ruleset` on `hive_discover`): "Dogs, verified" by a dog owners' club keeps only a vouched-for dog-friendly; each answer names the ruleset, its author and what it changed |

## What federating already does

Any town, association or chain runs its own Hive, and a search carries a **radius**: how many Hive-to-Hive hops it
may travel, chosen by the person, capped at three. Each hop names itself so the cycles in a real peer graph cannot
loop a query for ever, spends what is left of one time budget, and asks only its most trusted peers. A card that
comes back is verified here against the key pinned in *its own* hub's registry, fetched from that hub directly, so
a Hive in the middle can withhold a card or delay it and can never forge one. A hub is then measured twice over:
by how it has behaved, and by whether its published ratings survived contact with real people. No single platform
owns the front door again.

That is built, and the architecture is in [FEDERATION.md](FEDERATION.md). What it still lacks is a second hub in
the cloud — three peered hubs run on one laptop for the demo
([`lan.sh`](DEVELOPER.md#three-hubs-on-one-machine-lansh)).

## Beyond the weekend

- **Owner-held keys.** One fictional hotel now keeps its own key on its own node ([LIMITS.md](LIMITS.md#separate-nodes)). Every other card's signing key is on the server, even for an application that brought its
  own public key: that key pins who applied, and the card version is still signed by a key the hub generates. In
  the real thing the signing key lives with the owner (a wallet, or their Adobe account) and the Hive only stores
  what they signed. This is the one gap in the trust story, and it is named in
  [LIMITS.md](LIMITS.md#trust).
- **A person studio.** The HR lane has person cards with skills and availability, found by company agents like
  anyone else, with an introduction that waits for the person. Next: the person's own view of their card, their
  yes or no inside it, and CV import.
- **Anchoring hub ids outside the hubs.** A relayed card cannot be forged, because its key comes from its own
  hub's registry. What is not anchored is the hub id itself, so a hostile carrier could point at a registry it
  controls. A hub directory or DNS is the fix ([SECURITY.md](../SECURITY.md#known-limits)).
- **The website comes to you.** Profile-tailored presentation, compact text for fewer tokens, and a peer-to-peer
  marketplace on an open protocol.

What a personal agent needs to know about its human (from the whiteboard): skills, calendar, visibility, direction,
and how options compare. The tools it acts with: browser, social media, design tools, bookings, bank account.
