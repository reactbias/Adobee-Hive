# Demo and pitch script (5 minutes)

Short version for the stage: [PITCH.md](PITCH.md).

Everything below runs live. Without an API key the agent switches to a scripted planner that walks the same MCP
tools, so the demo cannot die on stage. The nav bar shows **Claude live** or **offline mode**.

## Pitch beats

| # | Beat | Time | Where |
| --- | --- | --- | --- |
| 1 | Adobe's timeline, our next box: "the front door becomes a signed card" | 30 s | slide |
| 2 | Two agents negotiate over MCP; the traveller only states the intent and approves. Hotel Rheinblick is booked, with reasons and who was left out | 90 s | `/agent` |
| 3 | Tamper with a price: the signature check fails and agents reject the card. A forged review is rejected too | 45 s | `/card/rheinblick` |
| 4 | Gare Central's owner sees missed dog-friendly demand, fixes it in one sentence, and the next search finds them | 60 s | `/owner` |
| 5 | The twist: Basel's missed-demand map, "agents write the business plan" | 45 s | `/demand` |
| 6 | Close: federated Hives, and people as Hive cards (the hiring idea) | 30 s | slide |

## Click by click

1. **Traveller agent** (`/agent`). Click the first example, then **Send to my agent**:
   *"Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, 2026-11-13 to 2026-11-15.
   My name is Tobi Muster."*
   The right side shows the two agents talking: your agent asks, the Hive and Hotel Rheinblick answer
   (`hive_discover`, `hive_get_card`, `hive_check_availability`), with the signature check and round-trip times.
   Your agent stops and asks **book this?** Click **Approve booking**: only now does it send `hive_book`, and the
   hotel answers with a signed receipt. "The human states the intent and says yes. The agents do the rest."
2. **Human card page** (`/card/rheinblick`). Same card, rendered for people, with direct booking.
   Click **Set the first room to CHF 1 and verify**: original *valid*, tampered *rejected*.
3. **Owner studio** (`/owner`), pick Gare Central. Show the missed demand ("dog-friendly" turned away). Type
   *"add dog-friendly"*, click **Preview change**, review the diff, **Sign and publish**. Go back to the agent and search again: Gare Central
   now shows up.
4. **Demand map** (`/demand`). Click **Simulate 40 traveller searches** for a busy week. Unserved demand rises to the top: pool,
   vegan breakfast, coworking. "Nobody in Basel offers this. Agents are telling you what to open."
5. **Bonus: from Claude itself.** Add the Hive's MCP URL (`<backend>/mcp/`) as a custom connector in Claude and ask
   for a dog-friendly hotel near Basel SBB. Claude books through the same tools.

## Before going on stage

- `curl <backend>/api/health` says `"llm": "claude"` if the key is set.
- Reset to a clean Basel after the warm-up run (Gare Central back to not dog-friendly, no bookings, no demand):
  `curl -X POST -H "X-Demo-Token: $DEMO_RESET_TOKEN" <backend>/api/demo/reset`. Locally no token is needed.
- Then click **Simulate 40 traveller searches** once on `/demand` so the map and Gare Central's missed demand have
  data to show.
- Keep the browser zoom at 125 % so the jury can read the timeline.
