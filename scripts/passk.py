"""Aggregate RadRead rollout results into pass@k leaderboard data.

Reads the ``results.jsonl`` files written by ``prime eval run`` (one directory per model),
re-grades every transcript against authorized gold with the bundle's own grader,
groups rollouts by task, and reports the unbiased pass@k estimator

    pass@k = 1 - C(n - c, k) / C(n, k)

for a task answered correctly in ``c`` of ``n`` rollouts (Chen et al., 2021, HumanEval). With
n = k the estimator is exactly "solved at least once in n attempts".

Re-grading means a gold correction never needs a paid re-run: the transcripts are the record,
the gold is the policy, and the leaderboard is always their product. The reward saved at eval
time is kept on each record as ``saved_reward`` for the audit to compare against.

usage: python scripts/passk.py results/full --out results/leaderboard.json
       python scripts/passk.py results/full --gold /authorized/gold.json --env-root envs/radread-public
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import random
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from types import ModuleType
from typing import Any, TypedDict

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "envs" / "radread-public"

# Historical $ per 1M tokens on Prime Inference at reference measurement time, not current quotes.
PRICING = {
    "google/gemini-3.8-flash": (0.75, 3.75),
    "anthropic/claude-opus-5": (5.0, 25.0),
    "anthropic/claude-fable-5.1": (10.0, 50.0),
    "openai/gpt-6-astra": (10.0, 50.0),
    "openai/gpt-5.6-sol": (5.0, 30.0),
}

DISPLAY = {
    "google/gemini-3.8-flash": "Gemini 3.8 Flash",
    "anthropic/claude-opus-5": "Claude Opus 5",
    "anthropic/claude-fable-5.1": "Claude Fable 5.1",
    "openai/gpt-6-astra": "GPT-6 Astra",
    "openai/gpt-5.6-sol": "GPT-5.6 Sol",
}

LAB = {"openai": "OpenAI", "anthropic": "Anthropic", "google": "Google"}


def load_grader(bundle: Path | None = None) -> ModuleType:
    """The bundle's own deterministic grader, imported by path — one scoring implementation."""
    bundle = (
        Path(bundle)
        if bundle is not None
        else Path(os.environ.get("RADREAD_PUBLIC_ROOT") or BUNDLE)
    )
    path = bundle / "verifier" / "read_scoring.py"
    spec = importlib.util.spec_from_file_location("read_scoring", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import grader from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_gold(
    bundle: Path | None = None, gold_path: str | Path | None = None
) -> dict[str, Any]:
    """Load authorized gold: explicit path, RADREAD_GOLD, then the private bundle key."""
    bundle = (
        Path(bundle)
        if bundle is not None
        else Path(os.environ.get("RADREAD_PUBLIC_ROOT") or BUNDLE)
    )
    configured = (
        gold_path if gold_path is not None else os.environ.get("RADREAD_GOLD") or None
    )
    path = (
        Path(configured).expanduser()
        if configured is not None
        else bundle / "verifier" / "gold.json"
    )
    if not path.is_file():
        raise FileNotFoundError(
            f"Authorized scoring gold not found: {path}. "
            "Supply --gold /authorized/gold.json or set RADREAD_GOLD; "
            "gold is not included in the public bundle."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def completion_text(record: dict[str, Any]) -> str:
    completion = record.get("completion") or []
    if isinstance(completion, str):
        return completion
    return "".join(str(message.get("content") or "") for message in completion)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k for a task solved in c of n rollouts."""
    if n < k:
        raise ValueError(f"pass@{k} needs at least {k} rollouts, got {n}")
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


@dataclass
class TaskGroup:
    task_id: str
    source: str
    rewards: list[float] = field(default_factory=list)
    checks: list[float] = field(default_factory=list)
    parsed: list[float] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def n(self) -> int:
        return len(self.rewards)

    @property
    def c(self) -> int:
        return sum(1 for r in self.rewards if r >= 1.0)


def choose_runs(directory: Path) -> list[Path]:
    """Select the primary run and allowed repair or extension runs for one model.

    A sibling ``<results_dir>.runs.json`` freezes published experiments: each model directory
    maps to ordered relative run paths (primary first, then repairs and cohort extensions).
    Missing pinned data is an error, never permission to substitute another run. Unpublished
    experiments without a manifest use the largest run, breaking ties by recency.
    """
    manifest = directory.parent.with_name(directory.parent.name + ".runs.json")
    if manifest.is_file():
        selection = json.loads(manifest.read_text(encoding="utf-8"))
        names = selection.get(directory.name)
        if not names:
            raise RuntimeError(f"no pinned runs for {directory.name} in {manifest}")
        selected = [directory / name for name in names]
        for run in selected:
            if not (run / "results.jsonl").is_file():
                raise RuntimeError(f"pinned run missing results.jsonl: {run}")
        print(
            f"{directory.name}: pinned primary {selected[0].name}, {len(selected) - 1} repair/extension run(s)"
        )
        return selected

    runs = {file.parent for file in directory.rglob("results.jsonl")}
    if not runs:
        raise FileNotFoundError(f"no results.jsonl under {directory}")

    def rank(run: Path) -> tuple[int, float]:
        path = run / "results.jsonl"
        rows = sum(
            1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
        return rows, path.stat().st_mtime

    chosen = max(runs, key=rank)
    if len(runs) > 1:
        print(
            f"{directory.name}: {len(runs)} runs present, using {chosen.name} ({rank(chosen)[0]} rollouts)"
        )
    repairs = sorted(
        runs - {chosen}, key=lambda run: (run / "results.jsonl").stat().st_mtime
    )
    return [chosen, *repairs]


def scored_records(
    directory: Path,
    max_k: int,
    grader: ModuleType | None = None,
    gold: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Score a model's primary rollouts, then ordered repair and cohort extension runs.

    A rollout lost to a provider error leaves its task with fewer than ``max_k`` scores. Later
    runs fill those gaps and introduce new task IDs even when every primary task is complete.
    All runs, including the primary, contribute only the first ``max_k`` provider-successful
    rollouts per task in run and file order. Later successes never replace earlier failures.
    Rollouts that errored are never scored; invalid or failed model replies still count.

    Every record is re-graded against the current gold. On return each record carries
    ``report`` (the grader's full verdict), ``reward`` (1.0 / 0.0 from that verdict),
    ``checks_accuracy``, ``reply_parsed`` and ``saved_reward`` (what the eval run wrote).
    """
    grader = grader or load_grader()
    gold = gold or load_gold()
    runs = choose_runs(directory)
    primary = runs[0]
    model = ""
    records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    def take(run: Path) -> None:
        nonlocal model
        meta = run / "metadata.json"
        if meta.is_file():
            model = json.loads(meta.read_text(encoding="utf-8")).get("model", model)
        for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            task_id = (row.get("info") or {}).get("task_id")
            if task_id is None or row.get("error"):
                continue
            if counts.get(task_id, 0) >= max_k:
                continue
            counts[task_id] = counts.get(task_id, 0) + 1
            report = grader.grade({"gold": gold[task_id]}, completion_text(row))
            row["saved_reward"] = float(row.get("reward") or 0.0)
            row["report"] = report
            row["reward"] = 1.0 if report["pass_"] else 0.0
            row["checks_accuracy"] = report["checks_passed"] / (
                report["checks_total"] or 1
            )
            row["reply_parsed"] = (
                0.0
                if any(c["check"] == "valid_json" for c in report["checks"])
                else 1.0
            )
            records.append(row)

    take(primary)
    short = {t for t, n in counts.items() if n < max_k}
    for run in runs[1:]:
        take(run)
    repaired = short - {t for t, n in counts.items() if n < max_k}
    if repaired:
        print(f"{directory.name}: repaired {len(repaired)} task(s) from later runs")
    return model or directory.name.replace("-", "/", 1), records


def load_model_dir(
    directory: Path,
    max_k: int,
    grader: ModuleType | None = None,
    gold: dict[str, Any] | None = None,
) -> tuple[str, dict[str, TaskGroup]]:
    """Load one model's re-graded rollouts, keyed by task id."""
    model, records = scored_records(directory, max_k, grader, gold)
    groups: dict[str, TaskGroup] = {}
    for row in records:
        info = row["info"]
        task_id = info["task_id"]
        group = groups.setdefault(
            task_id, TaskGroup(task_id, info.get("source", "other"))
        )
        group.rewards.append(row["reward"])
        group.checks.append(row["checks_accuracy"])
        group.parsed.append(row["reply_parsed"])
        usage = row.get("token_usage") or {}
        group.input_tokens += int(usage.get("input_tokens") or 0)
        group.output_tokens += int(usage.get("output_tokens") or 0)
    return model, groups


def summarize(model: str, groups: dict[str, TaskGroup], max_k: int) -> dict[str, Any]:
    """Per-model pass@1..max_k, per-source pass@k, cost and reliability counters."""
    usable = [g for g in groups.values() if g.n >= max_k]
    if not usable:
        raise ValueError(f"{model}: no task has {max_k} scored rollouts")
    n_tasks = len(usable)
    curve = {
        f"pass@{k}": sum(pass_at_k(g.n, g.c, k) for g in usable) / n_tasks
        for k in range(1, max_k + 1)
    }
    by_source: dict[str, dict[str, Any]] = {}
    for source in sorted({g.source for g in usable}):
        rows = [g for g in usable if g.source == source]
        by_source[source] = {
            "tasks": len(rows),
            "pass@1": sum(pass_at_k(g.n, g.c, 1) for g in rows) / len(rows),
            f"pass@{max_k}": sum(pass_at_k(g.n, g.c, max_k) for g in rows) / len(rows),
        }
    rollouts = sum(g.n for g in usable)
    input_tokens = sum(g.input_tokens for g in usable)
    output_tokens = sum(g.output_tokens for g in usable)
    price_in, price_out = PRICING.get(model, (0.0, 0.0))
    provider = model.split("/")[0]
    return {
        "model": model,
        "name": DISPLAY.get(model, model.split("/")[-1]),
        "lab": LAB.get(provider, provider),
        "tasks": n_tasks,
        "rollouts": rollouts,
        **curve,
        "solved_any": sum(1 for g in usable if g.c > 0),
        "solved_all": sum(1 for g in usable if g.c == g.n),
        "unsolved": sum(1 for g in usable if g.c == 0),
        "attempts_correct": {
            str(c): sum(1 for g in usable if g.c == c) for c in range(max_k + 1)
        },
        "checks_accuracy": sum(sum(g.checks) for g in usable) / rollouts,
        "parse_rate": sum(sum(g.parsed) for g in usable) / rollouts,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "output_tokens_per_rollout": output_tokens / rollouts,
        "cost_usd": (input_tokens * price_in + output_tokens * price_out) / 1e6,
        "by_source": by_source,
    }


class Pass1Comparison(TypedDict):
    model_a: str
    model_b: str
    difference: float
    ci95: list[float]


BootstrapUncertainty = TypedDict(
    "BootstrapUncertainty",
    {
        "method": str,
        "confidence_level": float,
        "resamples": int,
        "seed": int,
        "studies": int,
        "scope": str,
        "pass@1_comparisons": list[Pass1Comparison],
    },
)


def _percentile_interval(samples: list[float]) -> list[float]:
    """Return the central 95% interval using linearly interpolated percentiles."""
    samples.sort()
    bounds = []
    for quantile in (0.025, 0.975):
        index = (len(samples) - 1) * quantile
        lower, upper = math.floor(index), math.ceil(index)
        bounds.append(
            samples[lower] + (samples[upper] - samples[lower]) * (index - lower)
        )
    return bounds


def paired_bootstrap(
    model_groups: dict[str, dict[str, TaskGroup]],
    max_k: int,
    resamples: int = 10000,
    seed: int = 42,
) -> tuple[dict[str, list[float]], BootstrapUncertainty]:
    """Bootstrap aligned study c/n rates with shared draws across every model.

    Only studies eligible for the existing pass@k summaries participate. Different
    eligible study sets are an error, never intersected or independently sampled.
    """
    if resamples < 1:
        raise ValueError("bootstrap resamples must be positive")
    eligible = {
        model: {task_id: group for task_id, group in groups.items() if group.n >= max_k}
        for model, groups in model_groups.items()
    }
    model_ids = list(eligible)
    task_ids = sorted(eligible[model_ids[0]]) if model_ids else []
    reference_ids = set(task_ids)
    for model, groups in eligible.items():
        if set(groups) != reference_ids:
            missing = sorted(reference_ids - groups.keys())
            extra = sorted(groups.keys() - reference_ids)
            raise ValueError(
                f"{model}: incompatible eligible study set relative to {model_ids[0]}; "
                f"missing={missing}, extra={extra}"
            )
        if not groups:
            raise ValueError(f"{model}: no task has {max_k} scored rollouts")
    studies = len(task_ids)
    uncertainty: BootstrapUncertainty = {
        "method": "paired percentile study bootstrap",
        "confidence_level": 0.95,
        "resamples": resamples,
        "seed": seed,
        "studies": studies,
        "scope": (
            "Descriptive intervals conditional on this outcome-selected challenge cohort "
            "and its saved responses, not an independent holdout or population/clinical "
            "validation. Studies, not individual attempts, are resampled. Intervals do "
            "not account for cohort selection, gold-label uncertainty, or future responses; "
            "pairwise intervals are not adjusted for multiple comparisons."
        ),
        "pass@1_comparisons": [],
    }
    if not model_ids:
        return {}, uncertainty

    rates = [
        [groups[task_id].c / groups[task_id].n for task_id in task_ids]
        for groups in eligible.values()
    ]
    samples: list[list[float]] = [[] for _ in model_ids]
    rng = random.Random(seed)
    for _ in range(resamples):
        draw = [rng.randrange(studies) for _ in range(studies)]
        for values, model_samples in zip(rates, samples):
            model_samples.append(math.fsum(values[index] for index in draw) / studies)

    # Preserve the shared draw order until every paired contrast has been computed.
    for a, model_a in enumerate(model_ids):
        for b in range(a + 1, len(model_ids)):
            uncertainty["pass@1_comparisons"].append(
                {
                    "model_a": model_a,
                    "model_b": model_ids[b],
                    "difference": math.fsum(x - y for x, y in zip(rates[a], rates[b]))
                    / studies,
                    "ci95": _percentile_interval(
                        [x - y for x, y in zip(samples[a], samples[b])]
                    ),
                }
            )
    intervals = {
        model: _percentile_interval(model_samples)
        for model, model_samples in zip(model_ids, samples)
    }
    return intervals, uncertainty


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "results_dir", type=Path, help="directory holding one subdir per model"
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / "results" / "leaderboard.json"
    )
    parser.add_argument("--max-k", type=int, default=5)
    parser.add_argument(
        "--bootstrap-resamples",
        type=int,
        default=10000,
        help="shared study-bootstrap draws for 95%% pass@1 intervals (default: 10000)",
    )
    parser.add_argument(
        "--bootstrap-seed",
        type=int,
        default=42,
        help="study-bootstrap random seed (default: 42)",
    )
    parser.add_argument(
        "--env-root",
        type=Path,
        default=Path(os.environ.get("RADREAD_PUBLIC_ROOT") or BUNDLE),
        help="bundle containing verifier/read_scoring.py (default: RADREAD_PUBLIC_ROOT or repository bundle)",
    )
    parser.add_argument(
        "--gold",
        type=Path,
        help="authorized gold JSON (overrides RADREAD_GOLD and bundle/verifier/gold.json)",
    )
    args = parser.parse_args()

    grader, gold = load_grader(args.env_root), load_gold(args.env_root, args.gold)
    models: list[dict[str, Any]] = []
    model_groups: dict[str, dict[str, TaskGroup]] = {}
    task_solvers: dict[str, set[str]] = {}
    task_source: dict[str, str] = {}
    for directory in sorted(p for p in args.results_dir.iterdir() if p.is_dir()):
        try:
            model, groups = load_model_dir(directory, args.max_k, grader, gold)
        except (FileNotFoundError, ValueError) as exc:
            print(f"skip {directory.name}: {exc}")
            continue
        models.append(summarize(model, groups, args.max_k))
        model_groups[model] = groups
        for task_id, group in groups.items():
            task_source[task_id] = group.source
            task_solvers.setdefault(task_id, set())
            if group.c > 0:
                task_solvers[task_id].add(model)

    intervals, uncertainty = paired_bootstrap(
        model_groups, args.max_k, args.bootstrap_resamples, args.bootstrap_seed
    )
    for row in models:
        row["pass@1_ci95"] = intervals[row["model"]]
    # Exact c/n arithmetic keeps mathematically equal scores in their original order.
    pass1_order = {
        model: sum(
            (
                Fraction(group.c, group.n)
                for group in groups.values()
                if group.n >= args.max_k
            ),
            Fraction(),
        )
        / uncertainty["studies"]
        for model, groups in model_groups.items()
    }
    models.sort(key=lambda row: pass1_order[row["model"]], reverse=True)
    frontier_unsolved = sorted(t for t, solvers in task_solvers.items() if not solvers)
    payload = {
        "benchmark": "RadRead-Public",
        "tasks": max((m["tasks"] for m in models), default=0),
        "rollouts_per_task": args.max_k,
        "protocol": {
            "temperature": 0,
            "max_tokens": 65536,
            "reasoning_effort": "xhigh (OpenAI and Claude); high (Gemini)",
            "provider": "Prime Intellect Inference (api.pinference.ai)",
            "scoring": "deterministic grader, all-or-nothing per task, no judge model",
        },
        "models": models,
        "uncertainty": uncertainty,
        "unsolved_by_all": {
            "count": len(frontier_unsolved),
            "by_source": {
                source: sum(1 for t in frontier_unsolved if task_source[t] == source)
                for source in sorted({task_source[t] for t in frontier_unsolved})
            },
            "task_ids": frontier_unsolved,
        },
        "total_cost_usd": sum(m["cost_usd"] for m in models),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    width = max((len(m["name"]) for m in models), default=10)
    header = f"{'model':<{width}} " + " ".join(
        f"pass@{k}" for k in range(1, args.max_k + 1)
    )
    print(header + "  solved  unsolved  $")
    print("Models ordered by pass@1; equal scores retain their original order.")
    print(
        "Costs use historical reference-run Prime Inference prices, not current quotes."
    )
    for m in models:
        cells = " ".join(f"{m[f'pass@{k}']*100:6.1f}" for k in range(1, args.max_k + 1))
        print(
            f"{m['name']:<{width}} {cells}  {m['solved_any']:>6}  {m['unsolved']:>8}  {m['cost_usd']:.2f}"
        )
    print(f"\nunsolved by every model: {len(frontier_unsolved)} / {payload['tasks']}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
