# The challenge

**The Post-Website Business**, by Adobe at BaselHack 2026 (prize CHF 1,500).
Source: [baselhack.ch/challenges/the-post-website-business](https://www.baselhack.ch/challenges/the-post-website-business).
Contact: Damian Zehnder, Adobe (contact details in the BaselHack brief).

## Problem statement

> How might a local business (hotel, restaurant, café, shop, service provider) establish and control its presence
> in a web where the primary "visitor" is an AI agent rather than a human browsing pages?

The brief offers directions, not a checklist: the agent-facing storefront, discovery and trust, the transaction,
the owner's experience, representation and fairness, and the human fallback. Inventing your own angle is
encouraged and rewarded.

## Context from the brief

- ~2000s: every business needed its own website.
- ~2010s to today: Google Maps, TripAdvisor, Booking.com, OpenTable and Instagram own the interface.
- Emerging: a traveller asks an assistant *"book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with
  late check-in"* and never visits a website. The agent reads, compares, decides and books.

Adobe wants a credible, imaginative picture of the future plus a prototype that makes it tangible, "not yet
another CMS". It matters for millions of small businesses that can't afford to lose the discovery game a second time.

## Must-haves (weighted together)

1. **A vision** of local-business presence in about 5 to 10 years: the concept, the actors, why it's plausible.
2. **A prototype** that runs: for example an agent discovering and booking a fictional Basel hotel. The core
   mechanism must genuinely work, not be faked end to end.

Also required: an OSI licence (MIT) in the public repo. We keep ownership; Adobe may showcase the work with credit.

## How we are judged

| Adobe | BaselHack jury ([slide](../assets/slides/baselhack-assessment-criteria.png)) |
| --- | --- |
| Vision and believability | Innovation: a value proposition that stands out |
| Innovation | Impact: social, economic, technical relevance |
| Execution and craft | Technical depth: how well it's built |
| Bonus: "best vision no one expected" | AI code review: code quality and commit history |
| | Fair play, within the hackathon rules |
| | Pitch: clear story, confident delivery |
| | Demo: does it work, live? |

## Timeline

Hands off Sunday 2026-11-01 at 12:00, pitches at 13:00.

## How this repo answers it

| The brief asks about | Our answer | Where |
| --- | --- | --- |
| Agent-facing storefront | Signed Hive card, served over MCP | `hive.py`, `mcp_server.py` |
| Discovery and trust | Owner signatures, attestations, open ranking with reasons | `hive.py`, tamper test in chapter 2 |
| The transaction | Agent books end to end, signed receipt, cancel | `agent.py`, chapter 1 |
| The owner's experience | Edit in plain words, review diff, sign | `owner.py`, owner studio in chapter 2 |
| Representation and fairness | No paid placement; missed demand shows small players what to offer | demand map in chapter 2 |
| The human fallback | The same signed card, readable by people in the owner studio; direct booking stays in the REST API | `POST /api/hive/cards/{card_id}/book` |
