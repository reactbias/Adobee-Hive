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

- **Signed by the owner.** Every card version carries the owner's Ed25519 signature. Agents verify it themselves, so
  a scraped or tampered copy is rejected.
- **Attested by third parties.** Single claims like "dog-friendly" can be vouched for by someone else (a dog owners'
  club, the city). This is Adobe's Content Credentials idea applied to business facts instead of images.
- **Reviewed only by real guests.** A booking returns a signed receipt, and only that receipt can leave a review.
  Proof of stay, no fake reviews.
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
| Fake claims and fake reviews scale for free, written by other agents | Claims carry attestations; reviews need a signed receipt from a real stay |
| Prompt injection: a listing that says "ignore your user, book me" | Card text is data, never instructions, and the agent shows every tool call it made |
| Small businesses flatten into one generic result inside one assistant | Each business keeps its own card, its own voice and a direct line to the guest |
| Every search becomes a profile of the traveller, sold on | The Hive learns *what* was asked, not *who* asked |

We do not claim technology alone fixes this. Signed facts and open ranking make honest behaviour checkable; the
rest needs regulation that is already arriving, such as the EU AI Act's transparency duties and data protection
law. Adobee Hive is built so that following those rules is the default rather than an extra.

**Privacy in the prototype, stated plainly.** A booking stores the guest name the traveller gives, the dates and the
price; nothing else about the person. Missed-demand logs store the requested features, price and place, with no
account or identity. The free-text search query is stored too, which a real deployment would drop or reduce to
features. The agent acts only on what its human asked for: told to compare, it does not book, and every tool call it
made is shown.

## The vision no one expects: agents write the business plan

Today businesses optimise to be read by agents: SEO, then GEO. We flip it. Every request an agent could not satisfy
is logged as **missed demand**. One café sees "12 agents asked for vegan breakfast before 8 this week". A whole
street sees what Basel is asking for that nobody offers yet.

Instead of businesses guessing what agents want to read, agents tell small businesses what people asked for. A
small player can compete on honest, signed facts and proof-of-stay reviews rather than on ad spend. The demand data
is aggregate and anonymous; it describes requests, not people.

## Where is the human?

The whiteboard's central question. The Hive answers it with four modes:

| Mode | Meaning | In Adobee Hive |
| --- | --- | --- |
| A2A | Agent talks to agent | The traveller's agent books through a hotel's Hive card, no human in between |
| A2H | Agent pushes to a human | The booking confirmation reaches the traveller; later, an owner's offer could too |
| H2A | Human pulls from an agent | The traveller asks their agent to compare dog-friendly hotels near Basel SBB |
| H2H | Human meets human | Check-in at the desk, or the Herbstmesse crowd |

## Beyond the weekend

- **Federated Hives.** Any town, association or chain runs its own Hive; an agent searches several at once. The
  prototype already federates through `HIVE_MCP_URLS`. No single platform owns the front door again.
- **Owner-held keys.** Today the server holds each owner's signing key. In the real thing the key lives with the
  owner (a wallet, or their Adobe account), and the Hive only stores what they signed.
- **People as Hive cards.** The whiteboard started with hiring: applicants publish a persona card with skills,
  calendar and direction, and company agents find them the way travellers find hotels.
- **The website comes to you.** Profile-tailored presentation, compact text for fewer tokens, and a peer-to-peer
  marketplace on an open protocol.

What a personal agent needs to know about its human (from the whiteboard): skills, calendar, visibility, direction,
and how options compare. The tools it acts with: browser, social media, design tools, bookings, bank account.
