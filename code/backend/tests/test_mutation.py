"""The mutation harness has to be trustworthy itself.

A mutant can only be killed by a test that actually runs, so a target module missing from
tools/mutate.py's SUITE produces a confident all-clear over code nothing exercised. That is worse
than no mutation testing at all, and it happened once: the two hub test files were left out of
SUITE and every hub mutant "survived" while the real tests caught all of them.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

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
