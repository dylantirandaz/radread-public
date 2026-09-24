# RadRead

150 radiograph studies with a deterministic grader. Pixels and gold are not distributed. Not for clinical use.

[Leaderboard](https://dylantirandaz.com/radread-leaderboard/) · [Traces](https://dylantirandaz.com/radread-leaderboard/traces/) · [Results](https://huggingface.co/datasets/tirandazdylan/radread-public-results) · [Task instructions](envs/radread-public/task.md) · [Schema](envs/radread-public/completion.schema.json)

This package identifies **`public150-pass5-audit1`**, the correction of
`public150-pass5`: the same 150 studies and 3,750 frozen model responses, regraded
without new inference or cohort changes. It synchronizes all 150 task/source rows
and six-source image preparation, including the eight `com_` tasks that were staged
locally but not published in the prior benchmark-repository update. Website/results
publication alone does not update this environment package.

## Protocol

A study passes only if all finding/localization, diagnosis and next-step checks pass; impression is unscored.

The release protocol specifies five models, 150 studies and five provider-successful attempts per model/study: 3,750 scored reads, 750 per model. Settings are temperature 0, 65,536-token limit, xhigh reasoning for OpenAI and Claude, high for Gemini (its highest supported setting). pass@k uses `1−C(5−c,k)/C(5,k)`; c counts passing attempts. All five attempts count, including legitimate model failures; provider-successful does not mean passing the grader. The correction reuses the same prompts, images, inference settings and saved responses, but changes two source-backed reference entries and the laterality audit. This is not clinical validation.

Prioritize **pass@1** (mean per-study success over five attempts) and **5/5 reliability**
(studies passing every attempt). Rows are ordered by pass@1, retaining ties; pass@5 is
any success in five tries, not single-read reliability. The published uncertainty is a
paired percentile study bootstrap with 10,000 shared resamples of the 150 aligned study
IDs, seed 42: 95% intervals for each model's pass@1 and all pairwise pass@1 differences.
All five attempts stay together within each study; the 750 attempts per model are not
independent sampling units. Intervals describe this outcome-selected cohort, not clinical
population performance. A difference interval spanning zero does not establish a
definitive ordering.

The original cohort assembly retained 145 cases with five cached attempts per model from the previous 164-study cohort, plus five of its remaining 19 cases sampled with seed 42 before collecting new fifth-attempt outcomes. Those five are `com_frac_sing_143`, `com_graz_conj_18`, `com_graz_conj_9`, `com_graz_sing_141` and `com_nih_sing_43`. That assembly combined 3,725 cached reads with 25 new fifth reads (one per model for each sampled case). This correction regrades all 3,750 saved reads; it collects no additional responses.

The parent 164-study cohort was selected using reported outcomes from **all five models** to keep pass@4 strictly below 35%, after conservatively excluding 27 checklist, diagnosis or localization review flags from the historical 300-study cohort. Cached outcomes are reused for selection and scoring. The 150-study release therefore remains an **outcome-selected challenge subset**, not an independent holdout or evidence of general model deterioration on a fixed test. Review-flag exclusion is not clinical adjudication; disagreement does not prove reference error. Public traces contain passing answers.

Known template leakage, lexical rather than disease-level diagnosis grading and
`urgent_review` acceptance on 148/150 reference keys remain unresolved. Upstream finding
annotations do not clinically validate benchmark-authored diagnoses or next-step labels.
Source cohorts are too small for robust per-source comparisons. New normal cases,
urgency adjudication, disease-level diagnosis grading and larger source cohorts belong
to a separate version, not this correction.

Private selection provenance is frozen in `results/pass5_150.selection.json`. Pre-correction 150-study artifacts are archived under `results/cohorts/public150-pass5-pre-audit/`; the previous 164-study release is under `results/cohorts/public164-pass4/`, and the earlier 300-study snapshot under `results/cohorts/public300-pass4/`. These answer-bearing records are not part of this public package.

Source composition: 112 ChestDet, 14 NIH ChestXray14, 10 VinDr, 3 RSNA, 7 GRAZ and 4 FracAtlas studies.

## Prepare

Use Python 3.11–3.13 for evaluation. Read [source attribution, terms and rendering limits](NOTICE.md). Place authorized originals in `inputs/<source>/`, preserving filenames: `nih-chestxray14`, `chestdet`, `vindr`, `rsna`, `graz`, `fracatlas`. No datasets download automatically.

`envs/radread-public/environment/sources.jsonl` contains one source row for every task
study, including the original filenames for the eight previously unpublished `com_`
tasks; [NOTICE.md](NOTICE.md) lists those identifiers and the remaining provenance gaps.
The manifest identifies prepared files but does not establish exact upstream archive
versions or guarantee byte-identical reconstruction. In particular, original FracAtlas
archive versions and inherited JPEG-to-PNG equivalence remain unverified. VinDr requires
legitimately held equivalent processed PNGs, not guessed official-DICOM rendering.

```sh
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt -e environments/radread_public
python scripts/prepare_images.py --input-root inputs
```

Windows Git Bash activation: `source .venv/Scripts/activate`. Prepared images go to `envs/radread-public/environment/images/`.
The preparer resolves all six source directories recursively and refuses ambiguous
matches. Existing outputs require explicit `--overwrite`. For FracAtlas,
supply one released original JPEG per study, or a legitimately held prepared grayscale
1024×1024 PNG; the latter is preserved byte-for-byte without asserting upstream provenance.

## Evaluate

The correction requires only regrading existing responses; the inference command below
is for an optional fresh evaluation, not reproduction of the frozen response set.
Source/provider permission is required before API submission. Scored inference requires
independently authorized gold beforehand; keep it on the grading host, outside prompts
and agent images. Install Prime in isolation:

```sh
uv tool install prime==0.6.30
export PRIME_API_KEY=your-key
export RADREAD_GOLD=/private/gold.json
bash scripts/run_eval.sh anthropic/claude-opus-5 150 5 results/full/anthropic-claude-opus-5
python scripts/passk.py results/full --gold "$RADREAD_GOLD" --out results/leaderboard.json
```

Launcher uploads are disabled. Keep answer-bearing scoring reports private.
The public package supplies no case gold, raw private response archive, credentials or
private repository history. Public results/traces are descriptive release artifacts;
they are not an independently authorized reference key.

## Submit without gold

Follow the task instructions and schema; save completions as `completions/<task_id>.json`.

```sh
python scripts/collect_answers.py --completions completions --answers answers.jsonl
```

Collection is unscored. With authorized gold, score privately:

```sh
python scripts/score.py --answers answers.jsonl --gold /private/gold.json
```
