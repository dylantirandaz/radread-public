# RadRead

243 radiograph studies with a deterministic grader. Pixels and gold are not distributed. Not for clinical use.

[Leaderboard](https://dylantirandaz.com/radread-leaderboard/) · [Traces](https://dylantirandaz.com/radread-leaderboard/traces/) · [Results](https://huggingface.co/datasets/tirandazdylan/radread-public-results) · [Task instructions](envs/radread-public/task.md) · [Schema](envs/radread-public/completion.schema.json)

## Protocol

A study passes only if all finding/localization, diagnosis and next-step checks pass; impression is unscored.

Published: five models × 243 studies × five attempts = 6,075 reads; temperature 0, 65,536-token limit, OpenAI xhigh reasoning. pass@k averages `1−C(5−c,k)/C(5,k)` across studies; c counts passing attempts, C denotes combinations. Public traces contain passing answers: this is not a hidden holdout.

## Prepare

Use Python 3.11–3.13 for evaluation. Read [source attribution, terms and rendering limits](NOTICE.md). Place authorized originals in `inputs/<source>/`, preserving filenames: `nih-chestxray14`, `chestdet`, `vindr`, `rsna`, `graz`. No datasets download automatically.

```sh
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -r requirements.txt -e environments/radread_public
python scripts/prepare_images.py --input-root inputs
```

Windows Git Bash activation: `source .venv/Scripts/activate`. Prepared images go to `envs/radread-public/environment/images/`.

## Evaluate

Source/provider permission is required before API submission. Scored inference requires independently authorized gold beforehand; keep it on the grading host, outside prompts and agent images. Install Prime in isolation:

```sh
uv tool install prime==0.6.30
export PRIME_API_KEY=your-key
export RADREAD_GOLD=/private/gold.json
bash scripts/run_eval.sh anthropic/claude-opus-5 243 5 results/full/anthropic-claude-opus-5
python scripts/passk.py results/full --gold "$RADREAD_GOLD" --out results/leaderboard.json
```

Launcher uploads are disabled. Keep answer-bearing scoring reports private.

## Submit without gold

Follow the task instructions and schema; save completions as `completions/<task_id>.json`.

```sh
python scripts/collect_answers.py --completions completions --answers answers.jsonl
```

Collection is unscored. With authorized gold, score privately:

```sh
python scripts/score.py --answers answers.jsonl --gold /private/gold.json
```
