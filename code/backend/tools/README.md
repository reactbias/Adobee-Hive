# tools

## mutate.py — does the suite actually notice?

Coverage proves a line ran. It does not prove a test would fail if that line were wrong.
`mutate.py` makes deliberate changes to the sixteen modules the design rests on — `app/hive.py`,
`registration.py`, `federation.py`, `folders.py`, `limits.py`, `connections.py`, `folder_keys.py`,
`reputation.py`, `peers.py`, `services.py`, `calibration.py`, `main.py`, `sharing.py`,
`semantic.py`, `removals.py` and `audit.py` — runs the suite, and reports every change that
**survived**, because a surviving mutant is a missing assertion, named and located. There are 78
curated mutants.

```bash
cd code/backend && source .venv/bin/activate
python tools/mutate.py                   # every curated mutant
python tools/mutate.py --workers 8       # how many to check at once (default: 4)
python tools/mutate.py --modules app/semantic.py,app/hive.py   # only these modules
python tools/mutate.py --random 12       # random operator and constant flips at real sites
python tools/mutate.py --random 12 --seed 42   # reproduce a run
python tools/mutate.py --all             # both
```

Exit code is the number of survivors, so CI can gate on it. Your checkout is never written to:
the mutants are applied in throwaway copies of the tree, and the copies are deleted on the way
out, including on SIGINT, SIGTERM and SIGHUP.

### Why it costs what it costs

A mutant can only be proved dead by running the tests against it, so one run is
(mutants) × (one suite run) — 71 × about 20s. Measured on a 20-core laptop: **19m34s**
one at a time, **6m28s** with four workers, same 71 mutants and the same `No survivors.`
Two things keep that waitable:

- **Four at a time.** Mutants are independent, but a mutant is applied by *editing the source in
  place*, so two cannot share a tree: the second would read the first's edit. Each worker gets its
  own `shutil.copytree` of the repo instead. A copy, not a `git worktree`, because a worktree
  checks out a *commit* and would quietly mutate the last commit rather than the code you are
  running this on — and because a copy works with no `.git` at all and leaves nothing to prune if
  the process is killed. The copies sit under a `mkdtemp`, so one left behind by a `kill -9` is
  nowhere an import, a linter or the next run could mistake for source.
- **`--modules` on a pull request.** A diff that touches `semantic.py` does not need every other
  mutant re-proved; they were proved on main and nothing they touch has changed.

What it deliberately does **not** do is narrow the *tests* per mutant. That is the biggest single
win left and the one that can quietly weaken the harness: a mutant that was only ever killed by a
test the narrowing excluded would start "surviving", or stop being asked at all. Every mutant that
runs runs every file in `SUITE`.

On a GitHub runner the whole job is **about 8 minutes** for all 71 — 7m28s and 8m51s on the two
runs measured — and a pull request that touches one module is a fraction of that. It was 32m11s on
PR #146.

`--workers` is a dial; the 120s suite timeout is not. It is a hang detector with six times the
headroom a green run needs, and raising it to make a red run go green would hide the thing it is
there to find.

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
| Hiding people from discovery again, and ignoring `looking_for` | The index is `offers` and `needs` now: these two aim at a hub that quietly goes back to being a room search, and at a search for who *offers* a thing answering with who *wants* it. |

### Known survivors

Three random mutants still live, all in *which human-readable reason string* gets attached to a
trust factor rather than in behaviour:

- `federation.py:335` — the hub set built for the trust report
- `reputation.py:131` and `:133` — which reason is recorded for a vetted peer

They are listed here rather than quietly dropped. Worth closing if the reasons become user-facing.

### In CI

A `mutation` job runs after `backend`, with four workers, in one of two modes:

- **On a pull request, the modules the diff touched.** The job diffs `code/backend/app/**.py`
  against the merge base and passes the result to `--modules`. A pull request touching only
  `semantic.py` checks 2 mutants instead of 71. A pull request that touches `tools/mutate.py` or
  `tests/test_mutation.py` gets the full set instead, so a new or edited mutant is never merged
  unproved.
- **On a push to main, all 71.** Main is never left permanently unchecked, whatever the pull
  requests skipped on the way in.

Either way the job prints its mode and its mutant count, in the log and in the job summary, before
it runs anything. A green check that silently ran zero mutants would be worse than the slow job it
replaced. If a pull request touches no backend module it says so in one line and passes.

**Curated mutants must all die.** They aim at invariants — the loop guard, the radius clamp, the
sign of the calibration error, a stale connection becoming scorable — so a survivor is a real hole
and the job fails. **A seeded random pass** of eight flips runs on main, seeded by the run number
so a different corner is probed each time while the log still says how to reproduce it. It is
`continue-on-error`, because a random mutant can surface a gap that predates the change and
blocking an unrelated pull request on it would only teach people to ignore the job.

`tests/test_mutation.py` guards the harness itself: every file in `SUITE` exists, every curated
mutant still matches its source, every target module is covered by a file in `SUITE`, a worker copy
carries everything the suite reads and sits outside the checkout, the harness refuses to mutate the
real tree if it is ever handed it, every mutant still runs the whole `SUITE`, the parallel report is
ordered by mutant and not by timing, and `--modules` cannot select nothing when it was given a
module that has mutants. Two of those exist because they already went wrong — the two hub test files
were missing from `SUITE`, so eight hub mutants "survived" while the real tests caught every one of
them, and the first copy-based run was rooted at `code/backend` and lost the `testdata/` the suite
reads. A mutation tool that reports a false all-clear is worse than none, so they are now tests.

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

## seed_calibration.py — give a hub's peers something to be judged by

On a fresh hub every place calibration appears says *"Unproven, no scored introductions yet"*: the
directory (`InstancePicker`), the hub network (`#network`) and the admin peer table. That is correct
and it shows nothing, because `calibration.MIN_EVIDENCE` is 3 and a hub holds no scored introductions
until real people have been introduced and have come back to say how it went.

This walks that chain for real, through the endpoints an agent would use, once per introduction:

```
on the peer:   POST /api/hive/cards/{id}/book   ->  a signed receipt
on the peer:   POST /api/hive/reviews           ->  the peer's *claim*: a verified-review average
on this hub:   POST /api/hub/connect            ->  freezes that claim onto the row as published_rating
on this hub:   POST /api/hub/connections/{id}/score  ->  what our person actually found
```

```bash
cd code/backend && source .venv/bin/activate
python tools/seed_calibration.py --hub http://192.168.21.123:8420 --plan   # print, change nothing
python tools/seed_calibration.py --hub http://192.168.21.123:8420          # peers from its directory
python tools/seed_calibration.py --hub http://h:8420 --peer zurich=http://h:8421 --only zurich
```

Run it against each of the three LAN hubs in turn and every screen then shows three different
readings. The profiles are chosen so one of them is **negative**: `bern` under-promises, claiming
three stars and over-delivering every time, and a negative error earns a *better* standing than a
perfect one costs. That is the part of the design nobody expects, and a demo that only ever shows
hubs being punished has not shown it.

Two things it deliberately does not do:

- **It does not write to the database.** A published rating can only come from a reviewed stay, so
  it books and reviews like a guest. If any part of the chain is broken the script fails here rather
  than on stage — which is how the `published_rating` bug below was found.
- **It does not seed the hub's own row.** An introduction to an entity the hub carries itself always
  lands with `published_rating = NULL`, because `hub.connect` takes the stored card body whose trust
  block has not been computed, so there is no `verified_reviews.average` to freeze. The home row in
  the directory is therefore permanently "unproven" however much the hub is used. That is a bug in
  the hub and is filed; until it is fixed, every hub shows two real numbers and one honest blank.

`tests/test_seed_calibration.py` pins both halves: that the chosen numbers come out of the hub's own
`calibration.score` as three readings a person can tell apart — with the under-promising one scoring
better than the over-promising one — and the whole chain end to end against a **real second hub in a
subprocess**, because every fake-based version of this passed while `published_rating` was `NULL`.
