# The pitch film

`hive_federation.py` draws [`../hive-federation.mp4`](../hive-federation.mp4): about a minute, in the three
slides the pitch is built on — the punchline, the vision, and one hotel booked end to end. The model it shows is
the one that runs: [documentation/FEDERATION.md](../../documentation/FEDERATION.md) for the federation and
[documentation/cards/](../../documentation/cards/README.md) for the Card, whose real fields are what appears on
screen.

Every frame is drawn in code, so the film is edited by editing Python, not by re-cutting a video. Colours and type
come from [documentation/BRAND.md](../../documentation/BRAND.md): paper and ink with one accent, clay; Instrument
Serif for display, Mannin for text, Geist Mono for tool names. The faces are read from
`code/frontend/public/fonts/` and converted into a gitignored `.fontcache/`, so the licensed binaries live in
exactly one place in the repo.

## Render it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pillow imageio imageio-ffmpeg numpy fonttools brotli
python hive_federation.py              # the film -> ../hive-federation.mp4
python hive_federation.py --stills     # one PNG per slide -> ../slides/
python hive_federation.py --variant b  # cut the film with slide-2 version B
python hive_federation.py --preview 4  # three frames of scene 4, to check a change
```

`imageio-ffmpeg` brings its own ffmpeg binary, so nothing needs installing system-wide. These are tools for this
one script and are deliberately not in the backend's requirements.

## The scenes

| # | Scene | Slide | Says |
| --- | --- | --- | --- |
| 1 | Adobee Hive | 1 | A bee leaves the Hive, five more arrive, and they merge into one agent |
| 2 | The vision | 2 | Entities with their own folders, listed on hives as JSON, searched by agents |
| 3 | The ask | 3a | One sentence from a guest; her agent is built from her own entity |
| 4 | The hives | 3b | Interconnected hotel hives, best-calibrated first, and the route the answer took |
| 5 | The match | 3c | The listing is condensed JSON; an agent is built out of the matched entity |
| 6 | Two agents | 3d | Dates, price and check-in, settled between the two agents |
| 7 | Your yes | 3e | She approves, and only then does it book. The receipt is signed |
| 8 | Adobee Hive | — | Close |

To change a line, edit the scene function of the same name and re-render. To change the timing, edit `SCENES` at
the top; the chapter rule at the foot of the frame follows it automatically.

## Slide 2 has three versions

The vision slide is drawn three ways so the team can pick by looking, not by arguing. `--stills` writes all three;
`--variant` chooses the one the film is cut with (`a` by default).

| Version | Function | How it argues |
| --- | --- | --- |
| `a` flow | `v_flow` | Four steps in reading order: entity, hive, search, match. The shortest to narrate |
| `b` network | `v_network` | The federation as a graph, with each hive's error written on the edge to its peer |
| `c` data | `v_data` | The artefacts: the folder shape, the served JSON, and the two ratings as a table |

All three end on the same two lines, because that is the part a jury asks about: an entity is rated only from a
signed receipt or a scored meeting, and a hive is rated by its peers on `published - realised`, in tenths of a
star, lower being better.

## The bee

`Canvas.bee` draws the B6 mascot along a heading: a striped body in clay, two loop wings that flap, one curly
antenna, and a flip so a bee flying leftwards keeps its back up. The bees fly on cubic beziers
(`bez`, `bez_heading`) and leave a short trail, so the opening frame shows agents converging rather than shapes
moving. Nothing else in the film moves that does not carry a meaning.
