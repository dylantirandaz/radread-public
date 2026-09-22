"""Regression coverage for reproducible rollout selection."""

import json
from pathlib import Path

import pytest

from scripts.passk import load_gold, load_grader, pass_at_k, scored_records


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
