"""Synthetic coverage for public asset preflight and host-only answer keys."""

import asyncio
import base64
import json
import shutil
from pathlib import Path

import pytest

from environments.radread_public.radread_public import load_environment


@pytest.fixture
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.delenv("RADREAD_GOLD", raising=False)
    root = tmp_path / "bundle"
    (root / "environment" / "images").mkdir(parents=True)
    (root / "verifier").mkdir()
    shutil.copyfile(
        Path(__file__).resolve().parents[1]
        / "envs/radread-public/verifier/read_scoring.py",
        root / "verifier/read_scoring.py",
    )
    tasks = [
        {
            "task_id": name,
            "study_id": name,
            "system_prompt": "Read the synthetic image.",
            "user_prompt": "Return the requested JSON.",
            "image": f"images/{name}.png",
        }
        for name in ("first", "second")
    ]
    (root / "environment/tasks.jsonl").write_text(
        "".join(json.dumps(task) + "\n" for task in tasks), encoding="utf-8"
    )
    (root / "environment/images/first.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aO1sAAAAASUVORK5CYII="
        )
    )
    gold = tmp_path / "authorized-key.json"
    gold.write_text(
        json.dumps(
            {
                "first": {
                    "critical_findings": {"host_only_marker_739": True},
                    "diagnosis_accepted": ["synthetic"],
                    "next_step_accepted": ["none"],
                }
            }
        ),
        encoding="utf-8",
    )
    return root, gold


def test_selected_assets_and_host_only_gold(bundle: tuple[Path, Path]) -> None:
    """Unselected missing assets are irrelevant; selected gold never reaches messages."""
    root, gold = bundle
    env = load_environment(root, 1, "auto", None, True, gold_path=gold)
    row = env.get_dataset()[0]
    state = {**row, "trajectory": []}
    before = json.dumps(state)
    messages = asyncio.run(env.get_prompt_messages(state))
    wire = [
        message if isinstance(message, dict) else message.model_dump()
        for message in messages
    ]
    assert "host_only_marker_739" not in before
    assert "host_only_marker_739" not in json.dumps(wire)
    assert "data:image/png;base64," in json.dumps(wire)
    assert json.dumps(state) == before
    assert "data:image" not in before
    state["completion"] = json.dumps(
        {
            "findings": {"host_only_marker_739": True},
            "diagnosis": "synthetic",
            "next_step": "none",
        }
    )
    asyncio.run(env.rubric.score_rollout(state))
    assert state["reward"] == 1.0
    state["completion"] = "{}"
    asyncio.run(env.rubric.score_rollout(state))
    assert state["reward"] == 0.0


def test_missing_selected_image_fails_during_load(bundle: tuple[Path, Path]) -> None:
    root, gold = bundle
    (root / "environment/images/first.png").unlink()
    with pytest.raises(FileNotFoundError, match="image"):
        load_environment(root, num_tasks=1, gold_path=gold)
    # The deliberate text-only baseline has no image dependency.
    env = load_environment(root, num_tasks=1, send_image=False, gold_path=gold)
    row = env.get_dataset()[0]
    assert (
        asyncio.run(env.get_prompt_messages({**row, "trajectory": []})) == row["prompt"]
    )


def test_missing_selected_gold_fails_during_load(bundle: tuple[Path, Path]) -> None:
    root, gold = bundle
    with pytest.raises(KeyError, match="second"):
        load_environment(root, task_ids=["second"], send_image=False, gold_path=gold)


def test_external_gold_precedence_never_silently_falls_back(
    bundle: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, gold = bundle
    shutil.copyfile(gold, root / "verifier/gold.json")
    monkeypatch.setenv("RADREAD_GOLD", str(gold.parent / "missing.json"))
    load_environment(root, num_tasks=1, gold_path=gold)
    with pytest.raises(FileNotFoundError, match="authorized gold"):
        load_environment(root, num_tasks=1)
    monkeypatch.setenv("RADREAD_GOLD", str(gold))
    with pytest.raises(FileNotFoundError, match="authorized gold"):
        load_environment(
            root, num_tasks=1, gold_path=gold.parent / "explicit-missing.json"
        )
    (root / "verifier/gold.json").unlink()
    load_environment(root, num_tasks=1)
    monkeypatch.delenv("RADREAD_GOLD")
    with pytest.raises(FileNotFoundError, match="authorized gold"):
        load_environment(root, num_tasks=1)
