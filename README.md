# RadRead

243 radiograph studies, with the sandbox, installable evaluation environment and deterministic grader used by RadRead. Image pixels and case answer keys are not distributed.

[Leaderboard](https://dylantirandaz.com/radread-leaderboard/) · [Traces](https://dylantirandaz.com/radread-leaderboard/traces/) · [Results](https://huggingface.co/datasets/tirandazdylan/radread-public-results)

## Protocol

A study passes only when every finding/localization, diagnosis and next-step check passes; check fractions are not study passes. Impression is unscored.

Published: five models × 243 studies × five attempts = 6,075 reads; temperature 0, 65,536-token limit, OpenAI xhigh reasoning. pass@k averages `1−C(5−c,k)/C(5,k)` across studies, where c counts passing attempts. C denotes combinations.

## Layout

- [`envs/radread-public/`](envs/radread-public/): task instructions, 243 prompts/checklists, source identifiers, Dockerfile, skills and verifier.
- [`environments/radread_public/`](environments/radread_public/): the `verifiers` adapter; one image-and-text model call per study.
- [`scripts/`](scripts/): local image preparation, submission collection, evaluation and pass@k aggregation.

## Prepare

Python 3.11–3.13 for evaluation; image/submission utilities also support Python 3.10. Read [source terms and rendering limits](NOTICE.md), then place authorized originals in `inputs/<source>/`, preserving filenames. Sources: `nih-chestxray14`, `chestdet`, `vindr`, `rsna`, `graz`.

```sh
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt -e environments/radread_public
python scripts/prepare_images.py --input-root inputs
```

On Windows Git Bash, activate with `source .venv/Scripts/activate`. Prepared images go to `envs/radread-public/environment/images/`. No dataset is downloaded automatically.

Synthetic checks need no images, keys or model calls: `uv pip install pytest`, then `python -m pytest tests`.

## Evaluate with an authorized answer key

The scored adapter requires gold before inference; it never substitutes guessed answers or zero rewards. Supply an independently authorized key through `RADREAD_GOLD`, or `gold_path` when calling `load_environment`. Gold remains on the grading host, outside model prompts and the agent image. Check source/provider permissions before sending radiographs to an API.

```sh
uv tool install prime==0.6.30
export PRIME_API_KEY=your-key
export RADREAD_GOLD=/private/gold.json
bash scripts/run_eval.sh anthropic/claude-opus-5 243 5 results/full/anthropic-claude-opus-5
python scripts/passk.py results/full --gold "$RADREAD_GOLD" --out results/leaderboard.json
```

The launcher disables result uploads. Saved transcripts exclude image payloads. Local scoring reports may expose reference answers: keep them private. `RADREAD_PUBLIC_ROOT` selects a different task bundle; use `--env-root` for aggregation. Cost estimates use historical provider prices, not current quotes.

## Submit without an answer key

Use each task's prompts and image with your own reader/model. Save [completion JSON](envs/radread-public/completion.schema.json) (`findings`, `diagnosis`, `next_step`, `impression`) as `completions/<task_id>.json`; answer every checklist key. Boxes use top-left-origin 1024×1024 pixel coordinates `[x1,y1,x2,y2]`.

```sh
python scripts/collect_answers.py --completions completions --answers answers.jsonl
# Correctness scoring, unlike collection, requires authorized gold:
python scripts/score.py --answers answers.jsonl --gold /private/gold.json
```

For a sandbox run, build `envs/radread-public/environment/` only. Mount the [verifier](envs/radread-public/verifier/verifier.md) and gold after the agent finishes; do not expose them to the evaluated agent. This is RadRead's existing sandbox layout, not a native Harbor task.

No images, case gold, oracle answers, answer-bearing audit reports or commercial environments are included. Exact historical pixel reproduction remains limited by provenance described in `NOTICE.md`. Public traces already contain passing model answers; this is not an undisclosed holdout. Not for clinical use.
