"""The evaluation a jury is told to run has to run: it is a script, so no other test would notice it dying."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]


def test_eval_search_runs_and_reports_precision(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in {"DATABASE_URL", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}}
    env["DUCKDB_PATH"] = str(tmp_path / "eval.duckdb")
    done = subprocess.run(
        [sys.executable, "tools/eval_search.py"], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180
    )
    assert done.returncode == 0, done.stderr[-800:]
    assert "precision at 1" in done.stdout
