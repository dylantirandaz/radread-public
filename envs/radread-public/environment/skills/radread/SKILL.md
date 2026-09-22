# radread skill

How to write a radiology read the RadRead verifier accepts.

## What you receive per task

A `tasks.jsonl` line: `task_id`, `system_prompt`, `user_prompt` (request form + findings
checklist), and `image` (path relative to the workspace, one 1024x1024 radiograph).

## What you write

One line per task in `/root/answers.jsonl`:

{"task_id": "<id>", "completion": "<JSON string>"}

The completion parses as ONE JSON object:

{"findings": {...}, "diagnosis": "<one line>", "next_step": "<one of: emergency_action, urgent_review, routine_followup, none>", "impression": "<one line>"}

## Findings values by key shape

- Plain keys (e.g. `fracture_present`): JSON `true` or `false`. Answer every one.
- Word keys (marked "answer a word"): a short string such as `"left"` or `"right"`.
  Sides are the PATIENT's left/right, as a radiologist reports them.
- Number keys (marked with a unit): a JSON number.
- Single boxes (e.g. `nodule_box`): one `[x1, y1, x2, y2]` in pixels from the top-left.
- Box lists (keys ending in `_boxes`): a LIST of `[x1, y1, x2, y2]` boxes, one per finding.
  Box every finding you identify, not only the most obvious.

## How you are scored (so you know what matters)

- Every graded checklist key must satisfy its case-specific check. Extra findings keys are
  ignored; they do not themselves fail the task. Booleans must match exactly, words are
  normalized, and measurements must fall within their accepted ranges.
- Localization is not IoU-only. Focal boxes pass by the configured IoU threshold, a
  comparable-size box centered within the expanded reference region, or sufficient
  containment. Extent boxes additionally allow bounded coverage of the reference region.
- Each required lesion in a box list needs a matching box. Matching is one-to-one and
  maximizes required matches before optional matches; duplicating a box cannot count the
  same reference lesion twice. Unmatched boxes must stay within the case's extra-box quota.
  When both nodule and mass box sets are graded, their boxes and quotas are pooled.
- Diagnosis uses the grader's normalized accepted-label and negation-aware matching;
  next step must exactly match an accepted action. The free-text impression is not scored.
- A task receives 1 only if all its checks pass, otherwise 0. The answer key is not
  available to the agent; it is supplied to the verifier only after the agent finishes.
