"""Regression coverage for invalid diagnoses and lesion coordinates."""

import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from scripts.passk import load_grader


@pytest.fixture(scope="module")
def grader() -> ModuleType:
    """Load the shipped grader without private gold or model dependencies."""
    return load_grader(Path(__file__).resolve().parents[1] / "envs/radread-public")


def _case(as_set: bool = False, max_extra: int = 0) -> dict[str, Any]:
    box = {"x1": 100, "y1": 100, "x2": 200, "y2": 200}
    gold = {
        "critical_findings": {"nodule_present": True},
        "diagnosis_accepted": ["nodule"],
        "next_step_accepted": ["none"],
    }
    if as_set:
        gold["box_sets"] = {"nodule_boxes": {"boxes": [box], "max_extra": max_extra}}
    else:
        gold["box_findings"] = {"nodule_box": box}
    return {"gold": gold}


def _reply() -> dict[str, Any]:
    return {
        "findings": {
            "nodule_present": True,
            "nodule_box": [100, 100, 200, 200],
            "nodule_boxes": [[100, 100, 200, 200]],
        },
        "diagnosis": "nodule",
        "next_step": "none",
    }


@pytest.mark.parametrize("missing", [True, False], ids=["missing", "empty"])
def test_diagnosis_is_required(grader: ModuleType, missing: bool) -> None:
    reply = _reply()
    if missing:
        del reply["diagnosis"]
    else:
        reply["diagnosis"] = ""
    report = grader.grade(_case(), json.dumps(reply))
    assert not report["pass_"]
    assert not next(c["passed"] for c in report["checks"] if c["check"] == "diagnosis")


@pytest.mark.parametrize("coordinate", [None, "not-a-number"], ids=["null", "text"])
def test_nonnumeric_box_set_cannot_pass_without_a_match(
    grader: ModuleType, coordinate: object
) -> None:
    reply = _reply()
    reply["findings"]["nodule_boxes"] = [[coordinate] * 4]
    report = grader.grade(_case(as_set=True, max_extra=1), json.dumps(reply))
    assert not report["pass_"]
    assert not next(
        c["passed"] for c in report["checks"] if c["check"] == "box_set:nodule_boxes"
    )


@pytest.mark.parametrize("as_set", [False, True], ids=["single", "set"])
@pytest.mark.parametrize(
    "box",
    [
        [200, 200, 100, 100],
        [100, 100, 100, 200],
        [-1, 100, 200, 200],
        [100, 100, float("nan"), 200],
        [100, 100, float("inf"), 200],
    ],
    ids=["reversed", "zero-width", "outside-image", "nan", "infinity"],
)
def test_invalid_box_geometry_fails(
    grader: ModuleType, as_set: bool, box: list[float]
) -> None:
    reply = _reply()
    key = "nodule_boxes" if as_set else "nodule_box"
    reply["findings"][key] = [box] if as_set else box
    report = grader.grade(_case(as_set), json.dumps(reply))
    assert not report["pass_"]


@pytest.mark.parametrize("as_set", [False, True], ids=["single", "set"])
def test_image_edge_is_valid_but_beyond_it_fails(
    grader: ModuleType, as_set: bool
) -> None:
    case, reply = _case(as_set), _reply()
    spec = (
        case["gold"]["box_sets"]["nodule_boxes"]["boxes"][0]
        if as_set
        else case["gold"]["box_findings"]["nodule_box"]
    )
    spec.update(x1=0, y1=924, x2=100, y2=1024)
    key = "nodule_boxes" if as_set else "nodule_box"
    box = [0, 924, 100, 1024]
    reply["findings"][key] = [box] if as_set else box
    assert grader.grade(case, json.dumps(reply))["pass_"]
    box[3] = 1025
    assert not grader.grade(case, json.dumps(reply))["pass_"]


def test_extra_box_allowance_does_not_accept_invalid_coordinates(
    grader: ModuleType,
) -> None:
    reply = _reply()
    reply["findings"]["nodule_boxes"].append([200, 200, 100, 100])
    assert not grader.grade(_case(as_set=True, max_extra=1), json.dumps(reply))["pass_"]


def test_extra_box_allowance_still_accepts_valid_unmatched_boxes(
    grader: ModuleType,
) -> None:
    reply = _reply()
    reply["findings"]["nodule_boxes"].append([800, 800, 900, 900])
    text = json.dumps(reply)
    assert grader.grade(_case(as_set=True, max_extra=1), text)["pass_"]
    assert not grader.grade(_case(as_set=True, max_extra=0), text)["pass_"]
