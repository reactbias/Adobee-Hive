# testdata — the corpus semantic search is measured against

`vaults/` holds 28 fictional entities, one folder of markdown each, registered through the real signup
endpoint by `code/backend/tools/seed_vaults.py`. Ten folders are hand-written; the rest come from the
curated table in `code/backend/tools/make_corpus.py`. Nothing here is a real business or a real person.

`./lan.sh up` from the repository root is what puts them on three peered hubs and serves the app in front of
them: see [documentation/DEVELOPER.md](../documentation/DEVELOPER.md#three-hubs-on-one-machine-lansh).

Three hubs, mixed on purpose — a hub is what it mostly carries, never a rule it enforces:

| Hub | Mostly | Also |
| --- | --- | --- |
| `basel` | stays, cafés, places to eat | a laundry, a locksmith, a data freelancer |
| `zurich` | developers, designers, freelance technical work | — |
| `bern` | local services and trades | — |

## Why this corpus exists

Today `hive.discover` scores a card by substring: a query term either appears in the card's text,
offers or needs, or it does not. `app/semantic.py` is written and tested to close that gap and no module imports
it yet ([LIMITS.md](../documentation/LIMITS.md#discovery)), so the numbers below are the measurement waiting for
it. So a search for **haircut** misses *"Cut, wash and finish"*, and a
search for **hotel** misses *"Gästehaus"*. That gap is built in here deliberately:

- owners write their own words — *"Siedfleisch am Donnerstag"*, *"builds interfaces"*, *"Cut and
  finish"* — and guests type theirs;
- four languages, because a Basel hub really does hold a German, a French and an Italian card;
- near-misses that must rank **below** the real answer: a card that *mentions* a thing versus one
  that *offers* it;
- roughly half of the entities carry a real `## What I need`, so `looking_for=needs` has substance,
  and some needs are answered by an entity on another hub.

## The answer key

Each row is a query a person would plausibly type, and the entity it should return. **No row shares a
searchable word with its target** — `tests/test_seed_vaults.py` fails if one ever does, so the key
cannot quietly soften. Literal matching scores every one of these at zero relevance today; that is
the measurement.

<!-- answer-key -->

| What a person types | Should return | Hub | What it is | The words the card uses instead |
| --- | --- | --- | --- | --- |
| simple room over a tavern, under a hundred francs | `wirtshaus-anker` | basel | seven rooms over a tavern | "Zimmer über der Gaststube" |
| bed and breakfast with a garden | `gaestehaus-sonnenrain` | basel | nine-room guesthouse in Riehen | "Gästehaus", "Frühstück im Garten" |
| hostel with bunk beds for a school group | `herberge-dreiland` | basel | dorm beds from CHF 36 | "Mehrbettzimmer", "Gruppen willkommen" |
| furnished apartment for a three month contract | `kanalhaus-lofts` | basel | serviced lofts, minimum four weeks | "Wohnen auf Zeit", "möblierte Lofts" |
| houseboat | `schiffsquartier-mathilde` | basel | two cabins on a barge | "converted freight barge", "Kabine" |
| a family place in the country where dinner is cooked for you | `logis-vieux-moulin` | basel | three rooms in an old mill | "Chambres d'hôtes", "Table d'hôte" |
| somewhere I can let myself in by myself after midnight | `villa-hirzbrunnen` | basel | nine rooms, door code by SMS (**unclaimed lead**) | "Nach zwanzig Uhr ist niemand mehr da" |
| somewhere that serves boiled beef on Thursdays | `beizli-sternen` | basel | neighbourhood eatery, twelve seats | "Siedfleisch am Donnerstag" |
| where to buy freshly roasted coffee beans | `roesterei-vogelsang` | basel | roastery with eight seats | "Wir rösten hinten im Laden", "Bohnen" |
| italian restaurant with homemade noodles | `trattoria-barcarola` | basel | six-table osteria | "osteria", "pasta fresca" |
| laundry for hotel bed sheets, picked up daily | `textilpflege-gundeli` | basel | linen service for guesthouses | "Wäscherei", "Bettwäsche pro Kilo" |
| catering for a wedding of fifty people | `kuechenkollektiv-klybeck` | basel | four cooks who come to your kitchen | "Wir kochen in Ihrer Küche", "Hochzeiten" |
| I locked myself out of my apartment | `schluesseldienst-spalen` | basel | locksmith, day and night | "Türen öffnen", "Zylinder wechseln" |
| automate our monthly Excel reports | `mira-luetolf` | basel | data freelancer, off this hub's domain | "outgrown their spreadsheets", "import jobs" |

<!-- /answer-key -->

## Near-misses: what must rank *below*

Precision is only measurable against something that nearly fits. These cards literally contain the
query's words and are still the wrong answer, so a search that ranks them first has got worse, not
better.

| Query | Ranks first on substring today | Why that is wrong | Should win |
| --- | --- | --- | --- |
| quiet café where I can work on my laptop | `teestube-amselhof` — its card says "keine Laptops nach vierzehn Uhr" | the only card with the word *Laptops* bans them | `cafe-rhein` ("the long table for a quiet morning meeting") |
| vegan food for under ten francs | `cafe-rhein` and `suppenkueche-dreirosen` both say *vegan* | one is an CHF 18 all-day breakfast, the other a CHF 9 pot | `suppenkueche-dreirosen` |

## Both sides of the market

Some needs are answered by an entity on a different hub, which is what federation is for:

| Who needs it | Hub | Who offers it | Hub |
| --- | --- | --- | --- |
| `wirtshaus-anker` — "Jemand, der unsere Zimmer fotografiert" | basel | `lichtfeld-foto` — half-day shoot for a hotel | bern |
| `mira-luetolf` — "make a report look like something" | basel | `lena-hofmann` — dataviz sprint, design system audit | zurich |
| `beizli-sternen` — "eine Seite, die ein Agent lesen kann" | basel | `schnittwerk-bern` needs the same thing | bern |

## Trust signals

Varied on purpose, because a real directory is mostly unrated:

- **`rating: null` on every seeded card.** A verified rating needs the signed receipt of a completed
  booking (`hive.review`), so seeding cannot manufacture one, and it should not be able to.
  `reviews.md` in a few folders is owner-written prose; the parser walks past it and it never becomes
  a rating.
- **Unclaimed:** `villa-hirzbrunnen`, `imbiss-rheinbord`. Compiled from public information, so the
  hub reports them as leads and no agent may treat them as a business that agreed to anything.
- **Contact sharing:** published, `ask first` and `never` all appear, so consent is exercised rather
  than assumed.

## Regenerating

```bash
cd code/backend
python tools/make_corpus.py            # write the folders from the table
python tools/make_corpus.py --check     # fail if a folder drifted from the table
python tools/make_corpus.py --print-maps  # the HOME, KIND and UNCLAIMED entries for seed_vaults.py
```
