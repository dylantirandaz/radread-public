"""Score against explicitly supplied private gold; this release contains no answer key."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import read_scoring

HERE = Path(__file__).resolve().parent


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
        help="Explicit externally supplied authorized gold.json; never distributed here",
    )
    parser.add_argument("--answers", type=Path, default=HERE / "answers.jsonl")
    parser.add_argument("--tasks", type=Path, default=HERE / "tasks.jsonl")
    parser.add_argument(
        "--output",
        type=Path,
        default=HERE / "results/score.json",
        help="Private local report; may reveal reference answers",
    )
    args = parser.parse_args()
    if args.gold is None or not args.gold.is_file():
        parser.exit(
            2,
            "Restricted scoring unavailable: supply --gold /authorized/private/gold.json. "
            "The public release withholds answers and cannot reproduce correctness scores alone. "
            "Task inference and collect_answers.py do not require gold.\n",
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
        gold = json.loads(args.gold.read_text(encoding="utf-8"))
        if not isinstance(gold, dict) or set(gold) != set(ids):
            raise ValueError(
                "Gold task IDs must match this task manifest exactly; do not mix benchmark cohorts"
            )
        answers = load_answers(args.answers)
        if set(answers) - set(ids):
            raise ValueError("Submission contains task IDs outside this cohort")
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
                # Use the private environment's scorer verbatim, not a public imitation.
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
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        OverflowError,
    ) as error:
        parser.exit(1, f"Scoring failed: {error}\n")


if __name__ == "__main__":
    main()
