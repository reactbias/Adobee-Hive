"""The mutation harness has to be trustworthy itself.

A mutant can only be killed by a test that actually runs, so a target module missing from
tools/mutate.py's SUITE produces a confident all-clear over code nothing exercised. That is worse
than no mutation testing at all, and it happened once: the two hub test files were left out of
SUITE and every hub mutant "survived" while the real tests caught all of them.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _mutate():
    """Load tools/mutate.py as a module. It must be in sys.modules first, or @dataclass cannot
    resolve its own module and raises."""
    if "mutate" in sys.modules:
        return sys.modules["mutate"]
    spec = importlib.util.spec_from_file_location("mutate", ROOT / "tools" / "mutate.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["mutate"] = module
    spec.loader.exec_module(module)
    return module


def test_every_file_in_the_suite_exists():
    """A path that does not exist makes pytest fail, which the harness would read as 'killed'."""
    mutate = _mutate()
    assert [p for p in mutate.SUITE if not (ROOT / p).exists()] == []


def test_every_curated_mutant_points_at_a_string_that_is_really_there():
    """A pattern that has drifted prints SKIP, which is quiet enough to miss in a long run."""
    mutate = _mutate()
    missing = [
        f"{m.file}: {m.find!r}"
        for m in mutate.CURATED
        if m.path.exists() and m.find not in m.path.read_text(encoding="utf-8")
    ]
    assert missing == [], "these mutants no longer match their source"


def test_every_target_module_is_covered_by_a_file_in_the_suite():
    """The failure that actually happened: a target with no test file in SUITE is never checked."""
    mutate = _mutate()
    suite = " ".join((ROOT / p).read_text(encoding="utf-8") for p in mutate.SUITE if (ROOT / p).exists())
    uncovered = [t for t in mutate.TARGETS if t.removesuffix(".py") not in suite]
    assert uncovered == [], "no file in SUITE imports these, so their mutants cannot be killed"


def test_the_curated_mutants_cover_every_target_module():
    """Each module we mutate should have at least one hand-aimed mutant, not only random flips."""
    mutate = _mutate()
    aimed = {m.file for m in mutate.CURATED}
    assert set(mutate.TARGETS) - aimed == set(), "add a curated mutant for these"


def test_a_run_refuses_to_start_when_a_mutant_is_live_in_the_source():
    """A killed run leaves the source broken in a way that looks like a real failing test.

    The restore is in a `finally`, which survives an exception and a Ctrl-C but not a SIGKILL. That
    happened: a kill left `if state != WITHDRAWN` in registration.py and two unrelated-looking test
    failures. A run now refuses to start until the tree is clean.
    """
    mutate = _mutate()
    assert mutate.live_mutants() == [], "a mutant is sitting in the source right now"
    assert callable(mutate.live_mutants)


# --- Running the mutants in parallel -------------------------------------------------
# Each worker mutates its own copy of the tree, because a mutant is applied by editing the source
# in place. Two things have to stay true however many workers there are: a mutant is never written
# into the real checkout, and every mutant that runs still runs the whole suite.


@pytest.fixture
def trees():
    """One worker copy, cleaned up afterwards rather than at interpreter exit."""
    mutate = _mutate()
    made = mutate.make_trees(1)
    yield made
    mutate.drop_run_dir()


def test_a_worker_copy_is_outside_the_real_checkout(trees):
    """The point of the copy: a run that is SIGKILLed cannot have touched the developer's tree."""
    mutate = _mutate()
    tree = trees[0]
    assert tree != ROOT
    assert ROOT not in tree.parents, "a worker copy inside the checkout defeats the whole exercise"
    assert mutate.run_dir() in tree.parents


def test_a_worker_copy_carries_everything_the_suite_reads(trees):
    """The suite is not self-contained inside code/backend, and a copy that forgets that goes red.

    tests/test_folders.py reads testdata/vaults/ and tests/test_limits.py reads
    documentation/cards/README.md, both from the repo root. Copying code/backend alone makes the
    pre-flight report "the suite is already red" about the copy rather than about the code.
    """
    tree = trees[0]
    for needed in ("app", "tests", "tools", "pytest.ini"):
        assert (tree / needed).exists(), f"the copy is missing {needed}"
    repo = tree.parents[1]
    assert (repo / "testdata" / "vaults").is_dir(), "test_folders.py reads this"
    assert (repo / "documentation" / "cards" / "README.md").is_file(), "test_limits.py reads this"


def test_a_mutant_is_never_written_into_the_real_checkout(trees):
    """The guard, not the intention: handed the real tree, the harness refuses instead of editing.

    Nothing should ever call check() with the real tree, which is exactly why this is checked.
    """
    mutate = _mutate()
    victim = mutate.CURATED[0]
    before = victim.path.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing to mutate"):
        mutate.check(victim, ROOT)
    assert victim.path.read_text(encoding="utf-8") == before


def test_every_mutant_still_runs_the_whole_suite(trees, monkeypatch):
    """The optimisation that is not being made: narrowing the suite per mutant.

    A mutant killed only by a test that a narrowed suite left out would start surviving, or worse
    stop being noticed. So however the mutants are filtered or parallelised, the command each one
    runs names every file in SUITE.
    """
    mutate = _mutate()
    seen = []

    class FakeChild:
        returncode = 0

        def communicate(self, timeout=None):
            return "", ""

    def fake_popen(cmd, **kwargs):
        seen.append((cmd, kwargs["cwd"]))
        return FakeChild()

    monkeypatch.setattr(mutate.subprocess, "Popen", fake_popen)
    mutate.run_suite(trees[0])
    cmd, cwd = seen[0]
    assert cwd == trees[0], "the suite has to run in the copy that holds the mutant"
    assert [f for f in mutate.SUITE if f not in cmd] == [], "a suite file was dropped from the run"
    assert "-x" in cmd, "a mutant killed by the second test should not pay for the other 395"


def test_results_are_printed_in_the_order_the_mutants_were_listed(trees, monkeypatch, capsys):
    """Interleaved worker output is unreadable, so the report order must not depend on timing."""
    mutate = _mutate()
    listed = mutate.CURATED[:6]

    def fake_check(mutant, tree, timeout=None):
        # Later mutants finish first, which is what a real parallel run does.
        time.sleep(0.02 * (len(listed) - listed.index(mutant)))
        return mutate.Result(mutant, False, [f"killed {mutant.title}"])

    monkeypatch.setattr(mutate, "check", fake_check)
    results = mutate.run_mutants(list(listed), mutate.make_trees(3))
    assert [r.mutant for r in results] == list(listed), "the results must come back in listed order"
    printed = capsys.readouterr().out.splitlines()
    assert printed == [f"killed {m.title}" for m in listed]


def test_a_survivor_is_still_reported_as_a_survivor(trees, monkeypatch, capsys):
    """The verdict has to survive the rewrite: a green suite under a mutant means it lived."""
    mutate = _mutate()
    victim = mutate.CURATED[0]
    monkeypatch.setattr(mutate, "run_suite", lambda *a, **k: True)
    result = mutate.check(victim, trees[0])
    assert result.survived is True
    assert "SURVIVED" in result.lines[0]
    assert victim.why in result.lines[1]
    # And the file it mutated is back the way it was, even though the mutant lived.
    assert victim.find in victim.path_in(trees[0]).read_text(encoding="utf-8")


def test_an_interrupted_run_puts_every_held_file_back(trees):
    """_IN_FLIGHT holds one entry per worker now; the handler has to restore all of them."""
    mutate = _mutate()
    held = [mutate.CURATED[0].path_in(trees[0]), mutate.CURATED[7].path_in(trees[0])]
    originals = [p.read_text(encoding="utf-8") for p in held]
    for path, original in zip(held, originals, strict=True):
        path.write_text("# mutated\n", encoding="utf-8")
        mutate._hold(path, original)
    mutate._restore_in_flight()
    assert [p.read_text(encoding="utf-8") for p in held] == originals
    mutate._restore_in_flight()  # safe to call twice: the signal handler and the finally both do


def test_dropping_the_run_directory_removes_every_copy():
    """A crashed run leaves copies in a temp directory; a finished one leaves nothing at all."""
    mutate = _mutate()
    made = mutate.make_trees(2)
    where = mutate.run_dir()
    assert all(t.exists() for t in made)
    mutate.drop_run_dir()
    assert not where.exists()
    mutate.drop_run_dir()  # safe to call twice


# --- Choosing which mutants to run ---------------------------------------------------


def test_the_modules_flag_cannot_silently_select_nothing():
    """The failure mode this flag must not have: a green check that ran zero mutants.

    CI hands it whatever the diff printed, so every form the same file is written in has to select
    the same mutants. A form that selected nothing would pass, loudly green, having checked
    nothing — worse than the slow job it replaced.
    """
    mutate = _mutate()
    for module in sorted({m.file for m in mutate.CURATED}):
        expected = [m for m in mutate.CURATED if m.file == module]
        for form in (
            module,
            Path(module).name,
            f"app/{module}",
            f"code/backend/app/{module}",
            f"./code/backend/app/{module}",
            f"/home/someone/checkout/code/backend/app/{module}",
        ):
            selected, without = mutate.select_modules(mutate.CURATED, [form])
            assert selected == expected, f"{form!r} selected {len(selected)} mutants, not {len(expected)}"
            assert without == [], f"{form!r} was reported as having no mutants"


def test_a_module_with_no_mutants_is_named_rather_than_dropped():
    """Passing is right — but silence is not, so the caller gets the names back to print."""
    mutate = _mutate()
    selected, without = mutate.select_modules(mutate.CURATED, ["app/main.py", "code/frontend/src/api.ts"])
    assert selected == []
    assert without == ["app/main.py", "code/frontend/src/api.ts"]


def test_selecting_several_modules_keeps_the_curated_order_and_no_duplicates():
    """Two names for one module must not check it twice."""
    mutate = _mutate()
    once, _ = mutate.select_modules(mutate.CURATED, ["app/hive.py"])
    thrice, _ = mutate.select_modules(mutate.CURATED, ["hive.py", "app/hive.py", "code/backend/app/hive.py"])
    assert thrice == once
    both, _ = mutate.select_modules(mutate.CURATED, ["app/semantic.py", "app/hive.py"])
    assert both == [m for m in mutate.CURATED if m.file in ("hive.py", "semantic.py")]


def test_an_unfiltered_run_still_selects_every_curated_mutant():
    """main() passes CURATED straight through when no module is named; nothing may be lost."""
    mutate = _mutate()
    every = sorted({m.file for m in mutate.CURATED})
    selected, without = mutate.select_modules(mutate.CURATED, [f"app/{f}" for f in every])
    assert selected == mutate.CURATED
    assert without == []


def test_the_random_pass_is_scoped_too_and_does_not_fall_back_to_everything():
    """`--modules` plus `--random` must not quietly random-flip the modules the PR never touched."""
    mutate = _mutate()
    scoped = mutate.random_mutants(6, seed=1, targets=["semantic.py"])
    assert scoped, "semantic.py has flippable lines, so this should not be empty"
    assert {m.file for m in scoped} == {"semantic.py"}
    assert mutate.random_mutants(6, seed=1, targets=[]) == [], "no modules means no random flips"
    assert mutate.random_mutants(6, seed=1) != [], "no targets argument still means every target"


def test_an_empty_module_list_means_nothing_rather_than_everything():
    """The two things CI asks are different questions and must not collapse into one answer.

    No `--modules` at all is a push to main: every mutant. `--modules ""` is a pull request whose
    diff named no module with mutants: no mutant. Reading the second as the first would turn the
    fast path back into the slow one; reading the first as the second would leave main unchecked.
    """
    mutate = _mutate()
    ap = mutate.parser()
    assert ap.parse_args([]).modules is None
    assert ap.parse_args(["--modules", ""]).modules == ""


def test_an_empty_module_list_checks_nothing_and_still_passes():
    """Run for real, because this path returns before it copies anything: it has to be instant."""
    done = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "mutate.py"), "--modules", ""],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Nothing to check" in done.stdout
    assert "Curated mutants" not in done.stdout, "an empty list must not fall back to the full set"
    total = len(_mutate().CURATED)
    assert f"Mutants: 0 curated of {total}" in done.stdout, "and it has to say so, not pass in silence"


def test_the_mode_and_the_count_are_always_printed():
    """A green check that quietly ran zero mutants is worse than a slow one, so it says which."""
    done = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "mutate.py"), "--modules", "app/main.py"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=ROOT,
    )
    assert done.returncode == 0
    assert "Mode: only the modules named — app/main.py" in done.stdout
    assert "no mutants aimed at: app/main.py" in done.stdout


def test_a_skipped_mutant_is_not_counted_as_checked(trees, monkeypatch, capsys):
    """ "Checked 61" over 61 skips is the false all-clear the whole tool exists to avoid."""
    mutate = _mutate()
    drifted = mutate.Mutant("hive.py", "a pattern that no longer matches", "nowhere in the file", "x")
    result = mutate.check(drifted, trees[0])
    assert result.survived is None, "a mutant that was never applied neither lived nor died"
    assert "SKIP" in result.lines[0]
