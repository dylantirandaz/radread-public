---
document_version: '0.3'
verifier:
  name: radread-public-verifier
  default_strategy: pytest
  strategies:
    pytest:
      type: script
      command: ./test.sh
  rubric:
    combine: weighted_sum
    dimensions:
      correctness:
        weight: 1.0
        source: pytest
  outputs:
    reward_text: /logs/verifier/reward.txt
    reward_json: /logs/verifier/reward.json
    details_json: /logs/verifier/ctrf.json
---

## role:reviewer
A passing trial answers every task in the authorized key (300 for the released cohort).
Each task passes only when all deterministic checks pass: graded findings,
case-specific measurement/localization rules, required-lesion matching and extra-box
quotas, accepted diagnosis, and accepted next step. Extra findings keys are ignored, and
localization is not IoU-only. See `rubrics/verifier.md` for the rules implemented by the
single grader, `read_scoring.py`. The trial reward is the fraction of tasks passed.

## Runtime boundary

Build the agent image using `environment/` as the Docker build context, after locally
preparing authorized images. It contains only prompts, images, and generic skills; never
mount a verifier directory or answer key while the agent is running. No oracle submission
or answer key is distributed in the public release.

After the agent finishes, run the verifier in a separate trusted phase with the completed
workspace and `verifier/` mounted. Supply an authorized external key through `RADREAD_GOLD`
(an absolute path inside the verifier runtime is recommended). This overrides the private
default `verifier/gold.json`. Use the complete authorized key for all 300 released tasks.

Run `bash /path/to/verifier/test.sh /path/to/workspace`, or set `RADREAD_WORKSPACE` (default
`/root`). The optional workspace argument takes precedence. The workspace supplies
`answers.jsonl`; `LOGS_DIR` defaults to `/logs/verifier`. Relative paths
are resolved from the caller's directory. Missing gold or verifier setup failures stop
verification instead of producing a fabricated score.

Verifier logs/reports can expose expected findings and reference coordinates. Keep them
with the authorized evaluation artifacts, not in the public repository or agent transcript.
