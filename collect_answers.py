"""Collect one actual completion JSON file per task into the benchmark's answers.jsonl."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEXT_STEPS = {"emergency_action", "urgent_review", "routine_followup", "none"}


def valid_finding(value: object) -> bool:
    """Accept the documented scalar, single-box, and box-list finding shapes."""
    if isinstance(value, (bool, str)):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(value)
    if not isinstance(value, list):
        return False

    def box(item: object) -> bool:
        return (
            isinstance(item, list)
            and len(item) == 4
            and all(
                isinstance(v, (int, float))
                and not isinstance(v, bool)
                and math.isfinite(v)
                for v in item
            )
        )

    return box(value) or all(box(item) for item in value)


def check_completion(payload: object) -> None:
    """Check submission shape only, without estimating correctness or accessing answers."""
    required = {"findings", "diagnosis", "next_step", "impression"}
    if not isinstance(payload, dict) or set(payload) != required:
        raise ValueError(
            f"Completion must be an object with exactly {sorted(required)}"
        )
    if not isinstance(payload["findings"], dict) or not all(
        valid_finding(v) for v in payload["findings"].values()
    ):
        raise ValueError(
            "findings must map checklist keys to booleans, strings, finite numbers, boxes, or box lists"
        )
    for key in ("diagnosis", "next_step", "impression"):
        if not isinstance(payload[key], str):
            raise TypeError(f"{key} must be a string")
    if payload["next_step"] not in NEXT_STEPS:
        raise ValueError(
            "next_step must be emergency_action, urgent_review, routine_followup, or none"
        )


def main() -> None:
    """Collect task-ID-named JSON files without fabricating missing completions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--completions",
        type=Path,
        required=True,
        help="Directory containing <task_id>.json from your reader/model",
    )
    parser.add_argument("--tasks", type=Path, default=HERE / "tasks.jsonl")
    parser.add_argument("--answers", type=Path, default=HERE / "answers.jsonl")
    args = parser.parse_args()
    try:
        tasks = [
            json.loads(line)
            for line in args.tasks.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not tasks:
            raise ValueError("Task manifest is empty")
        rows = []
        seen = set()
        for task in tasks:
            task_id = task["task_id"]
            if (
                not isinstance(task_id, str)
                or not task_id
                or any(
                    c
                    not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                    for c in task_id
                )
            ):
                raise ValueError("Unsafe task ID in manifest")
            if task_id in seen:
                raise ValueError(f"Duplicate task ID: {task_id}")
            seen.add(task_id)
            path = args.completions / f"{task_id}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            try:
                check_completion(payload)
            except (ValueError, TypeError) as error:
                raise ValueError(f"{path}: {error}") from error
            rows.append(
                {
                    "task_id": task_id,
                    "completion": json.dumps(
                        payload, ensure_ascii=False, allow_nan=False
                    ),
                }
            )
        # Refuse to replace a previous submission and write only after all files pass.
        with args.answers.open("x", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(
            f"Collected {len(rows)} actual completions into {args.answers}; structure checked, NOT scored."
        )
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as error:
        parser.exit(1, f"Cannot collect submission: {error}\n")


if __name__ == "__main__":
    main()
