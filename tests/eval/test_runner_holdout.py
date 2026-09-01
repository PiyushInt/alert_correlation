import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_holdout_scenario_refused_without_flag() -> None:
    """The runner must refuse a path under eval/holdout/ when --holdout is
    not passed, before it ever opens the scenario file or touches the
    estate. The path used here does not need to exist: the guard matches on
    the "eval/holdout/" prefix before any file I/O, so a nonexistent file
    exercises the refusal without ever running a real hold-out scenario.
    """
    fake_holdout_path = "eval/holdout/does_not_exist_for_test"

    captures_dir = REPO_ROOT / "eval" / "captures"
    before = set(captures_dir.iterdir())

    env = dict(os.environ)
    env["DATABASE_URL"] = "postgresql+psycopg://fake:fake@localhost:1/ace_db_eval"

    result = subprocess.run(
        [sys.executable, "eval/runner.py", "--scenario", fake_holdout_path],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    after = set(captures_dir.iterdir())

    assert result.returncode != 0
    assert "Refusing to run holdout scenario" in result.stderr
    assert before == after
