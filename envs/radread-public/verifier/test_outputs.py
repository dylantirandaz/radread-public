# verifier/test_outputs.py — one pytest test per RadRead task; trial reward is the pass fraction.
import json
import os
import sys
from pathlib import Path

import pytest

WORKSPACE = Path(os.environ.get("RADREAD_WORKSPACE", "/root")).expanduser().resolve()
HERE = Path(__file__).resolve().parent

sys.path.insert(0, str(HERE))
import read_scoring

GOLD_PATH = (
    Path(os.environ.get("RADREAD_GOLD", str(HERE / "gold.json"))).expanduser().resolve()
)
if not GOLD_PATH.is_file():
    raise FileNotFoundError(
        f"Missing authorized gold at {GOLD_PATH}. Set RADREAD_GOLD to an authorized answer "
        "key mounted only for verification; the public bundle does not include it."
    )
GOLD = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
if not isinstance(GOLD, dict) or not GOLD:
    raise ValueError(
        f"authorized gold at {GOLD_PATH} must be a nonempty task-ID mapping"
    )
ANSWERS_FILE = WORKSPACE / "answers.jsonl"


def load_answers() -> dict:
    """task_id -> completion string. Raises informative errors the tests surface."""
    if not ANSWERS_FILE.exists():
        raise FileNotFoundError(f"answers file not found at {ANSWERS_FILE}")
    out = {}
    for lineno, line in enumerate(
        ANSWERS_FILE.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"line {lineno} is not valid JSON: {e}")
        if "task_id" not in row or "completion" not in row:
            raise ValueError(f"line {lineno} needs task_id and completion keys")
        out[row["task_id"]] = row["completion"]
    return out


class TestSubmissionPresent:
    def test_file_exists(self):
        assert ANSWERS_FILE.exists(), f"Answer file not found at {ANSWERS_FILE}"

    def test_file_is_valid_jsonl(self):
        try:
            load_answers()
        except (ValueError, FileNotFoundError) as e:
            pytest.fail(str(e))


@pytest.mark.parametrize("task_id", sorted(GOLD))
class TestTask:
    def test_task_passes(self, task_id):
        try:
            answers = load_answers()
        except (ValueError, FileNotFoundError) as e:
            pytest.fail(f"submission unreadable: {e}")
        if task_id not in answers:
            pytest.fail(f"no answer submitted for {task_id}")
        report = read_scoring.grade({"gold": GOLD[task_id]}, answers[task_id])
        if not report["pass_"]:
            failed = "; ".join(
                f"{c['check']}: {c['observed']}"
                for c in report["checks"]
                if not c["passed"]
            )
            pytest.fail(f"{task_id} failed: {failed}")
