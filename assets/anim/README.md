# The explainer film

`hive_federation.py` draws [`../hive-federation.mp4`](../hive-federation.mp4): sixty seconds on how the federated
backend works — one signed card, many Hives, a search whose reach the person chooses, and the two levels of trust.
It is the moving version of [documentation/FEDERATION.md](../../documentation/FEDERATION.md).

Every frame is drawn in code, so the film is edited by editing Python, not by re-cutting a video. Colours and type
come from [documentation/BRAND.md](../../documentation/BRAND.md): paper and ink with one accent, clay; Instrument
Serif for display, Mannin for text, Geist Mono for tool names. The faces are read from
`code/frontend/public/fonts/` and converted into a gitignored `.fontcache/`, so the licensed binaries live in
exactly one place in the repo.

## Render it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pillow imageio imageio-ffmpeg numpy fonttools brotli
python hive_federation.py            # the 60s film  -> ../hive-federation.mp4
python hive_federation.py --stills   # one PNG per scene -> ../slides/
python hive_federation.py --preview 4  # three frames of scene 4, to check a change
```

`imageio-ffmpeg` brings its own ffmpeg binary, so nothing needs installing system-wide. These are tools for this
one script and are deliberately not in the backend's requirements.

## The scenes

| # | Scene | Says |
| --- | --- | --- |
| 1 | Adobee Hive | The front door, signed |
| 2 | One card, signed | The business publishes the facts; the agent verifies them itself |
| 3 | Many Hives | A town, an association, a trade body — each can run one |
| 4 | How far to look | Radius 0, 1, 2: the person sets the reach |
| 5 | Two levels of trust | The Hive is rated for honesty; the business for what it delivered |
| 6 | Open ranking | Every answer says why, and where it came from |
| 7 | Close | On Adobee Hive, agents find businesses and people to work with |

To change a line, edit the scene function of the same name and re-render. To change the timing, edit `SCENES` at
the top; the chapter rule at the foot of the frame follows it automatically.
