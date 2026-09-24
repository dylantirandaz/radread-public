"""RadRead-public as a verifiers environment: one model call per radiology study.

The task bundle in ``envs/radread-public`` is the source of truth. This module reads its
``environment/tasks.jsonl`` prompts verbatim, attaches the study's radiograph on the image
channel, and grades the reply with the bundle's own deterministic grader
(``verifier/read_scoring.py``) against an authorized host-side gold file. No LLM judge, no tools.

Pixels never enter the saved rollout record: the image part is injected into the messages that
go to the provider and stripped from the transcript kept on disk (see NOTICE.md).
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import verifiers as vf
from datasets import Dataset
from verifiers.legacy.types import (
    ImageUrlContentPart,
    ImageUrlSource,
    TextContentPart,
    UserMessage,
)

DEFAULT_ENV_ROOT = Path(__file__).resolve().parents[2] / "envs" / "radread-public"

# study_id prefix -> upstream image source, for per-source breakdowns.
SOURCE_BY_PREFIX = {
    "nih": "NIH ChestX-ray14",
    "chestdet": "ChestX-Det",
    "vindr": "VinDr-CXR",
    "rsna": "RSNA Pneumonia",
    "graz": "GRAZPEDWRI-DX",
    "frac": "FracAtlas",
}


def _relax_service_tier() -> None:
    """Accept provider-specific ``service_tier`` values on chat completions.

    verifiers parses every response with ``ChatCompletion.model_validate_json``, and the
    OpenAI SDK types ``service_tier`` as a closed literal. Prime Inference answers image
    requests with ``service_tier: "provisioned"``, so strict validation turns a perfectly
    good completion into a ModelError. Widen the annotation to ``str`` once at import.
    """
    from openai.types.chat.chat_completion import ChatCompletion

    field = ChatCompletion.model_fields.get("service_tier")
    if field is None or field.annotation == (str | None):
        return
    field.annotation = str | None
    ChatCompletion.model_rebuild(force=True)


_relax_service_tier()


def _env_root() -> Path:
    root = Path(os.environ.get("RADREAD_PUBLIC_ROOT", DEFAULT_ENV_ROOT)).resolve()
    if not (root / "environment" / "tasks.jsonl").is_file():
        raise FileNotFoundError(
            f"radread-public env not found at {root}: expected environment/tasks.jsonl. "
            "Set RADREAD_PUBLIC_ROOT to the env directory."
        )
    return root


def _load_grader(root: Path) -> ModuleType:
    """Import the env's vendored grader by path so there is exactly one scoring implementation."""
    path = root / "verifier" / "read_scoring.py"
    spec = importlib.util.spec_from_file_location("radread_read_scoring", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import grader from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@cache
def _image_part(path: str, detail: str) -> ImageUrlContentPart:
    """Base64 image content part, built once per study and shared across rollouts."""
    raw = Path(path).read_bytes()
    mime = (
        "image/jpeg" if Path(path).suffix.lower() in (".jpg", ".jpeg") else "image/png"
    )
    url = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    source = (
        ImageUrlSource(url=url)
        if detail == "auto"
        else ImageUrlSource(url=url, detail=detail)
    )
    return ImageUrlContentPart(image_url=source)


def _source_of(study_id: str) -> str:
    return SOURCE_BY_PREFIX.get(study_id.split("_")[0], "other")


def _role_of(message: Any) -> str | None:
    return (
        message.get("role")
        if isinstance(message, dict)
        else getattr(message, "role", None)
    )


def _text_of(message: Any) -> str:
    content = message["content"] if isinstance(message, dict) else message.content
    if isinstance(content, str):
        return content
    parts = []
    for part in content:
        kind = (
            part.get("type") if isinstance(part, dict) else getattr(part, "type", None)
        )
        if kind == "text":
            parts.append(part["text"] if isinstance(part, dict) else part.text)
    return "\n".join(parts)


class RadReadEnv(vf.SingleTurnEnv):
    """SingleTurnEnv that attaches the study image to the request but not to the transcript.

    With ``send_image=False`` the prompt goes out unchanged and the radiograph is withheld: the
    text-only baseline that measures how much of a study the checklist alone gives away.
    """

    def __init__(
        self,
        images_root: Path,
        image_detail: str = "auto",
        send_image: bool = True,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.images_root = images_root
        self.image_detail = image_detail
        self.send_image = send_image

    async def get_prompt_messages(self, state: vf.State) -> Any:
        messages = await super().get_prompt_messages(state)
        if state["trajectory"] or not self.send_image:
            return messages
        info = state.get("info") or {}
        image = info.get("image")
        if not image:
            raise ValueError(f"task {info.get('task_id')!r} has no image path")
        image_path = self.images_root / image
        if not image_path.is_file():
            raise FileNotFoundError(
                f"missing image {image_path} for task {info.get('task_id')!r}"
            )
        part = _image_part(str(image_path), self.image_detail)
        out = list(messages)
        index = max(i for i, m in enumerate(out) if _role_of(m) == "user")
        out[index] = UserMessage(
            content=[TextContentPart(text=_text_of(out[index])), part]
        )
        return out


def load_environment(
    env_root: str | Path | None = None,
    num_tasks: int | None = None,
    image_detail: str = "auto",
    task_ids: list[str] | None = None,
    send_image: bool = True,
    gold_path: str | Path | None = None,
    **kwargs: Any,
) -> vf.Environment:
    """Build the radread-public environment.

    Args:
        env_root: Path to the task bundle (default: ``envs/radread-public`` in this repo).
        num_tasks: Keep only the first N tasks (smoke tests); ``None`` keeps the full cohort.
        image_detail: OpenAI-style image detail hint; ``auto`` sends no detail field.
        task_ids: Explicit task-id allowlist, applied before ``num_tasks``.
        send_image: ``False`` withholds the radiograph — the text-only baseline.
        gold_path: Authorized answer key. Explicit path overrides ``RADREAD_GOLD``, then
            the private bundle default ``verifier/gold.json``. Never added to model inputs.

    Returns:
        A ``vf.SingleTurnEnv`` whose reward is 1.0 only when every gold check on the case passes.
    """
    root = Path(env_root).resolve() if env_root else _env_root()
    grader = _load_grader(root)
    selected_gold = (
        gold_path if gold_path is not None else os.environ.get("RADREAD_GOLD")
    )
    key_path = (
        Path(selected_gold).expanduser().resolve()
        if selected_gold is not None
        else root / "verifier" / "gold.json"
    )
    if not key_path.is_file():
        raise FileNotFoundError(
            f"Missing authorized gold at {key_path}. Scored evaluation requires an authorized "
            "answer key: supply gold_path or set RADREAD_GOLD. The public bundle does not include it."
        )
    gold: dict[str, dict[str, Any]] = json.loads(key_path.read_text(encoding="utf-8"))
    if not isinstance(gold, dict):
        raise TypeError(
            f"authorized gold at {key_path} must map task IDs to grading records"
        )
    images_root = root / "environment"

    rows: list[dict[str, Any]] = []
    for line in (
        (root / "environment" / "tasks.jsonl").read_text(encoding="utf-8").splitlines()
    ):
        if not line.strip():
            continue
        task = json.loads(line)
        task_id = task["task_id"]
        if task_ids is not None and task_id not in task_ids:
            continue
        rows.append(
            {
                "prompt": [
                    {"role": "system", "content": task["system_prompt"]},
                    {"role": "user", "content": task["user_prompt"]},
                ],
                "answer": task_id,
                "info": {
                    "task_id": task_id,
                    "study_id": task["study_id"],
                    "image": task["image"],
                    "source": _source_of(task["study_id"]),
                },
            }
        )
    if task_ids is not None:
        unknown = set(task_ids) - {row["info"]["task_id"] for row in rows}
        if unknown:
            raise ValueError(f"unknown task IDs: {', '.join(sorted(unknown))}")
    if num_tasks is not None:
        rows = rows[:num_tasks]
    if not rows:
        raise ValueError("no tasks selected")
    for row in rows:
        task_id = row["info"]["task_id"]
        if task_id not in gold:
            raise KeyError(f"task {task_id} has no gold entry in {key_path}")
        case_gold = gold[task_id]
        if (
            not isinstance(case_gold, dict)
            or not isinstance(case_gold.get("critical_findings"), dict)
            or not isinstance(case_gold.get("diagnosis_accepted"), list)
            or not case_gold["diagnosis_accepted"]
            or not isinstance(case_gold.get("next_step_accepted"), list)
            or not case_gold["next_step_accepted"]
        ):
            raise ValueError(
                f"task {task_id} has an invalid grading record in authorized gold at {key_path}"
            )
        if send_image:
            image_path = images_root / row["info"]["image"]
            if not image_path.is_file():
                raise FileNotFoundError(
                    f"missing image {image_path} for task {task_id!r}; prepare authorized images before evaluation"
                )

    def _report(completion: Any, info: dict[str, Any]) -> dict[str, Any]:
        # Gold stays in this host-side closure, never in dataset rows, prompts, or transcripts.
        # Dataset serialization also must not reshape nested grading records.
        text = (
            completion
            if isinstance(completion, str)
            else vf.Parser().parse_answer(completion) or ""
        )
        return grader.grade({"gold": gold[info["task_id"]]}, text)

    def read_correct(completion: Any, info: dict[str, Any]) -> float:
        """1.0 only if every check on the case passes — the env's own pass criterion."""
        return float(bool(_report(completion, info)["pass_"]))

    def checks_accuracy(completion: Any, info: dict[str, Any]) -> float:
        """Fraction of individual gold checks passed (partial credit, diagnostic only)."""
        report = _report(completion, info)
        total = int(report.get("checks_total", 0)) or 1
        return float(report.get("checks_passed", 0)) / total

    def reply_parsed(completion: Any, info: dict[str, Any]) -> float:
        """1.0 if the reply contained a parseable JSON read (malformed output is a task failure)."""
        report = _report(completion, info)
        return float(
            not any(
                c["check"] == "valid_json" and not c["passed"] for c in report["checks"]
            )
        )

    rubric = vf.Rubric(
        funcs=[read_correct, checks_accuracy, reply_parsed], weights=[1.0, 0.0, 0.0]
    )
    return RadReadEnv(
        images_root=images_root,
        image_detail=image_detail,
        send_image=send_image,
        dataset=Dataset.from_list(rows),
        rubric=rubric,
        **kwargs,
    )
