"""Deterministic scoring for the radiology read: a structured reply against the case gold.

The model answers one JSON object: findings (booleans per template key), diagnosis (one line),
next_step (one of emergency_action | urgent_review | routine_followup | none), impression (free text).
Pass requires: the normalized diagnosis in the case's accepted set, every template finding correct,
and the next step in the case's accepted classes. No LLM judge anywhere.
"""
from __future__ import annotations

import json
import re

NEXT_STEPS = ("emergency_action", "urgent_review", "routine_followup", "none")


def parse_reply(text: str) -> dict[str, object] | None:
    """The JSON object in the reply: whole text, a fenced block, or the last brace span."""
    text = text.strip()
    for candidate in (text,):
        try:
            value = json.loads(candidate)
            return value if isinstance(value, dict) else None
        except (json.JSONDecodeError, ValueError):
            pass
    fence = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    for block in fence:
        try:
            value = json.loads(block)
            return value if isinstance(value, dict) else None
        except (json.JSONDecodeError, ValueError):
            continue
    spans = re.findall(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
    for span in reversed(spans):
        try:
            value = json.loads(span)
            return value if isinstance(value, dict) else None
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def normalize_label(text: object) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()
    return re.sub(r"\boedema\b", "edema", cleaned)

IMAGE_AREA_PX = 1024 * 1024


def box_verdict(x1: float, y1: float, x2: float, y2: float, expert: dict[str, object], kind: str, min_iou: float) -> tuple[bool, str]:
    """Judge one answered box against one expert box.

    focal (nodule, mass): IoU >= min_iou, or the answered centre lies inside the expert box dilated by
    half its size and the answered box is within a factor of four of the expert area, or the answered
    box sits inside the expert box and is at least 1% of its area - a tight box around the right
    lesion passes even when the gold box is loose, while a speck dropped in a large finding does not.
    extent (effusion, pneumothorax, consolidation): the focal criteria, or the answered box covers
    at least half of the expert box and is no larger than max(4x the expert area, 5% of the image) -
    a region drawn around a costophrenic angle passes, a whole-hemithorax box does not.

    The lower area bound matters for large findings: dilation scales with the expert box, so a
    300 px consolidation accepts centres over a fifth of the film, and without it a 24 px speck
    anywhere in that zone would count as finding the consolidation.
    """
    gx1, gy1, gx2, gy2 = float(expert["x1"]), float(expert["y1"]), float(expert["x2"]), float(expert["y2"])
    ix = max(0.0, min(x2, gx2) - max(x1, gx1))
    iy = max(0.0, min(y2, gy2) - max(y1, gy1))
    inter = ix * iy
    area = (x2 - x1) * (y2 - y1)
    expert_area = (gx2 - gx1) * (gy2 - gy1)
    union = max(1e-9, area + expert_area - inter)
    iou = inter / union
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    gw, gh = gx2 - gx1, gy2 - gy1
    centre_hit = (gx1 - 0.5 * gw <= cx <= gx2 + 0.5 * gw) and (gy1 - 0.5 * gh <= cy <= gy2 + 0.5 * gh)
    comparable_size = 0.25 * expert_area <= area <= 4.0 * expert_area
    contained = inter / max(area, 1e-9) >= 0.9 and area / max(expert_area, 1e-9) >= 0.01
    focal_ok = iou >= min_iou or (centre_hit and comparable_size) or contained
    focal_note = (f"IoU {iou:.2f} (needs >= {min_iou}); centre {'inside' if centre_hit else 'outside'} the dilated expert box, "
                  f"area x{area / max(expert_area, 1e-9):.2f} of the expert box"
                  + (", contained in the expert box" if contained else ""))
    if kind == "focal":
        return focal_ok, focal_note
    if kind != "extent":
        raise ValueError(f"unknown box kind {kind!r}")
    coverage = inter / max(expert_area, 1e-9)
    bounded = area <= max(4.0 * expert_area, 0.05 * IMAGE_AREA_PX)
    ok = focal_ok or (coverage >= 0.5 and bounded)
    return ok, (f"{focal_note}; covers {coverage:.0%} of the expert box, "
                f"area {area / IMAGE_AREA_PX:.1%} of the image ({'bounded' if bounded else 'too large'})")


def _max_bipartite_match(adj: list[list[int]], n_left: int, n_right: int) -> tuple[list[int], list[int]]:
    """Maximum bipartite matching (Hopcroft-Karp). adj[u] lists the v it may take.
    Returns (match_l, match_r) with -1 for unmatched. Deterministic for fixed input order."""
    from collections import deque

    INF = n_left + n_right + 1
    match_l = [-1] * n_left
    match_r = [-1] * n_right
    dist = [0] * n_left

    def bfs() -> bool:
        queue = deque()
        for u in range(n_left):
            if match_l[u] == -1:
                dist[u] = 0
                queue.append(u)
            else:
                dist[u] = INF
        dist_nil = INF
        while queue:
            u = queue.popleft()
            if dist[u] < dist_nil:
                for v in adj[u]:
                    w = match_r[v]
                    if w == -1:
                        dist_nil = dist[u] + 1
                    elif dist[w] == INF:
                        dist[w] = dist[u] + 1
                        queue.append(w)
        return dist_nil != INF

    def dfs(u: int) -> bool:
        for v in adj[u]:
            w = match_r[v]
            if w == -1 or (dist[w] == dist[u] + 1 and dfs(w)):
                match_l[u] = v
                match_r[v] = u
                return True
        dist[u] = INF
        return False

    while bfs():
        for u in range(n_left):
            if match_l[u] == -1:
                dfs(u)
    return match_l, match_r


def match_box_set(answered: list[list[float]], experts: list[dict[str, object]]) -> tuple[list[str | None], list[bool | None], list[str]]:
    """Find every marked finding: each answered box matches at most one expert box, each expert is matched
    at most once, and a box flagged must_find=false is tolerated rather than required (matched if answered,
    unpenalized if not). Assignment is optimal, not greedy: required matches are maximized first, then
    tolerated matches with the remaining boxes, so the result never depends on the answer order.
    Returns (per-answered-box verdict or None for unmatched, per-expert hit state,
    per-missing-must-find notes)."""
    try:
        coords = [[float(v) for v in box] for box in answered]
    except (TypeError, ValueError):
        return [f"answered {box!r}, expected [x1, y1, x2, y2]" for box in answered], [], []
    required = [bool(expert.get("must_find", True)) for expert in experts]
    ok_matrix: list[list[bool]] = []
    note_matrix: list[list[str]] = []
    for x1, y1, x2, y2 in coords:
        row, notes = [], []
        for expert in experts:
            ok, note = box_verdict(x1, y1, x2, y2, expert, str(expert.get("kind", "focal")), float(expert.get("min_iou", 0.25)))
            row.append(ok)
            notes.append(note)
        ok_matrix.append(row)
        note_matrix.append(notes)
    consumed = [False] * len(experts)
    verdicts: list[str | None] = [None] * len(coords)
    for want_required in (True, False):
        adj = [[v for v in range(len(experts))
                if not consumed[v] and required[v] == want_required and ok_matrix[u][v]]
               for u in range(len(coords)) if verdicts[u] is None]
        rows = [u for u in range(len(coords)) if verdicts[u] is None]
        match_l, _ = _max_bipartite_match(adj, len(rows), len(experts))
        for row, expert in zip(rows, match_l):
            if expert != -1:
                consumed[expert] = True
                verdicts[row] = f"matched expert box {expert + 1} ({note_matrix[row][expert]})"
    hits: list[bool | None] = [c if r else None for c, r in zip(consumed, required)]
    misses = [f"missing marked finding {index + 1} (expert box [{e['x1']}, {e['y1']}, {e['x2']}, {e['y2']}])"
              for index, (e, req, hit) in enumerate(zip(experts, required, consumed)) if req and not hit]
    return verdicts, hits, misses


def grade(case: dict[str, object], reply_text: str) -> dict[str, object]:
    """Grade one reply against one case. Returns the report dict (pass_ plus the check rows)."""
    gold = case["gold"]
    checks: list[dict[str, object]] = []

    def record(name: str, passed: bool, observed: str) -> None:
        checks.append({"check": name, "passed": passed, "observed": observed})

    payload = parse_reply(reply_text)
    if payload is None:
        record("valid_json", False, "no JSON object in the reply")
        return {"pass_": False, "checks": checks, "checks_passed": 0, "checks_total": len(checks)}

    findings = payload.get("findings")
    findings = findings if isinstance(findings, dict) else {}
    for key, expected in gold["critical_findings"].items():
        answered = findings.get(key)
        if isinstance(expected, bool):
            ok = answered is expected
        else:
            ok = normalize_label(answered) == normalize_label(expected)
        record(f"finding:{key}", ok, f"answered {answered!r}, expected {expected!r}")

    for key, band in gold.get("measurement_findings", {}).items():
        try:
            value = float(findings.get(key))
            ok = float(band["min"]) <= value <= float(band["max"])
            observed = f"answered {value:g}, expected {band['min']:g}-{band['max']:g} {band.get('unit', '')}"
        except (TypeError, ValueError):
            ok, observed = False, f"answered {findings.get(key)!r} (not a number in {band['min']:g}-{band['max']:g})"
        record(f"measurement:{key}", ok, observed)

    for key, spec in gold.get("box_findings", {}).items():
        answered = findings.get(key)
        try:
            x1, y1, x2, y2 = [float(v) for v in answered]
        except (TypeError, ValueError):
            record(f"box:{key}", False, f"answered {answered!r}, expected a box [x1, y1, x2, y2]")
            continue
        verdicts = [box_verdict(x1, y1, x2, y2, expert, str(spec.get("kind", "focal")), float(spec.get("min_iou", 0.3)))
                    for expert in [spec, *spec.get("alternatives", [])]]
        ok = any(v[0] for v in verdicts)
        record(f"box:{key}", ok, " | ".join(v[1] for v in verdicts))
    box_sets = dict(gold.get("box_sets", {}))
    if "nodule_boxes" in box_sets and "mass_boxes" in box_sets:
        # a nodule over 3 cm is a mass: one pooled lesion set, so a box on the right lesion
        # never fails for choosing the other label. Quotas pool with the boxes.
        pooled_boxes = [*box_sets["nodule_boxes"]["boxes"], *box_sets["mass_boxes"]["boxes"]]
        pooled_quota = int(box_sets["nodule_boxes"].get("max_extra", 0)) + int(box_sets["mass_boxes"].get("max_extra", 0))
        del box_sets["nodule_boxes"]
        del box_sets["mass_boxes"]
        box_sets["nodule_mass_boxes"] = {"boxes": pooled_boxes, "max_extra": pooled_quota}
    for key, spec in box_sets.items():
        if key == "nodule_mass_boxes":
            answered = list(findings.get("nodule_boxes") or []) + list(findings.get("mass_boxes") or [])
        else:
            answered = findings.get(key)
        if answered is None:
            answered = []
        if not isinstance(answered, list) or any(not isinstance(box, list) or len(box) != 4 for box in answered):
            record(f"box_set:{key}", False, f"answered {answered!r}, expected a list of boxes [x1, y1, x2, y2]")
            continue
        experts = [dict(b) for b in spec["boxes"]]
        verdicts, hits, misses = match_box_set(answered, experts)
        required = sum(1 for h in hits if h is not None)
        extra = sum(1 for v in verdicts if v is None)
        max_extra = int(spec.get("max_extra", 0))
        ok = not misses and extra <= max_extra
        detail = f"{sum(1 for h in hits if h)} of {required} marked findings found; {extra} extra box(es) (allowed {max_extra})"
        if misses:
            detail += "; " + "; ".join(misses)
        record(f"box_set:{key}", ok, detail)
    raw_diagnosis = str(payload.get("diagnosis", "")).lower()
    diagnosis = normalize_label(raw_diagnosis)
    accepted = {normalize_label(label) for label in gold["diagnosis_accepted"]}
    gold_is_negative = any(re.search(r"\b(normal|unremarkable|clear|no acute|without)\b", label) for label in accepted)
    clauses = [normalize_label(part) for part in re.split(r"[;,.]|\band\b|\bbut\b", raw_diagnosis) if part.strip()]
    # weak positives, not negations: strip them before the window check so they can never veto.
    weak_positive = re.compile(r"\bto exclude\b|\bnot excluded?\b|\bcannot excludes?\b|\bcan t excludes?\b|\bcould not excludes?\b")
    negation_before = {"no", "not", "absent", "without", "excluding", "excluded", "excludes",
                       "exclude", "clear", "ruled", "rule", "negative"}

    def negated(tokens: list[str], at: int) -> bool:
        """A label occurrence is negated only by a negation word just before it ('no effusion',
        'without consolidation'). Justifying phrases after the finding ('not a normal chest') and
        differential phrases ('malignancy to exclude') never negate it."""
        for back in range(1, 5):
            if at - back < 0:
                break
            if tokens[at - back] in negation_before:
                return True
        return False

    def clause_match(label: str) -> bool:
        if not label:
            return False
        for clause in clauses:
            tokens = weak_positive.sub("", clause).split()
            joined = " ".join(tokens)
            start = 0
            while True:
                at = joined.find(label, start)
                if at < 0:
                    break
                token_at = len(joined[:at].split())
                if gold_is_negative or not negated(tokens, token_at):
                    return True
                start = at + 1
        return diagnosis in label and (gold_is_negative or not negated(diagnosis.split(), 0))

    record("diagnosis", diagnosis in accepted or any(clause_match(label) for label in accepted), f"{payload.get('diagnosis', '')!r}")

    step = str(payload.get("next_step", ""))
    record("next_step", step in gold["next_step_accepted"], f"{step!r} (accepted: {', '.join(gold['next_step_accepted'])})")

    passed = sum(1 for c in checks if c["passed"])
    return {"pass_": passed == len(checks) and bool(checks), "checks": checks,
            "checks_passed": passed, "checks_total": len(checks)}
