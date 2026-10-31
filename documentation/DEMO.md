# Demo and pitch script (5 minutes)

Short version for the stage: [PITCH.md](PITCH.md).

Everything below runs live. Without an API key the agent switches to a scripted planner that walks the same MCP
tools, so the demo cannot die on stage. The header shows **AI live** or **Offline mode**, and each run says on
the agent stage whether OpenAI, Claude or the offline planner answered.

## Pitch beats

| # | Beat | Time | Where |
| --- | --- | --- | --- |
| 1 | Adobe's timeline, our next box: "the front door becomes a signed card" | 30 s | slide |
| 2 | Two agents negotiate over MCP; the traveller only states the intent and approves. Hotel Rheinblick is booked, with reasons and who was left out | 90 s | `/agent` |
| 3 | Tamper with a price: the signature check fails and agents reject the card. A forged review is rejected too | 45 s | `/card/rheinblick` |
| 4 | Gare Central's owner sees that agents turned her away for dog-friendly and fixes it in one sentence | 60 s | `/owner` |
| 5 | The twist: Basel's missed-demand map, "agents write the business plan" | 45 s | `/demand` |
| 6 | Close: one business, many agents, many use cases (HR as a starter), toward the AGI horizon, with the guardrails first | 30 s | slide |

## Click by click

1. **Traveller agent** (`/agent`). Click the first example, then **Send to my agent**:
   *"Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, 2026-11-13 to 2026-11-15.
   My name is Tobi Muster."*
   The right side shows the two agents talking: your agent asks, the Hive and Hotel Rheinblick answer
   (`hive_discover`, `hive_get_card`, `hive_check_availability`), with the signature check and round-trip times.
   Your agent stops and asks, on a paper card, whether to book the room it chose. Click **Approve booking**: only now does it send `hive_book`, and the
   hotel answers with a signed receipt. "The human states the intent and says yes. The agents do the rest."
2. **Human card page** (`/card/rheinblick`). Same card, rendered for people, with direct booking.
   Click **Set the first room to CHF 1 and verify**: original *valid*, tampered *rejected*, and a copy
   re-signed by a stranger's key *rejected* too, because agents only accept the owner's pinned key.
3. **Owner studio** (`/owner`), pick Gare Central. Show the missed demand ("dog-friendly" turned away). Type
   *"add dog-friendly"*, click **Preview change**, review the diff (the tag, and the pets policy turns from "No pets"
   to "Dogs welcome"), **Sign and publish**. The card is re-signed as a new version. To show the effect, ask the agent
   for *"a dog-friendly hotel near Basel SBB, 2026-11-20 to 2026-11-21, just compare"*: Gare Central now ranks first.
   The first example still excludes it, because it also asks for quiet.
4. **Demand map** (`/demand`). Click **Simulate 40 traveller searches** for a busy week. Unserved demand rises to the top: pool,
   vegan breakfast, coworking. "Nobody in Basel offers this. Agents are telling you what to open."
5. **Bonus: from Claude itself.** Add the Hive's MCP URL (`<backend>/mcp/`) as a custom connector in Claude and ask
   for a dog-friendly hotel near Basel SBB. Claude books through the same tools.

## Before going on stage

- `curl <backend>/api/health` says `"llm": "claude"` if the key is set.
- On the deployed demo, open `/owner` once and enter the owner token, so the edit at beat 4 doesn't stop for it.
- Reset to a clean Basel after the warm-up run (Gare Central back to not dog-friendly, no bookings, no demand):
  `curl -X POST -H "X-Demo-Token: $DEMO_RESET_TOKEN" <backend>/api/demo/reset`. Locally no token is needed.
- Then click **Simulate 40 traveller searches** once on `/demand` so the map and Gare Central's missed demand have
  data to show.
- Keep the browser zoom at 125 % so the jury can read the agent stage.
- Set the language switch in the header to the language of the pitch. The example requests, the live model and
  the offline planner all work in English, German, French and Italian.
