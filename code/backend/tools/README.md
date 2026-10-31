# tools

## mutate.py — does the suite actually notice?

Coverage proves a line ran. It does not prove a test would fail if that line were wrong.
`mutate.py` makes deliberate changes to `app/federation.py`, `app/reputation.py` and `app/hive.py`,
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
