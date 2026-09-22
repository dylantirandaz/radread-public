"""Synthetic CLI coverage for the public helpers and external answer-key boundary."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """Stage only shipped helpers, the actual grader, and a synthetic task manifest."""
    root = tmp_path / "checkout"
    for relative in (
        "scripts/prepare_images.py",
        "scripts/collect_answers.py",
        "scripts/score.py",
        "envs/radread-public/verifier/read_scoring.py",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    environment = root / "envs/radread-public/environment"
    environment.mkdir()
    (environment / "tasks.jsonl").write_text(
        json.dumps({"task_id": "synthetic"}) + "\n", encoding="utf-8"
    )
    return root


def _run(
    root: Path, script: str, *arguments: str, gold: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Exercise a checkout from outside it, without inherited private configuration."""
    environment = os.environ.copy()
    environment.pop("RADREAD_GOLD", None)
    environment.pop("RADREAD_PUBLIC_ROOT", None)
    if gold is not None:
        environment["RADREAD_GOLD"] = str(gold)
    # Collection and scoring are deliberately exercised without any site packages.
    flags = ["-I"] if script == "prepare_images.py" else ["-I", "-S"]
    return subprocess.run(
        [sys.executable, *flags, str(root / "scripts" / script), *arguments],
        cwd=root.parent,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def _completion() -> dict[str, object]:
    return {
        "findings": {"synthetic_flag": True},
        "diagnosis": "synthetic condition",
        "next_step": "none",
        "impression": "Synthetic fixture, not a clinical case.",
    }


def _gold(path: Path, expected: bool) -> None:
    path.write_text(
        json.dumps(
            {
                "synthetic": {
                    "critical_findings": {"synthetic_flag": expected},
                    "diagnosis_accepted": ["synthetic condition"],
                    "next_step_accepted": ["none"],
                }
            }
        ),
        encoding="utf-8",
    )


def test_collect_without_gold_then_score_external_key(checkout: Path) -> None:
    completions = checkout.parent / "completions"
    completions.mkdir()
    (completions / "synthetic.json").write_text(
        json.dumps(_completion()), encoding="utf-8"
    )
    missing_key = checkout.parent / "absent.json"
    collected = _run(
        checkout,
        "collect_answers.py",
        "--completions",
        str(completions),
        gold=missing_key,
    )
    assert collected.returncode == 0, collected.stderr
    row = json.loads((checkout / "answers.jsonl").read_text(encoding="utf-8"))
    assert row["task_id"] == "synthetic"
    assert json.loads(row["completion"]) == _completion()

    refused = _run(checkout, "score.py")
    assert refused.returncode != 0
    assert "--gold" in refused.stderr
    assert not (checkout / "results/score.json").exists()

    key = checkout.parent / "authorized.json"
    _gold(key, True)
    scored = _run(checkout, "score.py", "--gold", str(key), gold=missing_key)
    assert scored.returncode == 0, scored.stderr
    report = json.loads((checkout / "results/score.json").read_text(encoding="utf-8"))
    assert report["reward"] == 1.0
    assert report["tasks"][0]["pass_"] is True


def test_gold_precedence_never_falls_back_from_missing_selected_key(
    checkout: Path,
) -> None:
    (checkout / "answers.jsonl").write_text(
        json.dumps({"task_id": "synthetic", "completion": json.dumps(_completion())})
        + "\n",
        encoding="utf-8",
    )
    _gold(checkout / "envs/radread-public/verifier/gold.json", False)
    key = checkout.parent / "authorized.json"
    _gold(key, True)
    from_environment = _run(
        checkout, "score.py", "--output", str(checkout / "environment.json"), gold=key
    )
    assert from_environment.returncode == 0, from_environment.stderr
    assert json.loads((checkout / "environment.json").read_text())["reward"] == 1.0
    from_bundle = _run(checkout, "score.py")
    assert from_bundle.returncode == 0, from_bundle.stderr
    assert json.loads((checkout / "results/score.json").read_text())["reward"] == 0.0

    missing = checkout.parent / "missing-key.json"
    for arguments, env_gold in ((("--gold", str(missing)), key), ((), missing)):
        rejected_output = checkout / "must-not-exist.json"
        rejected = _run(
            checkout,
            "score.py",
            *arguments,
            "--output",
            str(rejected_output),
            gold=env_gold
        )
        assert rejected.returncode != 0
        assert not rejected_output.exists()


def test_collection_rejects_unsafe_ids_and_preserves_submission(checkout: Path) -> None:
    completions = checkout.parent / "completions"
    completions.mkdir()
    (completions / "synthetic.json").write_text(
        json.dumps(_completion()), encoding="utf-8"
    )
    answers = checkout / "answers.jsonl"
    answers.write_text("existing submission\n", encoding="utf-8")
    collision = _run(checkout, "collect_answers.py", "--completions", str(completions))
    assert collision.returncode != 0
    assert answers.read_text(encoding="utf-8") == "existing submission\n"

    manifest = checkout / "envs/radread-public/environment/tasks.jsonl"
    manifest.write_text(json.dumps({"task_id": "../outside"}) + "\n", encoding="utf-8")
    output = checkout / "rejected.jsonl"
    traversal = _run(
        checkout,
        "collect_answers.py",
        "--completions",
        str(completions),
        "--answers",
        str(output),
    )
    assert traversal.returncode != 0
    assert not output.exists()


def test_prepare_local_source_from_other_cwd_preserves_pixels_and_guard(
    checkout: Path,
) -> None:
    environment = checkout / "envs/radread-public/environment"
    (environment / "sources.jsonl").write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"source": "nih-chestxray14", "study_id": "nih_synthetic"},
                {"source": "graz", "study_id": "graz_unselected"},
            )
        )
        + "\n",
        encoding="utf-8",
    )
    inputs = checkout.parent / "inputs"
    source = inputs / "nih-chestxray14/nested/synthetic.png"
    source.parent.mkdir(parents=True)
    Image.new("L", (1024, 1024), color=31).save(source)
    arguments = ("--input-root", str(inputs), "--source", "nih-chestxray14")
    prepared = _run(checkout, "prepare_images.py", *arguments)
    assert prepared.returncode == 0, prepared.stderr
    output = environment / "images/nih_synthetic.png"
    assert output.read_bytes() == source.read_bytes()
    assert not (environment / "images/graz_unselected.png").exists()

    original = output.read_bytes()
    Image.new("L", (1024, 1024), color=92).save(source)
    refused = _run(checkout, "prepare_images.py", *arguments)
    assert refused.returncode != 0
    assert output.read_bytes() == original
    replaced = _run(checkout, "prepare_images.py", *arguments, "--overwrite")
    assert replaced.returncode == 0, replaced.stderr
    assert output.read_bytes() == source.read_bytes()
