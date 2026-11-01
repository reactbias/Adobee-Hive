# Diagrams

Five hand-built SVGs. They scale, they diff as text, and they open in a browser with nothing
installed. [DIAGRAMS.md](../DIAGRAMS.md) holds the Mermaid graphs that GitHub renders inline; these
are the drawn ones, for reading and for a slide.

| | What it shows |
| --- | --- |
| [01-federation-topology](01-federation-topology.svg) | Hives peering, and how far a search reaches |
| [02-three-tier-privacy](02-three-tier-privacy.svg) | Public index · the folder a link opens · what a grant opens |
| [03-discovery-to-deal](03-discovery-to-deal.svg) | Search → connect → the real meeting → the score |
| [04-card-anatomy](04-card-anatomy.svg) | One Card, field by field |
| [05-current-architecture](05-current-architecture.svg) | **Browser to storage, as the code is now** |

## 05 is generated, and that is the point

It is drawn from what is actually on `main` — the module list, the real `from . import` edges, the
live route table, the MCP tool count — not from memory. A diagram that drifts is worse than none,
because a reader trusts a picture more than prose. Three doc pages in this repo were found claiming
things the code did not do; a diagram makes that kind of error bigger, not smaller.

So when it stops matching the code, **regenerate it rather than patching the SVG by hand**, and
re-check the claims in its two annotated columns: what crosses a hub boundary, and what is still not
true of the system. The last regeneration added `folder_keys.py`, `peers.py`, `removals.py` and
`services.py`, and deleted a column that still said the folder API was unbuilt — it had shipped.

It is deliberately honest about gaps: that both folders sit on one disk, that `owner_public_key` is
recorded and never checked against, that a requester is an unauthenticated string ([#158]), and that
a local introduction yields no calibration number ([#164]).

[#158]: https://github.com/reactbias/Adobee-Hive/issues/158
[#164]: https://github.com/reactbias/Adobee-Hive/issues/164
