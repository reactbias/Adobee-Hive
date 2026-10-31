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
| `zurich` | developers, designers, freelance technical work | a bike courier, a guesthouse in the woods |
| `bern` | local services and trades | a café, a developer who keeps COBOL alive |

## What is in it

61 entities: 20 on `basel`, 21 on `zurich`, 20 on `bern`. 11 of them take bookings (the stays, parsed
out of `rooms.md`), 43 carry a real `## What I need`, and between them they publish 178 offers and 47
needs. Contact sharing is mixed on purpose: 20 folders gate a channel behind `ask first` and 13 keep
one off the card entirely. Prose is in English, German, French and Italian.

41 query-to-entity pairs in the answer key below, plus four near-misses and twelve cross-hub
need-to-offer matches.

## Why this corpus exists

Today `hive.discover` scores a card by substring: a query term either appears in the card's text,
offers or needs, or it does not. `app/semantic.py` is written and tested to close that gap and no module imports
it yet ([LIMITS.md](../documentation/LIMITS.md#discovery)), so the numbers below are the measurement waiting for
it. So a search for **haircut** misses *"Cut, wash and finish"*, and a
search for **hotel** misses *"Gästehaus"*. That gap is built in here deliberately:

- owners write their own words — *"Siedfleisch am Donnerstag"*, *"Oberflächen für Maschinen"*,
  *"Cut, wash and finish"* — and guests type theirs;
- four languages, because a Basel hub really does hold a German, a French and an Italian card;
- near-misses that must rank **below** the real answer: a card that *mentions* a thing versus one
  that *offers* it;
- two thirds of the entities carry a real `## What I need`, so `looking_for=needs` has substance, and
  twelve of those needs are answered by an entity on another hub.

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
| frontend developer for our web shop | `jonas-brun` | zurich | builds the half you can see, Vue | "I build the half of a product you can see" |
| UX designer for a phone app | `fabienne-roulet` | zurich | wireframes and user journeys | "Je dessine des parcours et des maquettes" |
| control panel designer for medical devices | `tobias-wenger` | zurich | interfaces that must not be misread | "Oberflächen für Maschinen", "Medizintechnik" |
| technical writer for our documentation | `anouk-pfister` | zurich | runbooks and release notes | "the pages people read when something has gone wrong" |
| machine learning engineer | `kaspar-lienhard` | zurich | forecasting models | "builds the thing that guesses the next number" |
| database performance expert | `kuno-steinmann` | zurich | query and index work | "I make slow queries fast" |
| WCAG compliance check before we ship | `mirjam-oswald` | zurich | accessibility review | "a screen reader and a keyboard" |
| QA engineer for test automation | `leonie-frei` | zurich | breaks release candidates | "I break software on purpose" |
| agency to take over a half finished project | `quellcode-genossenschaft` | zurich | six-person co-operative | "Arbeit, die jemand liegengelassen hat" |
| retoucher for product photos | `bildwerk-retusche` | zurich | image post-production | "Wir arbeiten Bilder nach" |
| someone to build us a smartphone app | `basil-zuercher` | zurich | iPhone and Android work | "Apps für iPhone und Android" |
| somewhere to put our machines that is not a big cloud provider | `datenhaus-oerlikon` | zurich | small hosting outfit | "Wir stellen Server auf und betreuen sie" |
| same day delivery by bicycle | `kurierdienst-sihlquai` | zurich | courier, off this hub's domain | "Vier Leute, vier Velos" |
| where can I get a haircut | `schnittwerk-bern` | bern | two-chair hairdresser, walk-ins | "Cut, wash and finish", "Walk-ins before eleven" |
| someone to braid my hair for a party | `coiffure-bluemlisalp` | bern | hairdresser, by appointment | "Wir schneiden, färben und flechten" |
| electrician to put in a socket | `elektro-mattenhof` | bern | electrical work and inspections | "Steckdosen, Sicherungen, Elektrokontrollen" |
| tailor to shorten my trousers | `naehatelier-sulgenau` | bern | alterations | "Wir ändern Kleider: kürzen, enger machen" |
| piano tuner | `stimmwerk-aare` | bern | tunes pianos across the canton | "Wir stimmen Klaviere und Flügel" |
| accountant for our VAT | `treuhand-kehrli` | bern | bookkeeping for small businesses | "Buchhaltung, Mehrwertsteuer" |
| plumber for a leak on a Sunday | `sanitaer-hofstetter` | bern | emergency plumbing | "Wir kommen, wenn es tropft" |
| roofer after a storm | `dachdecker-laengmoos` | bern | roofing and repairs | "Wir decken Dächer", "was der Sturm aufgemacht hat" |
| gardener to cut a hedge twice a year | `gartenbau-weissenstein` | bern | garden maintenance | "Wir pflegen Gärten, schneiden Hecken" |
| my grandfather's wind up clock has stopped | `uhrmacher-bubenberg` | bern | watchmaker, mechanical only | "Wir bringen mechanische Uhren wieder zum Laufen" |
| driving lessons in a car with an automatic gearbox | `fahrschule-breitenrain` | bern | driving school, category B | "Fahrstunden", "auch mit Automat" |
| grooming for a nervous dog | `hundesalon-wankdorf` | bern | dog groomer (**unclaimed lead**) | "Wir baden und scheren Hunde, auch die nervösen" |
| picture framing for a large print | `bildrahmen-kramgasse` | bern | framing shop | "Wir fassen Bilder ein" |
| legacy code nobody dares to touch | `sami-kaufmann` | bern | COBOL and Delphi, off this hub's domain | "I keep old software alive" |

<!-- /answer-key -->

## Scoring it

```bash
cd code/backend
python tools/eval_answer_key.py           # every pair, with where it actually ranks
python tools/eval_answer_key.py --quiet   # just the totals
python tools/eval_answer_key.py --hub bern
```

It publishes the whole corpus into a throwaway database and calls `hive.discover` in process, so it
needs no running hub. Its exit code is the number of pairs not in the top three, so CI can gate on it.

**The baseline, measured on `main` at the time of writing: `0/41` first, `0/41` in the top three.**
Every pair is a miss while matching is literal; `app/semantic.py` has landed with its own tests but
is not yet wired into `discover`, so this number is the one to watch, not a bug in the key.

## Near-misses: what must rank *below*

Precision is only measurable against something that nearly fits. These cards literally contain the
query's words and are still the wrong answer, so a search that ranks them first has got worse, not
better.

| Query | Ranks first on substring today | Why that is wrong | Should win |
| --- | --- | --- | --- |
| quiet café where I can work on my laptop | `teestube-amselhof` — its card says "keine Laptops nach vierzehn Uhr" | the only card with the word *Laptops* bans them | `cafe-rhein` ("the long table for a quiet morning meeting") |
| vegan food for under ten francs | `cafe-rhein` and `suppenkueche-dreirosen` both say *vegan* | one is an CHF 18 all-day breakfast, the other a CHF 9 pot | `suppenkueche-dreirosen` |
| someone who can write Rust | measured on the running hub: `niko-ferrer` 15, `svenja-aebi` 15, then **`mirjam-oswald` 10**, and `renzo-balmer` 5 | the two who offer Rust do come first, but an accessibility reviewer who never mentions it beats the one who does, because the word *someone* appears in one of her offers. Filler words earn offer points. | `svenja-aebi`, `niko-ferrer`, then `renzo-balmer` last — his card says "I read about Rust on the train and have never once been paid for it" |
| React developer | `ilaria-conti` wins, correctly | the control: exactly one card in the corpus uses the client's word | `ilaria-conti`, then `jonas-brun` and `tobias-wenger`, who score zero today |
| frontend developer for our web shop | measured: **`mirjam-oswald` 10**, everyone else 0 | she is the only card containing the string *developer* — in an offer about sitting next to yours. The three people who actually build interfaces score nothing. | `jonas-brun`, `ilaria-conti`, `tobias-wenger` |

## Both sides of the market

Some needs are answered by an entity on a different hub, which is what federation is for:

| Who needs it | Hub | Who offers it | Hub |
| --- | --- | --- | --- |
| `wirtshaus-anker` — "Jemand, der unsere Zimmer fotografiert" | basel | `lichtfeld-foto` — half-day shoot for a hotel | bern |
| `mira-luetolf` — "make a report look like something" | basel | `lena-hofmann` — dataviz sprint, design system audit | zurich |
| `beizli-sternen` — "eine Seite, die ein Agent lesen kann" | basel | `schnittwerk-bern` needs the same thing | bern |
| `lichtfeld-foto` — "a retoucher for busy months" | bern | `bildwerk-retusche` — CHF 12 an image | zurich |
| `datenhaus-oerlikon` — "eine Elektrikerin für einen zweiten Stromkreis" | zurich | `elektro-mattenhof` | bern |
| `kurierdienst-sihlquai` — "unsere vier Velos im Winter wartet" | zurich | `velowerk-bern` — service and safety check | bern |
| `aylin-dervis` and `grid-ops` — "a technical writer" | zurich | `anouk-pfister` — runbooks | zurich |
| `gaestehaus-sonnenrain` — "eine Gärtnerin für den Frühling" | basel | `gartenbau-weissenstein` | bern |
| `roesterei-vogelsang` — "eine Buchhalterin für die Mehrwertsteuer" | basel | `treuhand-kehrli` | bern |
| `wirtshaus-anker` — "ein Sanitär, der am Sonntag abnimmt" | basel | `sanitaer-hofstetter` — emergency at the weekend | bern |
| `logis-vieux-moulin` — "un couvreur pour le toit" | basel | `dachdecker-laengmoos` | bern |
| `kanalhaus-lofts` — "eine Reinigungsfirma für den Wechseltag" | basel | `reinigung-sternenfeld` | bern |
| `sami-kaufmann` — "someone to break it on purpose" | bern | `leonie-frei` — breaks release candidates | zurich |
| `schreinerei-ostermundigen` — "jemand, der unsere Möbel fotografiert" | bern | `lichtfeld-foto` | bern |

## Trust signals

Varied on purpose, because a real directory is mostly unrated:

- **`rating: null` on every seeded card.** A verified rating needs the signed receipt of a completed
  booking (`hive.review`), so seeding cannot manufacture one, and it should not be able to.
  `reviews.md` in a few folders is owner-written prose; the parser walks past it and it never becomes
  a rating.
- **Unclaimed:** `villa-hirzbrunnen`, `imbiss-rheinbord`, `hundesalon-wankdorf`. Compiled from public information, so the
  hub reports them as leads and no agent may treat them as a business that agreed to anything.
- **Contact sharing:** published, `ask first` and `never` all appear, so consent is exercised rather
  than assumed.

## Regenerating

```bash
cd code/backend
python tools/make_corpus.py               # write the folders from the table
python tools/make_corpus.py --check       # fail if a folder drifted from the table
python tools/make_corpus.py --print-maps  # the HOME, KIND and UNCLAIMED entries for seed_vaults.py
```

Adding an entity is three steps: a row in the table, `make_corpus.py`, then paste `--print-maps`
into `seed_vaults.py`. A test fails until the two agree, so the paste cannot be forgotten.

## Seeding time

All 61, signed and posted one at a time through the real `POST /api/hub/register` on three hubs:
**1.4 seconds** cold, three interpreter starts included (0.37 s basel, 0.45 s zurich, 0.48 s bern).
A restart is not a reason to shrink the corpus.
