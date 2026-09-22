"""Score with an authorized private gold key; the public release contains no answer key."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "envs" / "radread-public"


def load_grader() -> ModuleType:
    """Import the bundle's deterministic grader without model or verifier dependencies."""
    path = BUNDLE / "verifier" / "read_scoring.py"
    spec = importlib.util.spec_from_file_location("read_scoring", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import the benchmark grader from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_answers(path: Path) -> dict[str, str]:
    """Read the existing task_id/completion-string interface, rejecting duplicate IDs."""
    answers = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("task_id"), str)
            or not isinstance(row.get("completion"), str)
        ):
            raise TypeError(f"{path}:{number}: expected task_id and completion strings")
        if row["task_id"] in answers:
            raise ValueError(f"{path}:{number}: duplicate task_id {row['task_id']}")
        answers[row["task_id"]] = row["completion"]
    return answers


def main() -> None:
    """Run the unchanged benchmark grader and report task pass fraction."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--gold",
        type=Path,
        help="Authorized gold.json; overrides RADREAD_GOLD and bundle/verifier/gold.json",
    )
    parser.add_argument("--answers", type=Path, default=ROOT / "answers.jsonl")
    parser.add_argument(
        "--tasks", type=Path, default=BUNDLE / "environment" / "tasks.jsonl"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "results" / "score.json",
        help="Private local report; may reveal reference answers",
    )
    args = parser.parse_args()
    gold_path = args.gold
    if gold_path is None:
        configured_gold = os.environ.get("RADREAD_GOLD")
        gold_path = (
            Path(configured_gold)
            if configured_gold
            else BUNDLE / "verifier" / "gold.json"
        )
    if not gold_path.is_file():
        parser.exit(
            2,
            f"Restricted scoring unavailable: gold file not found: {gold_path}. "
            "Supply --gold /authorized/private/gold.json or set RADREAD_GOLD. "
            "The public release withholds answers and cannot reproduce correctness scores alone. "
            "Task inference and scripts/collect_answers.py do not require gold.\n",
        )
    try:
        tasks = [
            json.loads(line)
            for line in args.tasks.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        ids = [task["task_id"] for task in tasks]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("Tasks must be nonempty with unique task IDs")
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        if not isinstance(gold, dict) or set(gold) != set(ids):
            raise ValueError(
                "Gold task IDs must match this task manifest exactly; do not mix benchmark cohorts"
            )
        answers = load_answers(args.answers)
        if set(answers) - set(ids):
            raise ValueError("Submission contains task IDs outside this cohort")
        read_scoring = load_grader()
        reports = []
        for task_id in ids:
            if task_id not in answers:
                report = {
                    "pass_": False,
                    "checks": [
                        {
                            "check": "submission_present",
                            "passed": False,
                            "observed": "Missing task",
                        }
                    ],
                    "checks_passed": 0,
                    "checks_total": 1,
                }
            else:
                # Use the single canonical grader, not a public imitation.
                report = read_scoring.grade({"gold": gold[task_id]}, answers[task_id])
            reports.append({"task_id": task_id, **report})
        passed = sum(bool(report["pass_"]) for report in reports)
        summary = {
            "reward": passed / len(ids),
            "passed": passed,
            "total": len(ids),
            "tasks": reports,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        print(f"reward {summary['reward']:.6f} ({passed}/{len(ids)})")
        print(
            f"Private report: {args.output}; do not publish reference-bearing checks."
        )
    except (
        OSError,
        ImportError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        OverflowError,
    ) as error:
        parser.exit(1, f"Scoring failed: {error}\n")


if __name__ == "__main__":
    main()
