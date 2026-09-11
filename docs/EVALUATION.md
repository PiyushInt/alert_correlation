# Evaluation Protocol

This document outlines the protocol for labelling, running, and scoring scenarios for the Alert Correlation Engine.

## Ground Truth Labelling Protocol

1. **Who writes ground truth:** The engineers designing the scenario must define the ground truth.
2. **When it is written:** Ground truth is written *before* the scenario is ever run through the pipeline. It must represent what *should* happen, not what *does* happen.
3. **Immutability:** Ground truth is immutable. It is never adjusted to match the pipeline's output.
4. **Disagreements:** If the pipeline's output disagrees with the ground truth, the resolution is either to improve the pipeline or to acknowledge the failure as a known defect. We do not relax ground truth to artificially improve scores.

## How to Add a Scenario

To add a new scenario:
1. Define the YAML in `eval/scenarios/<family>/<name>.yaml`.
2. Specify the `fault_script`, `duration_seconds`, and target `arguments`.
3. Provide the `expected_incidents` ground truth block before capturing data.
4. Run `python eval/runner.py --scenario <path> --capture` to collect raw payloads.
5. The next CI run or `eval/scorer.py` invocation will evaluate the new scenario against the pipeline automatically.

## Note on Synthetic Data
**Important**: `ace_db_eval` contains one deliberately merged incident for a metric demonstration (`unrelated_concurrent`). Do not assume all database state represents natural pipeline behaviour; this forced merge was created via the API to validate the over-merge rate metric.
