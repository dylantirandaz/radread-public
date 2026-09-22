---
version: "1.0"
metadata:
  category: natural-science
  difficulty: hard
  tags: [radiology, vision-language, localization]
agent:
  timeout_sec: 21600
verifier:
  timeout_sec: 600
environment:
  build_timeout_sec: 600
  cpus: 2
  memory_mb: 4096
  storage_mb: 10240
  allow_internet: false
---

## prompt

You are the radiologist on call. In `/root` you will find `tasks.jsonl` (243 radiology reading
tasks) and `images/` (one 1024x1024 radiograph per task). Each task line holds a `task_id`, a
`system_prompt`, a `user_prompt` (request form plus findings checklist), and the task's `image`
path relative to `/root`.

For EVERY task, read its image carefully and systematically, then append one line to
`/root/answers.jsonl`:

{"task_id": "<the task id>", "completion": "<your read as a single JSON string>"}

where the completion is ONE JSON object and nothing else:

{"findings": {<each requested checklist key>: true/false, a word, a number, a single
[x1,y1,x2,y2] box, or (for keys ending in _boxes) a LIST of [x1,y1,x2,y2] boxes},
"diagnosis": "<one line>", "next_step": "emergency_action | urgent_review | routine_followup | none",
"impression": "<one line>"}

Rules: answer every checklist key with only what the image shows; sides are the PATIENT's
left/right as a radiologist reports them; box coordinates are [x1,y1,x2,y2] pixels from the
top-left corner; for box lists, box every finding you identify, not only the most obvious.
A missing task, an unparseable line, or a malformed read fails that task. The trial reward is
the fraction of tasks passed. The `radread` skill in `/root/skills` documents the schema.

## Host runtime

The public bundle supplies task prompts and generic scoring code, not images, answer keys,
or oracle submissions. Prepare authorized images locally before building the agent image
with `environment/` as its context. The image contains only tasks, images, and skills.

Keep the verifier and any authorized answer key inaccessible during the agent phase.
After the agent finishes, mount the completed workspace and verifier in a trusted
verification phase; set `RADREAD_GOLD` to the authorized key's path in that runtime and
run `bash /path/to/verifier/test.sh /path/to/workspace`. The workspace contains
the submitted `answers.jsonl`. Use the complete authorized key for all 243 tasks.
`RADREAD_WORKSPACE` is the alternative to the optional workspace argument; its default is
`/root`. Existing private bundles may use `verifier/gold.json` when `RADREAD_GOLD` is unset.
