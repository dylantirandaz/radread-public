# RadRead — published 243-study task release

RadRead evaluates **frontier models reading radiographs**. This repository contains the
**243 tasks behind the [published leaderboard](https://dylantirandaz.com/radread-leaderboard/)**,
image provenance, local image preparation, submission tools and the deterministic grader.

[Every model attempt](https://dylantirandaz.com/radread-leaderboard/traces/) ·
[Rollout-level results](https://huggingface.co/datasets/tirandazdylan/radread-public-results)

| Source | Studies |
| --- | ---: |
| NIH ChestX-ray14 | 18 |
| ChestX-Det | 195 |
| VinDr-CXR | 15 |
| RSNA Pneumonia Detection Challenge | 6 |
| GRAZPEDWRI-DX | 9 |
| **Total** | **243** |

**Not included:** radiograph pixels, benchmark gold/reference labels or boxes, oracle
answers, private evaluation artifacts, commercial environments, credentials, or private
repository history. The benchmark answer key is withheld; upstream dataset labels may
still be independently available. This is not a claim that task answers are unknowable.
For evaluation, not clinical use. This benchmark is not a medical device, clinical
decision service, or substitute for a radiologist.

## Files and interfaces

- `tasks.jsonl`: exactly `task_id`, `study_id`, `system_prompt`, `user_prompt`, `image`,
  `checklist`; one task per study. Prompts/checklists retain the published task content.
- `sources.jsonl`: exactly `study_id`, `source`, `study_ref`. References retain historical
  provenance, including historical archive/mirror names; **they are not authorized
  download instructions**. See `NOTICE.md` for official acquisition sources.
- `prepare_images.py`: local source-file preparation; no automatic acquisition.
- `collect_answers.py`: collect real task completions without gold or a model API.
- `submission.schema.json` and `completion.schema.json`: outer JSONL row and decoded
  completion schemas respectively.
- `read_scoring.py`: unchanged grading implementation from the published environment;
  it contains scoring logic, not case-specific answers.
- `score.py`: restricted local scoring, requiring explicitly supplied private gold.

Use Python 3.10 or newer. Image preparation requires:

```sh
python -m pip install -r requirements.txt
```

Collection and scoring otherwise use only Python's standard library. There is no API
server, managed inference service, cloud upload, or model dependency.

## 1. Obtain source files through authorized channels

Read `NOTICE.md` **before acquisition or inference**. Obtain the relevant original files
from their source provider under the terms applicable to you. Extract archives locally;
no source ZIP is automatically downloaded or unpacked by this release. Place files below
these source-specific directories (nested extraction folders are accepted):

```text
inputs/
  nih-chestxray14/  00026398_000.png, ...
  chestdet/         70948.png, ...
  vindr/            <anonymous-image-id>.png, ...
  rsna/             <patient-uuid>.dcm (or .dicom), ...
  graz/             3799_0950453336_04_WRI-L2_M010.png, ...
```

Exact IDs are in `sources.jsonl`. Remove the `nih_`, `chestdet_`, `vindr_`, `rsna_`, or
`graz_` study-ID prefix to get the original filename stem. NIH references name the
`images_NNN.zip` archive; ChestX-Det references identify train/test archives; GRAZ
references identify the original figshare file. A study must resolve to exactly one
matching source file. Duplicate copies of the same basename must be removed from the
selected source directory; ambiguous matches fail rather than choosing silently.

### Important rendering/reproducibility limits

- **NIH and ChestX-Det:** a grayscale 1024×1024 PNG is preserved byte-for-byte. Otherwise
  convert to grayscale and resize with LANCZOS to 1024×1024, matching the historical helper.
- **GRAZ:** the original PNGs are 16-bit. Keep the top byte (`>> 8`) when not already in
  grayscale `L` mode; then LANCZOS-resize to 1024×1024, matching the historical helper.
- **VinDr:** authorized PhysioNet access supplies DICOMs, but the historical benchmark
  consumed original-resolution, 8-bit grayscale PNGs from a processed source. The upstream
  **DICOM-to-PNG conversion is not documented sufficiently to reproduce it**. This script
  deliberately accepts only equivalent, legitimately held `L`-mode PNGs and performs only
  the known LANCZOS resize. It does not invent a DICOM window, accept an access-bypassing
  mirror, or claim that arbitrary PNG conversion matches the published pixels. Access to
  authorized DICOMs alone is not enough to guarantee exact VinDr pixel reconstruction.
- **RSNA:** the historical helper decoded a JPEG-baseline frame inside the DICOM without
  rescale, windowing, or inversion; that exact decode path is retained. Official
  uncompressed 8-bit grayscale DICOMs can also be read directly without normalization.
  Different source encodings may produce different pixels; raw official images are not
  claimed byte-equivalent to historically JPEG-compressed images. Unsupported transfer
  syntaxes or non-8-bit raw images fail rather than guessing a rendering.

Thus task text and cohort are preserved exactly, but this metadata-only release does
**not** promise exact published image reconstruction from every currently available
upstream download. No benchmark pixels are shipped to work around these limitations.

## 2. Prepare local task images

From this repository directory:

```sh
python prepare_images.py --input-root /path/to/authorized/inputs
```

The result is `images/<study_id>.png`, exactly as referenced by `tasks.jsonl`. Prepare one
source at a time if useful (this does not constitute a complete benchmark run):

```sh
python prepare_images.py --input-root /path/to/authorized/inputs --source nih-chestxray14
python prepare_images.py --input-root /path/to/authorized/inputs --source graz
```

Repeat `--source` to select multiple sources. Missing inputs or ambiguous filenames fail
before any output is written. Rendering errors exit nonzero, retaining successfully
prepared local images. Existing outputs are never silently trusted: use `--overwrite`
only when intentionally regenerating them. `--output` can relocate generated images,
but your inference process must resolve each task's relative `image` path accordingly.

## 3. Run your own reader/model and collect actual answers

For **every** task, supply its `system_prompt`, its `user_prompt`, and the image at its
relative `image` path to your reader/model. Read the image, not just the checklist.
Your own local model runner is sufficient; no particular framework is required.
Follow source-specific restrictions before any cloud inference, especially VinDr's DUA.

Save each real response as `completions/<task_id>.json`, containing one JSON object:

```json
{
  "findings": {},
  "diagnosis": "your one-line diagnosis",
  "next_step": "none",
  "impression": "your one-line impression"
}
```

The empty findings object above illustrates only the envelope, **not a valid completed
read**. Populate every requested checklist key with the value type that task requests:
booleans, words, numbers, a single `[x1,y1,x2,y2]` box, or a list of such boxes for keys
ending in `_boxes`. Box coordinates are pixels from the top-left of the prepared
1024×1024 image. Sides mean the patient's left/right. For box lists, mark every finding
you identify, not only the most obvious. `next_step` must be `emergency_action`,
`urgent_review`, `routine_followup`, or `none`. Do not add prose or Markdown fences.

Collect the full manifest in task order:

```sh
python collect_answers.py --completions completions --answers answers.jsonl
```

This command requires a real JSON completion for every task and checks the documented
payload shape. It never fabricates missing responses and never estimates correctness.
It refuses to overwrite a prior answer file. Alternatively, write the required JSONL
format directly in your own inference loop:

```python
import json
# task is the current tasks.jsonl record; response is your actual decoded read object.
row = {"task_id": task["task_id"], "completion": json.dumps(response)}
answers_file.write(json.dumps(row) + "\n")
```

Each `completion` is a **JSON string**, not a nested object. All 243 task IDs must occur
once. Collection success is only a structural check, not a score. The generic schema
cannot check task-specific checklist correctness without withheld reference data.

## 4. Restricted scoring (answer key required)

The public repository alone cannot reproduce correctness scores. There is no public
answer-key download, oracle, scoring API, or substitute reward. If you independently
have an authorized matching gold file, keep it **outside this repository** and run:

```sh
python score.py --answers answers.jsonl --gold /authorized/private/gold.json --output results/score.json
```

The existing `gold.json` interface is a JSON object keyed by task ID; each entry is the
case-gold object consumed by `read_scoring.grade({"gold": case_gold}, completion)`.
The gold IDs must match the supplied task manifest exactly. Do not mix another cohort's
answer key with this release. Missing submitted tasks fail. Duplicate/unknown task IDs
and unreadable submissions are rejected. The unchanged grader handles per-task parsing,
findings, box matching, diagnosis, and next-step checks. Reward is passed tasks / all
manifest tasks, not pass@k across multiple rollouts. A successfully computed report can
therefore contain failed tasks without being a command error.

Calling `python score.py --answers answers.jsonl` without `--gold` exits nonzero with an
explicit withheld-answer explanation. Task inference and answer collection need no gold.
Reports contain reference-bearing check details: treat them as private, not leaderboard
uploads. Existing report files are not overwritten.

## Publication safety

The initial release consists only of the named public files. `.gitignore` excludes
inputs, images, completions, answers, gold/oracle files, results, and common credentials.
Ignore rules are guardrails, not a security boundary: inspect every staged file and never
force-add restricted material. No license to third-party data or code is implied by
this repository; see `NOTICE.md`. No broad replacement license is assigned here.
