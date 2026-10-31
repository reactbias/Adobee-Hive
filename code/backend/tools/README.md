# tools

## eval_search.py — is the search actually better?

> The hub's own answer key lives in `testdata/README.md` and `eval_answer_key.py` scores it. Run that one for
> the headline number (`19/41 first, 30/41 in the top three`, against `0/41` for literal matching). This script
> answers the neighbouring question — *what did the change do?* — by running the same key twice, once with the
> semantic component switched off, and adding the seeded hotels and example cards as extra distractors.

Semantic search is easy to believe in and hard to be sure about: a synonym table that reads well in a
docstring can quietly make every card similar to every query. `eval_search.py` builds a hub out of
`testdata/vaults/`, runs a list of query-to-expected pairs through `hive.discover()` twice — once with the
semantic component off, which is the literal substring search we started from, and once with it on — and
prints **precision at 1 and at 3** for both, plus the share of queries where the hub had any reason at all to
return the right entity rather than returning it by the luck of a tie-break:

```
                            literal only    with semantics
  precision at 1                 0.000            0.415
  precision at 3                 0.000            0.707
  queries with any evidence      0.000            0.805
```

Seventeen queries fixed, none broken.

```bash
cd code/backend && source .venv/bin/activate
python tools/eval_search.py              # the before and after table, and which queries changed
python tools/eval_search.py --verbose    # every query, its top three, and the reason the hub gave
python tools/eval_search.py --floor      # the similarity of every pair, expected and not
python tools/eval_search.py --sweep      # precision at each candidate floor: how the floor was chosen
```

The pairs come from `testdata/README.md` when it carries a query-to-expected table, so whoever writes the
corpus owns the scoring set; the list in the script is the fallback and the output says which was used. Exit
code is 1 when the semantic run scores *worse* than the literal one, so a change that makes search worse can
be caught by a machine instead of by a jury.

It is a measurement, not a test, and it is deliberately not in `pytest`: the suite pins behaviour that must
never regress, while this number is allowed to move as the corpus grows. `--sweep` is the one to run before
touching `semantic.SIMILARITY_FLOOR`.

## mutate.py — does the suite actually notice?

Coverage proves a line ran. It does not prove a test would fail if that line were wrong.
`mutate.py` makes deliberate changes to the eight modules the design rests on — `app/hive.py`,
`federation.py`, `reputation.py`, `calibration.py`, `connections.py`, `registration.py`,
`sharing.py` and `semantic.py` — runs the suite, and reports every change that **survived**, because
a surviving mutant is a missing assertion, named and located. There are 35 curated mutants.

```bash
cd code/backend && source .venv/bin/activate
python tools/mutate.py                   # every curated mutant
python tools/mutate.py --random 12       # random operator and constant flips at real sites
python tools/mutate.py --random 12 --seed 42   # reproduce a run
python tools/mutate.py --all             # both
```

Exit code is the number of survivors, so CI can gate on it. The source file is always restored,
even when a run is interrupted.

Run the suite with **no model key in your environment**. An `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`
exported in your shell makes the agent answer live, and the tests that pin what the offline planner
writes then fail for a reason that has nothing to do with your change. CI has no key, which is why
it does not see this.

### What it has caught

| Mutant | What it revealed |
| --- | --- |
| Dropping the `max(0, ...)` clamp on the radius | A negative radius meant "local" by luck, not by design. Three layers now assert it. |
| Blanking `owner_keys` in the peer parser | `HttpTransport` had **no test at all** — the fakes replace it — so the parser that supplies the keys every relayed card is verified against was never run. |
| Inverting the filter in `hop_params()` | A forwarded query could arrive empty and nothing noticed. |
| Blanking a peer's `ranking_policy` | Paid placement is detected from that string, so a hub silently stopped downgrading peers that sell rank. |
| Dropping the similarity floor, and ignoring the semantic score | The floor is the whole difference between "close to what you asked for" and "everything is a bit like everything". Without it the component is a constant and ranks nothing; without the score a search for "haircut" goes back to missing *"Cut, wash and finish"*. |
| Hiding people from discovery again, and ignoring `looking_for` | The index is `offers` and `needs` now: these two aim at a hub that quietly goes back to being a room search, and at a search for who *offers* a thing answering with who *wants* it. |

### Known survivors

Three random mutants still live, all in *which human-readable reason string* gets attached to a
trust factor rather than in behaviour:

- `federation.py:335` — the hub set built for the trust report
- `reputation.py:131` and `:133` — which reason is recorded for a vetted peer

They are listed here rather than quietly dropped. Worth closing if the reasons become user-facing.

### In CI

A `mutation` job runs after `backend` on every pull request:

- **Curated mutants must all die.** They aim at invariants — the loop guard, the radius clamp, the
  sign of the calibration error, a stale connection becoming scorable — so a survivor is a real
  hole and the job fails.
- **A seeded random pass** of eight flips runs alongside, seeded by the run number so a different
  corner is probed each time while the log still says how to reproduce it. It is
  `continue-on-error`, because a random mutant can surface a gap that predates the pull request
  and blocking an unrelated change on it would only teach people to ignore the job.

`tests/test_mutation.py` guards the harness itself: every file in `SUITE` exists, every curated
mutant still matches its source, and every target module is covered by a file in `SUITE`. That
last one exists because it already went wrong — the two hub test files were missing from `SUITE`,
so eight hub mutants "survived" while the real tests caught every one of them. A mutation tool
that reports a false all-clear is worse than none, so it is now a test.

### Adding a mutant

Add to `CURATED` in `mutate.py`: the file, one line on what the bug would break, the exact string to
find, and what to put there. Aim at an invariant, not at a line — "the loop guard goes" is a useful
mutant, "this plus became a minus" usually is not.

## serve_folders.py — three folders an end-user agent can crawl

A Card is already structured. The harder half of search is the one an agent has on the owner's own
machine: point it at a folder of real files and ask it a question. This serves three such folders
over HTTP with a directory listing, so an agent can crawl them with nothing but an HTTP client — no
Python, no venv, no knowledge of this repo.

```bash
cd code/backend && source .venv/bin/activate
python tools/serve_folders.py                   # the three default vaults on 127.0.0.1:8600
python tools/serve_folders.py --list            # print what would be served, serve nothing
python tools/serve_folders.py --host 0.0.0.0    # reachable from another device
python tools/serve_folders.py --vault hotel-krafft --vault lena-hofmann
python tools/serve_folders.py --strict          # only `public`, not `public-summary`
```

The three defaults are deliberately unlike each other — `wirtshaus-anker` (a stay on `basel`),
`jonas-brun` (a person on `zurich`) and `elektro-mattenhof` (a service on `bern`) — and between them
they carry markdown, PDFs, PNGs and CSVs. Each one also withholds something, so the privacy boundary
is in every folder rather than in a footnote.

**It will not serve anything the owner marked `private`, `shared` or `hidden`.** The visibility
parser is imported from `seed_vaults.py` rather than reimplemented, so the served set cannot drift
from the `structure` rows the hub publishes; `tests/test_serve_folders.py` asserts the two sets are
equal folder by folder, that every withheld path answers 404, and the strong form — that no line of
any withheld file and no withheld path appears in **any** response the server will give. A `private`
folder is listed as a count and nothing else; a `hidden` one is not mentioned at all.

Worked examples, and the expected answer to a question per folder so another team can tell whether
their agent works: [documentation/SEARCH_API.md](../../../documentation/SEARCH_API.md).
