"""Regression coverage for reproducible rollout selection."""

import json
from pathlib import Path

import pytest

from scripts.passk import (
    TaskGroup,
    load_gold,
    load_grader,
    main,
    paired_bootstrap,
    pass_at_k,
    scored_records,
)


def _write_run(path: Path, answers: list[bool]) -> None:
    path.mkdir(parents=True)
    rows = []
    for answer in answers:
        reply = {
            "findings": {"present": answer},
            "diagnosis": "nodule",
            "next_step": "none",
        }
        rows.append(
            {
                "info": {"task_id": "study"},
                "completion": [{"content": json.dumps(reply)}],
            }
        )
    (path / "results.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_published_estimate_ignores_unselected_later_run(tmp_path: Path) -> None:
    """A later run must not replace published answers or supply their repair attempts."""
    directory = tmp_path / "full" / "provider-model"
    _write_run(directory / "published", [False])
    _write_run(directory / "repair", [True])
    _write_run(directory / "late", [True, True, True])
    (tmp_path / "full.runs.json").write_text(
        json.dumps({"provider-model": ["published", "repair"]})
    )
    gold = {
        "study": {
            "critical_findings": {"present": True},
            "diagnosis_accepted": ["nodule"],
            "next_step_accepted": ["none"],
        }
    }

    _, records = scored_records(directory, 2, load_grader(), gold)

    assert len(records) == 2
    correct = sum(record["reward"] == 1 for record in records)
    assert pass_at_k(2, correct, 1) == 0.5
    assert pass_at_k(2, correct, 2) == 1.0


@pytest.mark.parametrize(
    ("options", "attempts", "solved"),
    [(["--max-k", "4"], 4, False), (["--max-k", "5"], 5, True)],
)
def test_primary_attempt_cap_preserves_failures_in_file_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    options: list[str],
    attempts: int,
    solved: bool,
) -> None:
    """A fifth-attempt success cannot improve a first-four-attempt leaderboard."""
    directory = tmp_path / "full" / "provider-model"
    _write_run(directory / "published", [False, False, False, False, True])
    _write_run(directory / "repair", [True] * 5)
    (tmp_path / "full.runs.json").write_text(
        json.dumps({"provider-model": ["published", "repair"]})
    )
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(
        json.dumps(
            {
                "study": {
                    "critical_findings": {"present": True},
                    "diagnosis_accepted": ["nodule"],
                    "next_step_accepted": ["none"],
                }
            }
        )
    )
    output = tmp_path / "leaderboard.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "passk.py",
            str(directory.parent),
            "--gold",
            str(gold_path),
            "--out",
            str(output),
            *options,
        ],
    )

    main()

    board = json.loads(output.read_text(encoding="utf-8"))
    model = board["models"][0]
    assert board["rollouts_per_task"] == attempts
    assert model["rollouts"] == attempts
    assert model["pass@1"] == pytest.approx(1 / attempts if solved else 0.0)
    assert model[f"pass@{attempts}"] == float(solved)
    assert model["unsolved"] == int(not solved)
    assert model["solved_all"] == 0
    assert model["attempts_correct"] == {
        str(count): int(count == int(solved)) for count in range(attempts + 1)
    }
    assert board["unsolved_by_all"]["task_ids"] == ([] if solved else ["study"])


def test_provider_errors_do_not_consume_attempts_but_invalid_replies_do(
    tmp_path: Path,
) -> None:
    """Repairs fill provider gaps without discarding legitimate failed model replies."""
    directory = tmp_path / "full" / "provider-model"
    _write_run(directory / "published", [False, True, False])
    primary = directory / "published" / "results.jsonl"
    rows = [json.loads(line) for line in primary.read_text().splitlines()]
    rows[1]["error"] = {"message": "provider unavailable"}
    rows[2]["completion"] = [{"content": "not a JSON read"}]
    primary.write_text("".join(json.dumps(row) + "\n" for row in rows))
    _write_run(directory / "first-repair", [False])
    _write_run(directory / "second-repair", [True, False, False])
    (tmp_path / "full.runs.json").write_text(
        json.dumps({"provider-model": ["published", "first-repair", "second-repair"]})
    )
    gold = {
        "study": {
            "critical_findings": {"present": True},
            "diagnosis_accepted": ["nodule"],
            "next_step_accepted": ["none"],
        }
    }

    _, records = scored_records(directory, 4, load_grader(), gold)

    assert [record["reward"] for record in records] == [0.0, 0.0, 0.0, 1.0]
    assert records[1]["reply_parsed"] == 0.0


def test_complete_primary_keeps_original_attempts_and_adds_pinned_extension(
    tmp_path: Path,
) -> None:
    """A pinned extension adds new tasks without replacing completed primary attempts."""
    directory = tmp_path / "full" / "provider-model"
    primary_ids = [f"old_{index}" for index in range(243)]
    extension_ids = [f"new_{index}" for index in range(57)]
    for name, task_ids, present, attempts in (
        ("published", primary_ids, False, 5),
        ("extension", primary_ids + extension_ids, True, 6),
    ):
        run = directory / name
        run.mkdir(parents=True)
        reply = {
            "findings": {"present": present},
            "diagnosis": "nodule",
            "next_step": "none",
        }
        rows = [
            {
                "info": {"task_id": task_id},
                "completion": [{"content": json.dumps(reply)}],
            }
            for task_id in task_ids
            for _ in range(attempts)
        ]
        (run / "results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
    (tmp_path / "full.runs.json").write_text(
        json.dumps({"provider-model": ["published", "extension"]}), encoding="utf-8"
    )
    gold = {
        task_id: {
            "critical_findings": {"present": True},
            "diagnosis_accepted": ["nodule"],
            "next_step_accepted": ["none"],
        }
        for task_id in primary_ids + extension_ids
    }

    _, records = scored_records(directory, 4, load_grader(), gold)

    rewards: dict[str, list[float]] = {}
    for record in records:
        rewards.setdefault(record["info"]["task_id"], []).append(record["reward"])
    assert rewards == {
        **{task_id: [0.0] * 4 for task_id in primary_ids},
        **{task_id: [1.0] * 4 for task_id in extension_ids},
    }


def test_missing_published_run_does_not_fall_back(tmp_path: Path) -> None:
    """Missing frozen data must fail rather than quietly score a different run."""
    directory = tmp_path / "full" / "provider-model"
    _write_run(directory / "late", [True])
    (tmp_path / "full.runs.json").write_text(
        json.dumps({"provider-model": ["missing"]})
    )
    gold = {
        "study": {
            "critical_findings": {"present": True},
            "diagnosis_accepted": ["nodule"],
            "next_step_accepted": ["none"],
        }
    }
    with pytest.raises(RuntimeError, match="pinned run"):
        scored_records(directory, 1, gold=gold)


def test_external_gold_overrides_bundle_and_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regrading must honor an explicit authorized key, not a stale embedded key."""
    bundle = tmp_path / "bundle"
    (bundle / "verifier").mkdir(parents=True)
    embedded = bundle / "verifier" / "gold.json"
    configured = tmp_path / "configured.json"
    explicit = tmp_path / "explicit.json"
    for path, present in ((embedded, False), (configured, False), (explicit, True)):
        path.write_text(
            json.dumps(
                {
                    "study": {
                        "critical_findings": {"present": present},
                        "diagnosis_accepted": ["nodule"],
                        "next_step_accepted": ["none"],
                    }
                }
            ),
            encoding="utf-8",
        )
    monkeypatch.setenv("RADREAD_GOLD", str(configured))
    directory = tmp_path / "runs" / "provider-model"
    _write_run(directory / "primary", [True])

    _, records = scored_records(
        directory, 1, load_grader(), load_gold(bundle, gold_path=explicit)
    )
    assert records[0]["reward"] == 1.0
    embedded.unlink()
    assert load_gold(bundle)["study"]["critical_findings"]["present"] is False
    monkeypatch.delenv("RADREAD_GOLD")
    with pytest.raises(FileNotFoundError, match="RADREAD_GOLD"):
        load_gold(bundle)


def test_missing_explicit_gold_never_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A mistyped explicit key must not quietly grade with a different authorized key."""
    configured = tmp_path / "configured.json"
    configured.write_text(json.dumps({"study": {}}), encoding="utf-8")
    monkeypatch.setenv("RADREAD_GOLD", str(configured))
    with pytest.raises(FileNotFoundError, match="missing.json"):
        load_gold(tmp_path, gold_path=tmp_path / "missing.json")


def _groups(counts: dict[str, tuple[int, int]]) -> dict[str, TaskGroup]:
    return {
        task_id: TaskGroup(
            task_id, "synthetic", rewards=[1.0] * correct + [0.0] * (attempts - correct)
        )
        for task_id, (correct, attempts) in counts.items()
    }


def test_bootstrap_pairs_studies_by_id_not_input_order() -> None:
    """Identical study outcomes have no paired uncertainty, despite broad marginal CIs."""
    groups = {
        "provider/a": _groups({"failed": (0, 5), "solved": (5, 5)}),
        "provider/b": _groups({"solved": (5, 5), "failed": (0, 5)}),
    }
    intervals, uncertainty = paired_bootstrap(groups, 5, resamples=200, seed=7)

    assert intervals["provider/a"] == intervals["provider/b"] == [0.0, 1.0]
    contrast = uncertainty["pass@1_comparisons"][0]
    assert contrast["difference"] == 0.0
    assert contrast["ci95"] == [0.0, 0.0]
    assert paired_bootstrap(groups, 5, resamples=200, seed=7) == (
        intervals,
        uncertainty,
    )


@pytest.mark.parametrize(
    "other",
    [
        {"different": (1, 5), "shared": (3, 5)},
        {"study": (1, 4), "shared": (3, 5)},
    ],
)
def test_bootstrap_rejects_incompatible_eligible_study_sets(
    other: dict[str, tuple[int, int]],
) -> None:
    """Neither matching cohort sizes nor an incomplete study permit unpaired comparisons."""
    with pytest.raises(ValueError, match="provider/b"):
        paired_bootstrap(
            {
                "provider/a": _groups({"study": (1, 5), "shared": (3, 5)}),
                "provider/b": _groups(other),
            },
            5,
            resamples=20,
        )


def test_bootstrap_single_model_resamples_studies_not_attempts() -> None:
    """One study supplies no between-study variation even when its attempts vary."""
    intervals, uncertainty = paired_bootstrap(
        {"provider/a": _groups({"study": (2, 5)})}, 5, resamples=20
    )

    assert intervals["provider/a"] == [0.4, 0.4]
    assert uncertainty["pass@1_comparisons"] == []


@pytest.mark.parametrize(
    ("counts", "expected"),
    [
        ({"provider-a": [1, 1], "provider-z": [5, 0]}, ["provider-z", "provider-a"]),
        (
            {"provider-a": [1, 1, 4], "provider-z": [2, 2, 2]},
            ["provider-a", "provider-z"],
        ),
    ],
)
def test_cli_ranks_by_pass1_with_stable_exact_ties(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    counts: dict[str, list[int]],
    expected: list[str],
) -> None:
    """Reliability outranks best-of-five success; roundoff cannot break equal pass@1."""
    results = tmp_path / "full"
    for model, successes in counts.items():
        run = results / model / "published"
        run.mkdir(parents=True)
        records = [
            {
                "info": {"task_id": f"study-{study}"},
                "completion": [
                    {
                        "content": json.dumps(
                            {
                                "findings": {"present": attempt < correct},
                                "diagnosis": "nodule",
                                "next_step": "none",
                            }
                        )
                    }
                ],
            }
            for study, correct in enumerate(successes)
            for attempt in range(5)
        ]
        (run / "results.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in records), encoding="utf-8"
        )
    gold_path = tmp_path / "gold.json"
    gold_path.write_text(
        json.dumps(
            {
                f"study-{study}": {
                    "critical_findings": {"present": True},
                    "diagnosis_accepted": ["nodule"],
                    "next_step_accepted": ["none"],
                }
                for study in range(len(next(iter(counts.values()))))
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "leaderboard.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "passk.py",
            str(results),
            "--gold",
            str(gold_path),
            "--out",
            str(output),
            "--bootstrap-resamples",
            "200",
            "--bootstrap-seed",
            "7",
        ],
    )

    main()

    board = json.loads(output.read_text(encoding="utf-8"))
    names = [model.replace("-", "/", 1) for model in expected]
    assert [model["model"] for model in board["models"]] == names
    printed = capsys.readouterr().out
    assert printed.index(f"\n{expected[0].split('-')[1]} ") < printed.index(
        f"\n{expected[1].split('-')[1]} "
    )
    if expected[0] == "provider-z":
        first, second = board["models"]
        assert first["pass@1"] > second["pass@1"]
        assert first["pass@5"] < second["pass@5"]
        assert first["solved_all"] == 1


def test_bootstrap_reports_every_paired_difference_with_consistent_direction() -> None:
    """Uniform study-level advantages survive every common draw for all model pairs."""
    models = {
        f"provider/model-{index}": _groups(
            {"study-a": (index, 5), "study-b": (index + 1, 5)}
        )
        for index in range(5)
    }
    _, uncertainty = paired_bootstrap(models, 5, resamples=200, seed=13)
    contrasts = {
        (row["model_a"], row["model_b"]): row
        for row in uncertainty["pass@1_comparisons"]
    }
    expected = {
        (f"provider/model-{a}", f"provider/model-{b}"): (a - b) / 5
        for a in range(5)
        for b in range(a + 1, 5)
    }
    assert contrasts.keys() == expected.keys()
    for pair, difference in expected.items():
        assert contrasts[pair]["difference"] == pytest.approx(difference)
        assert contrasts[pair]["ci95"] == pytest.approx([difference, difference])
