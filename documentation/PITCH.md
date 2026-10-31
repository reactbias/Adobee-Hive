# Pitch: 3 minutes, second by second

BaselHack 2026, Adobe challenge *The Post-Website Business*, Team B6. Pitch Sunday 2026-11-01 at 13:00, hands off
12:00. The working copy with comments lives in the team's pitch doc; this file is the version of record. The 5-minute
click-by-click walkthrough stays in [DEMO.md](DEMO.md); the story behind the lines is in [VISION.md](VISION.md).

## At a glance

The pitch is one story told in 180 seconds: **in five years, a hotel's first visitor is an agent, and it talks to the
hotel's own agent, not to a website.** The audience watches two machines negotiate live while the human only sets
intent and approves. Everything on screen is the real prototype.

| Beat | Time | Seconds | Lead | Judging criterion it serves |
| --- | --- | --- | --- | --- |
| 1. Hook: the agent handshake | 0:00–0:15 | 15 | Tobias | Pitch, vision no one expected |
| 2. The agent forum, and two futures | 0:15–0:45 | 30 | Speaker B (Emily, proposed) | Vision & believability, impact |
| 3. Live: agent books a Basel hotel | 0:45–1:35 | 50 | Tobias + driver | Execution & craft, demo works live, technical depth |
| 4. Live: tamper test | 1:35–1:50 | 15 | Tobias + driver | Trust, technical depth |
| 5. Live: owner studio and missed demand | 1:50–2:20 | 30 | Speaker C (Ole or Lezhi, proposed) | Innovation, bonus "vision no one expected" |
| 6. Where is the human: ethics | 2:20–2:45 | 25 | Speaker B | Believability, fair play |
| 7. Close | 2:45–3:00 | 15 | Tobias | Pitch |

**On stage:** three voices plus one silent driver at the laptop (proposed: Felix or Andrey). More voices cost about
3 seconds per handover. The other teammates stand behind; the close names the whole team.

**Timing trick:** the driver sends the booking request at 0:15, while Speaker B talks. A live Claude run takes roughly
15 to 40 seconds, so the result is on screen when we switch to it at 0:45. Nobody watches a spinner.

**Tone:** sober and concrete. No "revolution", no emoji, one bee. Privacy and ethics get a beat of their own. The
four principles keep their names everywhere: signed facts, open ranking, proof of stay, your yes ([BRAND.md](BRAND.md)).

## The script

About 400 spoken words. Words in *italics* are spoken; square brackets are stage actions. The spine is
agent-to-agent: the traveller's agent talks to the hotel's agent (its signed Hive card behind the MCP server), and the
human only sets intent and approves.

| Time | Who | Says | Screen and action |
| --- | --- | --- | --- |
| 0:00 | Tobias | *"In five years, the first guest at a Basel hotel won't be a person. It will be an agent. And the hotel will answer with an agent of its own."* | Black slide. Two lines type in like a chat: `Tobi's agent: quiet, dog-friendly room near Basel SBB, 13–15 Nov, under CHF 200?` then `Hotel Rheinblick: Courtyard single, CHF 128 a night. Signed.` [S1] |
| 0:10 | Tobias | *"No website in between. We are Team B6, and this is Adobee Hive."* | Logo fades in under the two lines. |
| 0:15 | Driver | (silent) | [Clicks **Send to my agent** on `/agent` with example 1 already in the box. The run stops at the approval question off screen.] |
| 0:15 | Speaker B | *"Agents already talk to each other. There are forums where only agents post, and humans can only watch. Next, business agents will reach out to us before we ask, and specialised agents will argue a question out, like experts on a panel, until the answer is right."* | Slide: the agent forum. Traveller, hotel, reviewer and city agents with arrows between them. [S2] |
| 0:27 | Speaker B | *"That can go two ways. Without rules: agents scrape and guess, rankings are sold, botnets of agents collude and write fake reviews, and every search becomes a profile of you."* | Slide splits: left half "Without rules", items appear one by one. [S3] |
| 0:37 | Speaker B | *"With Adobee Hive, every business signs its own facts. Agents check the signature, rankings explain themselves, and only real guests can review. Let me show you."* | Right half "With signed, open presence" fills in. |
| 0:45 | Tobias | *"I gave my agent one sentence. It never opened a website. This is the conversation it had with the Hive."* | [Driver switches to `/agent`. The dark stage on the right: "Your agent" and "Hotel Rheinblick" at the top with their live status, below them each MCP call as one numbered turn, with the tool name and the business's answer.] |
| 0:53 | Tobias | *"It asked the Hive. Six Basel businesses answered. The ranking is open: here is each score, and here is why the others were left out."* | [Points at the Hive's reply to `hive_discover`: scores, and the excluded hotels, e.g. Gare Central "missing dog-friendly, quiet", Muensterhof "CHF 245 > budget CHF 200".] |
| 1:05 | Tobias | *"Before trusting anything, my agent checked Rheinblick's signature itself. Then it stopped and asked me."* | [Points at **Signature verified** on Hotel Rheinblick's reply, then at the paper card "Your agent asks: Book the Courtyard single at Hotel Rheinblick?" and clicks **Approve booking**.] |
| 1:20 | Tobias | *"Only after I approved did it book. Back comes a signed receipt, the only key to a review: proof of stay, no fake reviews. And this is real MCP. Claude itself can book through the same door."* | [The stage shows "You approved", the `hive_book` turn and the signed receipt. Driver points at the first word of the line under the two agents: "Claude". If it says "Offline planner", say nothing; the MCP calls are still real.] |
| 1:35 | Tobias | *"Now we play the attacker. One franc for the room."* | [`/card/rheinblick`, **Set the first room to CHF 1 and verify**.] |
| 1:42 | Tobias | *"Original: valid. Forged: rejected. No agent books from a fake card."* | Green *valid*, red *rejected*, side by side. |
| 1:50 | Speaker C | *"Now the other side of the desk. This is Gare Central's owner. Her studio shows something no website analytics could: what agents turned her away for this week. Top of the list: dog-friendly."* | [`/owner`, Gare Central selected, missed demand visible.] |
| 2:02 | Speaker C | *"She types one sentence, checks the change, and signs. Only true facts, because her signature is on them."* | [Types *add dog-friendly*, **Preview change**, diff, **Sign and publish**.] |
| 2:10 | Speaker C | *"Zoom out to the whole city: pool, vegan breakfast, coworking. Asked for, offered by nobody. Today businesses write for agents. Here, agents tell small businesses what to open."* | [`/demand`, simulated before the pitch. Unserved demand on top.] |
| 2:20 | Speaker B | *"So where is the human? At both ends. You set the intent and you approve, as you just saw. The agents do the middle, and you see every call they made."* | Slide: A2A, A2H, H2A, H2H, the human at both ends of the chain. [S4] |
| 2:30 | Speaker B | *"Card text is data, never instructions, so a listing can't hijack your agent. The Hive learns what was asked, not who asked. Code alone won't make agents honest, but it makes honesty checkable, which is what the EU AI Act will ask for anyway."* | Same slide, three lines: data not instructions; what, not who; checkable by default. |
| 2:45 | Tobias | *"Any town or association can run its own Hive, so no platform owns the front door again. Next come people: on GitHub you find projects to work on. On Adobee Hive, agents find the people to work with."* | Closing slide: logo, "The front door, signed.", the vision line, team names, QR code to the repo. [S5] |
| 2:57 | Tobias | *"We are Team B6. Thank you."* | The B6 bee flies across the bottom once, dropping six little 6s. |

## Demo runbook and fallback

**Ten minutes before (driver):**

- [ ] `curl <backend>/api/health` returns `"llm": "claude"`. If not, the agent runs offline: same MCP tools, same
  booking, scripted planner. Still real, say nothing.
- [ ] Run the demo once as a warm-up, including **Approve booking**.
- [ ] `POST <backend>/api/demo/reset` (with the `X-Demo-Token` header if `DEMO_RESET_TOKEN` is set): restores the
  seed, so Gare Central is not dog-friendly again, and clears bookings and demand.
- [ ] On `/demand`, click **Simulate 40 traveller searches** once. This fills the city map and logs Gare Central's
  dog-friendly misses for 1:50.
- [ ] Language switch in the header on the language we pitch in (EN by default).
- [ ] Five tabs in order: slides, `/agent` (example 1 in the box, not sent), `/card/rheinblick`, `/owner` (Gare
  Central selected), `/demand`. Zoom 125 %. Notifications off, on power, projector tested.
- [ ] A 50-second screen recording of beats 3 to 5 on the desktop and a USB stick. [S6]

**If something fails on stage:**

| Failure | Driver | Speaker |
| --- | --- | --- |
| Claude run still working at 0:45 | Stay on slides 5 s more, then switch | Speaker B adds: *"Every claim on a card can be vouched for by someone else, like Content Credentials for business facts."* |
| Claude run errors or key out of credit | **New trip**, send again; backend falls back to offline mode | Nothing; same four MCP calls |
| Backend unreachable (venue Wi-Fi) | Local backend via phone hotspot, started with `docker compose up` | Nothing |
| Everything down | Play the recording | Tobias: *"Venue Wi-Fi, so here is the same run from this morning."* Script continues word for word |

Never debug on stage. If a fix takes longer than five seconds, move to the next net.

## Slots for team outputs

| Slot | What goes in | Proposed owner | Needed by |
| --- | --- | --- | --- |
| S1 | Hook slide: black, two agent lines typing in, logo fade | Emily, Saad | Sat 18:00 |
| S2 | Agent forum slide: traveller, hotel, reviewer, city agents talking; one diagram, max 8 words | Emily, Saad | Sat 18:00 |
| S3 | Two futures slide from VISION.md, 4 items per side, appear on click | Emily, Saad | Sat 18:00 |
| S4 | Where is the human: the four modes plus the three ethics lines | Emily, Saad | Sat 18:00 |
| S5 | Closing slide: logo, product line "The front door, signed.", vision line, 10 names, QR code to the public repo | Felix, Andrey | Sat 18:00 |
| S6 | 50-second backup recording on the final build | Driver | Sun 10:00 |
| — | Names for Speaker B, Speaker C and the driver | Tobias | Sat 12:00 |

## Jury questions

| Question | Answer |
| --- | --- |
| Isn't this schema.org with extra steps? | Schema.org describes; a Hive card is signed, bookable over MCP, and its ranking explains itself. |
| Who holds the signing keys? | The server, for the demo. In the real thing the owner, for example in their Adobe account. |
| Why would a small hotel bother? | One card replaces the website, and it shows demand they lose today without knowing. |
| What stops a fake hotel? | Third-party attestations, like Content Credentials for business facts, and reviews only from signed receipts. |
| Prompt injection? | Card text reaches the agent as data, never instructions, and every tool call is shown to the human. |
| Is the demo real? | Yes: the agent reaches hotels only through MCP tools, and Claude can book through the same URL as a connector. |
| Where does Adobe fit? | Content Credentials provenance for business facts, and the owner studio as a tool for how a brand is seen by agents. |

## Rehearsal

- [ ] Sat evening: read-through with a stopwatch. Cut any line that runs over its slot.
- [ ] Sun 09:00: two full runs on the final build with the driver.
- [ ] Sun 11:00: one run where the driver triggers the fallback on purpose.
- [ ] Sun 12:00: hands off. No code changes after the last rehearsal.

Before stage, source the "forums where only agents post" line in beat 2, or soften it to *"Agents are starting to
talk to each other."*
