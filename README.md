# RadRead

243 radiograph studies. Each `tasks.jsonl` entry supplies system/user prompts, a checklist and an image path.

[Leaderboard](https://dylantirandaz.com/radread-leaderboard/) · [Traces](https://dylantirandaz.com/radread-leaderboard/traces/) · [Results](https://huggingface.co/datasets/tirandazdylan/radread-public-results)

## Protocol

A study passes only when every finding/localization, diagnosis and next-step check passes; check fractions are not study passes. Impression is unscored.

Published: five models × 243 studies × five attempts = 6,075 reads; temperature 0, 65,536-token limit, OpenAI xhigh reasoning. pass@k averages `1−C(5−c,k)/C(5,k)` across studies, where c counts passing attempts. C denotes combinations.

## Run

Python 3.10+. Put authorized originals in `inputs/<source>/`, preserving filenames; read [source terms/rendering limits](NOTICE.md).

```sh
python -m pip install -r requirements.txt
python prepare_images.py --input-root inputs
```

Supply each task's prompts/image to your model. Save [JSON](completion.schema.json) (`findings`, `diagnosis`, `next_step`, `impression`) as `completions/<task_id>.json`; answer every checklist key. Boxes use top-left-origin 1024×1024 pixel coordinates `[x1,y1,x2,y2]`.

```sh
python collect_answers.py --completions completions --answers answers.jsonl
```

Scoring requires authorized private gold; reward is the fraction of studies passing:

```sh
python score.py --answers answers.jsonl --gold /private/gold.json
```

No images, gold, oracle answers, inference harness or commercial environments. Exact reproduction remains limited by image provenance. Not for clinical use.
