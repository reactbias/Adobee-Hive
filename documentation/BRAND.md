# Brand

![Adobee Hive wordmark](../assets/brand/adobee-hive-wordmark.png)

## Name

**Adobee Hive**, one word Adobee: *adobe* is sun-dried clay brick, plus the *bee*. A hive is what bees build;
the Hive is what local businesses build together. Short form ABH.

## Logo

A hexagon of hand-moulded clay bricks with the bee in its recess, from the whiteboard sketch. Clay because adobe
means clay; a hexagon because it is the honeycomb cell.

| File | Use |
| --- | --- |
| `code/frontend/public/brand/logo.svg` | Master logo (clay texture via SVG filters) |
| `code/frontend/public/brand/favicon.svg` | Simplified, no filters, for small sizes |
| `code/frontend/public/brand/wordmark.svg` | Logo plus name, self-contained |
| `assets/brand/*.png` | Exports for slides |

## Mascot: the B6 bee

![The B6 bee](../assets/brand/b6-bee-mascot.png)

Traced from the team's whiteboard drawing: striped, hatched body, two loop wings, curly antenna
(`code/frontend/public/brand/mascot.svg`). We are team **B6**: the bee is the B, and it carries the 6.

The easter egg is deliberately quiet. The bee sleeps in the footer next to "Team B". Click it, or leave the app idle
for a minute, and it flies across the bottom of the page, dropping six little 6s. It never flies with
`prefers-reduced-motion`. The rest of the app stays serious.

## Colour and type

| Token | Value | Use |
| --- | --- | --- |
| `--honey` | `#f5b700` | Nav, primary buttons |
| `--clay` | `#b85c34` | Logo bricks, accents, the flying 6s |
| `--clay-dark` | `#5a2e1a` | Wordmark, ink on clay |
| `--paper` | `#fffdf6` | Background |
| `--ink` | `#1d1a14` | Text |

Headings use **Mannin** by Cristiano Sobral ([1001fonts](https://www.1001fonts.com/mannin-font.html), free for
personal and commercial use under its UFL licence), with Georgia as fallback. The font file still needs to be added:
see `code/frontend/public/fonts/README.md`.
