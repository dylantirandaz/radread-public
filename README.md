# RadRead

243 public tasks for frontier models reading radiographs.

[Leaderboard](https://dylantirandaz.com/radread-leaderboard/) · [Traces](https://dylantirandaz.com/radread-leaderboard/traces/) · [Results](https://huggingface.co/datasets/tirandazdylan/radread-public-results)

No images, gold, oracle answers or commercial environments. Not for clinical use.

## Run

Python 3.10+. Place authorized originals in `inputs/<source>/`, keeping original filenames. Read [data terms and rendering limits](NOTICE.md) first.

```sh
python -m pip install -r requirements.txt
python prepare_images.py --input-root inputs
```

Run your model with each `tasks.jsonl` prompt and image. Save JSON responses as `completions/<task_id>.json` ([schema](completion.schema.json)).

```sh
python collect_answers.py --completions completions --answers answers.jsonl
```

Scoring requires authorized private gold:

```sh
python score.py --answers answers.jsonl --gold /private/gold.json
```
