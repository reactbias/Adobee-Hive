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
`mutate.py` makes deliberate changes to `app/federation.py`, `app/reputation.py`, `app/hive.py` and
`app/semantic.py`,
runs the suite, and reports every change that **survived** — because a surviving mutant is a missing
assertion, named and located.

```bash
cd code/backend && source .venv/bin/activate
python tools/mutate.py                   # every curated mutant
python tools/mutate.py --random 12       # random operator and constant flips at real sites
python tools/mutate.py --random 12 --seed 42   # reproduce a run
python tools/mutate.py --all             # both
```

Exit code is the number of survivors, so CI can gate on it. The source file is always restored,
even when a run is interrupted.

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
