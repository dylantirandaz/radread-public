# Pass criteria

A task passes when the submitted read satisfies every check at once:

1. **Graded findings correct.** Required booleans match exactly; other critical values use
   normalized labels. Measurement values must lie within the case's inclusive range.
   Extra findings keys are ignored rather than rejected.
2. **Localization accepted.** Single boxes may match the reference or an allowed alternative.
   Focal boxes pass if IoU meets the configured threshold (default 0.3 for single boxes,
   0.25 for box-list references), or their center is inside the reference expanded by half
   its width/height and their area is between 0.25 and 4 times the reference area, or at
   least 90% of their area is inside the reference and their area is at least 1% of it.
   Extent boxes also pass if they cover at least half the reference and their area is at
   most max(4 times the reference area, 5% of the 1024×1024 image).
3. **Required lesions found; spurious boxes within quota.** Box-list matching is one-to-one
   and maximizes required matches before optional matches. Optional reference boxes need
   not be found. Unmatched answered boxes must not exceed the case's quota. If both nodule
   and mass box sets exist, their references, answers, and quotas are pooled.
4. **Diagnosis accepted.** Normalized accepted labels and the grader's negation-aware
   clause matching determine acceptance; literal equality is not the only passing route.
5. **Next step accepted.** The action exactly matches an accepted next step. The impression
   is not scored.

Trial reward = tasks passed / tasks in the authorized key (243 for the released cohort).
Missing answers, unparseable lines, and malformed reads fail their tasks. There is no
partial task reward and no judge model. The adapter also reports per-check accuracy as a
diagnostic with zero reward weight. `../read_scoring.py` is the single scoring implementation.

The public release contains no answer key or oracle submission. An authorized key is
required at verification time; a missing or empty key is a setup error, not a zero score.
