# Assets

Everything the team shared while forming the idea, kept here so nothing lives only in a chat.

## Whiteboard (Friday 2026-10-30, kickoff evening)

| File | What's on it |
| --- | --- |
| [whiteboard-1.jpg](whiteboard/whiteboard-1.jpg) | First sketch: dashboards, data extraction, "5. Future" (hotels, events, finds), and the tagline *"On GitHub you find projects to work on. On AdoBee Hive (ABH) you find people to work with!"* |
| [whiteboard-3.jpg](whiteboard/whiteboard-3.jpg) | Name ideas (Adobee Hive, ADOB66, Ado Bee 6) and the first logo and bee |
| [whiteboard-4.jpg](whiteboard/whiteboard-4.jpg) | *Where is the human?* A2A, A2H, H2A, H2H; B2B, B2C, C2C; centralised vs federated; what a personal agent needs to know |
| [whiteboard-5.jpg](whiteboard/whiteboard-5.jpg) | Workstreams S1 to S6, DuckDB, and the note on LLM access and data protection |
| [name-and-logo-sketch.png](whiteboard/name-and-logo-sketch.png) | "Adobee Hive" and the hexagon bee, the source of the logo |
| [bee-mascot-sketch.png](whiteboard/bee-mascot-sketch.png) | The striped bee, the source of the B6 mascot |

Photos are downscaled and stripped of camera metadata (location, device).

## Slides

Four groups, in the order the pitch tells them, with three alternative versions of slide 2. Every PNG here is a
still from the film below, so a slide and the film can never drift apart: change a scene in
[anim/hive_federation.py](anim/README.md) and re-render both.

**Slide 1 — punchline and project**

| File | What |
| --- | --- |
| [slide-1-punchline.png](slides/slide-1-punchline.png) | A bee leaves the Hive, five more arrive, and they merge into one agent. *Agents don't browse. They ask the Hive.* |

**Slide 2 — the vision. Three versions; the team picks one**

| File | Version | How it argues |
| --- | --- | --- |
| [slide-2-vision-a-flow.png](slides/slide-2-vision-a-flow.png) | **A · flow** | Four steps in reading order: entity, hive, search, match. The shortest to narrate |
| [slide-2-vision-b-network.png](slides/slide-2-vision-b-network.png) | **B · network** | The federation as a graph, with each hive's error written on the edge to its peer |
| [slide-2-vision-c-data.png](slides/slide-2-vision-c-data.png) | **C · data** | The artefacts themselves: the folder shape, the served JSON, and the two ratings as a table |

All three carry the same two closing lines, because they are the part a jury asks about: a hive rates
its entities only from a signed receipt, and it rates its peer hives on `published - realised`, in
tenths of a star, where lower is better.

**Slide 3 — the hotel user journey**

| File | What |
| --- | --- |
| [slide-3a-the-ask.png](slides/slide-3a-the-ask.png) | One sentence from a guest. Her agent is built from her own entity |
| [slide-3b-the-hives.png](slides/slide-3b-the-hives.png) | The agent visits interconnected hotel hives, best-calibrated first, and what comes back carries its whole `provenance.path` |
| [slide-3c-the-match.png](slides/slide-3c-the-match.png) | The hotel's listing is condensed JSON. On a match, an agent is built out of the entity |
| [slide-3d-two-agents.png](slides/slide-3d-two-agents.png) | The two agents settle dates, price and check-in between them |
| [slide-3e-your-yes.png](slides/slide-3e-your-yes.png) | She approves, and only then does it book. The receipt is signed |
| [slide-4-close.png](slides/slide-4-close.png) | Closing frame |

**Reference**

| File | What |
| --- | --- |
| [baselhack-assessment-criteria.png](slides/baselhack-assessment-criteria.png) | BaselHack jury criteria: innovation, impact, technical depth, AI code review, fair play, pitch, demo |

## Film

| File | What |
| --- | --- |
| [hive-federation.mp4](hive-federation.mp4) | About a minute: the punchline, the vision, and the hotel journey end to end. Drawn frame by frame by [anim/hive_federation.py](anim/README.md); the model it shows is [documentation/FEDERATION.md](../documentation/FEDERATION.md) and [documentation/cards/](../documentation/cards/README.md). `--variant a\|b\|c` cuts it with any of the three slide-2 versions. |

## Brand

| File | What |
| --- | --- |
| [adobee-hive-logo-1024.png](brand/adobee-hive-logo-1024.png) | The mark: a bee in an open hexagon, from the whiteboard sketch |
| [adobee-hive-wordmark.png](brand/adobee-hive-wordmark.png) | Logo and name |
| [adobee-hive-wordmark-v2-on-light.png](brand/adobee-hive-wordmark-v2-on-light.png), [-on-dark.png](brand/adobee-hive-wordmark-v2-on-dark.png) | The v2 logos cropped for the readme: `adobee-hive-wordmark-v2.png` for light grounds, `adobee-hive-wordmark-light-v2.png` for dark |
| [b6-bee-mascot.png](brand/b6-bee-mascot.png) | The B6 bee |
| [hero-clay.svg](brand/hero-clay.svg) | Lit clay honeycomb, for slides |

Logo sources (SVG) live in `code/frontend/public/brand/`; see [documentation/BRAND.md](../documentation/BRAND.md).

## Screens

Six views on a 375 px phone, offline mode, fictional data. The instance finder, the node view and the admin
panel are not captured here yet: [home](screens/phone-375-home.jpg),
[traveller agent](screens/phone-375-agent.jpg), [ask the Hive](screens/phone-375-ask.jpg),
[owner studio](screens/phone-375-owner.jpg), [card](screens/phone-375-card.jpg),
[demand map](screens/phone-375-demand.jpg).

## Pitch uploads

Added on the last morning: decks ([bees](slides/adobee-hive-bees.html), [with photos](slides/adobee-hive-with-photos-upd.html), [presentation update](<slides/Adobee Hive — Presentation Update (2).html>)), [animation](slides/adobee-hive.gif), [bee images, zipped](slides/bees.zip), [network](slides/slide-network.png), [team](slides/slide-team.png).
