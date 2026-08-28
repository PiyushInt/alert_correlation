# Evaluation Database (`ace_db_eval`)

## Purpose
`ace_db_eval` is a clean evaluation database stood up specifically for Phase 12 (Gate B) evaluation. Its corpus is the foundation for every metric and evaluation report in the final phases of the project.

## Ingestion Rule (Crucial)
**`ace_db_eval` is populated only by alerts arriving through the ingestion pipeline from injected faults. No manual inserts, no copies from `ace_db`, no constructed rows, ever.** 

This absolute constraint ensures that the Phase 12 evaluation corpus is describable in one sentence and remains uncontaminated by demo scripts, fabricated rows, or hand-written test setups.

## Population Mechanism
1. **Reference Data**: The database is seeded strictly from the YAML configuration files (`estate/inventory/components.yaml` and `estate/inventory/topology.yaml`). This seeds the `components`, `component_aliases`, and `dependencies` tables.
2. **Observational Data**: All observational tables (e.g., `alerts`, `incidents`, `incident_alerts`, `root_cause_candidates`, `incident_splits`, `incident_feedback`) start entirely empty. They are populated strictly at runtime by the application ingestion pipeline receiving real faults from the estate.

## Graph Limitations (Phase 13 Context)
The evaluation dependency map contains exactly 4 edges, all of which are `source='inventory'`. The single trace-derived edge present in `ace_db` (load-generator → frontend) was not reproduced, so the evaluation graph is entirely hand-seeded. Phase 13 must state this: **root cause ranking is evaluated against a map that encodes the expected answer, not one discovered from observed traffic.** Note also that the `load-generator` component exists with an alias but has no edges, making it an isolated node in the graph.

## Configuration
There is no `.env` file checked into this repository (only `.env.example`). Therefore, the `EVAL_DATABASE_URL` will resolve from its default in `src/ace/config.py`:
`postgresql+psycopg://ace_user:ace_password@localhost:5433/ace_db_eval`

## Component ID Disclaimer
Because `ace_db_eval` is freshly seeded from configuration files, the generated UUIDs for components will **not** match the UUIDs in the development database (`ace_db`). 
**Fresh seeding generates new IDs, so f134e20d, 9171e0ed and every other component ID appearing in existing docs, walkthroughs and DECISIONS.md refers to `ace_db` only.** 
Do not compare IDs across the two databases or assume identical UUIDs.

## Deduplication and Replay Isolation
Evaluation runs use `DEDUP_WINDOW=330`, differing from the default `3600`. The evaluation harness cannot run with dedup entirely disabled because the Phase 12/13 metrics measure the deduplication rate itself. A window of 330 seconds still collapses Alertmanager repeats within a single run, but successfully expires the deduplication cache before the next replay. Any duplicate-rate figure reported in Phase 13 must carry this qualifier.

Furthermore, replay isolation depends on runs being separated in time by more than `DEDUP_WINDOW`. Back-to-back replays executed closer than this window will merge into each other's incidents. This is correct pipeline behaviour, not a defect, but it constrains how the harness schedules runs.

### Scoping Constraint (Phase 12b)
With timed replays faithfully recreating the 300-second capture gaps, plus the required 305s correlation waits and 350s inter-run isolation sleeps, a single evaluation scenario takes exactly **43 minutes** of wall-clock time. Scaling this to eight scenarios for Phase 12b equates to approximately **5.7 hours**. Phase 12b must be scoped as a full day's execution, not an afternoon, unless parallelized across isolated database shards.
