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

## Positioning

| | |
| --- | --- |
| Product line | **The front door, signed.** |
| Promise | Adobee Hive gives every local business one signed card. Agents find it, verify it and book through it. The owner writes it in plain words, and nothing is booked until a person says yes. |
| Headline | The next guest is an agent. |
| Vision line (close of the pitch) | On GitHub you find projects to work on. On Adobee Hive, agents find businesses and people to work with. |

The four principles always carry these names, in this order, in the app, the readme and the pitch:

| Name | One line |
| --- | --- |
| Signed facts | Every card carries the owner's signature; agents verify it and turn away any altered copy. |
| Open ranking | Every result says why it won and why the others were left out. Placement cannot be bought. |
| Proof of stay | Only a signed booking receipt can leave a review. No stay, no review. |
| Your yes | Agents negotiate. People decide. Nothing is booked without your approval. |

And one idea beyond them: **missed demand**, "agents write the business plan".

## Voice

Short sentences. Facts before adjectives. Say what the product does, never how revolutionary it is: no
"seamless", "unlock", "empower", "AI-powered", no exclamation marks, no emoji. Privacy and ethics are stated as
plainly as features ("The Hive learns what was asked, never who asked"). One bee, used sparingly.

The interface ships in English, German, French and Italian, in the formal register (Sie, vous, Lei) with Swiss
spelling (ss, not ß), CHF and Swiss date formats. How to add a string: [CONTRIBUTING.md](../CONTRIBUTING.md).

## Colour and type

The page is paper and ink. Clay and honey are accents, used for one thing each: clay marks what matters on paper
(eyebrows, the chosen row, missed demand), honey marks life on the dark agent stage (live status, the wire, the
moment you approve). Status is always a dot and a word, never a pill.

| Token | Value | Use |
| --- | --- | --- |
| `--paper` | `#f6f3ed` | Page background, warm limestone |
| `--surface` | `#fffefb` | Panels, the approval card, the receipt |
| `--ink` | `#17140f` | Text, primary buttons, the agent stage |
| `--ink-2` / `--ink-3` | `#4b443a` / `#857c6f` | Secondary and quiet text |
| `--line` | `#e4ded3` | Hairlines |
| `--clay` | `#a24f2c` | Accents on paper; the logo bricks stay `#b85c34` |
| `--clay-dark` | `#5a2e1a` | Ink on clay |
| `--honey` | `#d49b1c` | Accents on the dark stage, focus rings, review stars |
| `--good` / `--bad` | `#2f6b46` / `#a3321f` | Valid and rejected |

Type: headings in **Mannin** by Cristiano Sobral ([1001fonts](https://www.1001fonts.com/mannin-font.html), free for
personal and commercial use under its UFL licence), falling back to Iowan Old Style, Palatino and Georgia. Text in
the system sans (SF Pro, Segoe UI, Inter); code and signatures in SF Mono. Headings are set at regular weight with
tight tracking; small uppercase eyebrows carry the section names. The font file still needs to be added: see
`code/frontend/public/fonts/README.md`.

Motion is purposeful only: turns on the agent stage arrive one after another, the wire pulses while agents talk, and
nothing moves with `prefers-reduced-motion`.
