# Project: Alert Correlation Engine

## Working agreement — read this first, every task

- Produce a plan and wait for approval before writing code.
- Stay inside the current phase's file allowlist. If a fix seems to need a file outside it,
  STOP and report instead of editing.
- If you are unsure whether an edit is correct, STOP AND ASK. Do not write the doubt into a
  code comment and execute anyway.
- NEVER claim a phase or task is complete without running the acceptance checks and pasting
  the real output. "It should work" is not evidence. Pasted terminal output is not evidence; output must never be edited, abridged, or reformatted; acceptance is verified via CI and the GitHub diff view.
- NEVER batch operations I asked you to do one at a time.
- NEVER write a rule, query, or config referencing a metric, label, or field you have not
  first confirmed exists. Query it, paste the non-empty result, then write.
- Do not refactor, rename, or "improve" code from earlier phases unless asked.
- Ambiguity: ask one question rather than guess.
- No mock data or stubbed returns in a component being marked complete.
- Acceptance for any phase is ./scripts/check.sh printing "All checks passed!", pasted in full. Not pytest alone. CI evidence must be gh run view <id> --json conclusion,headSha, and the headSha must match HEAD.
- NEVER run a hold-out scenario (`eval/holdout/`). Running one during development destroys
  the evidence it exists to provide.
- Every dependency goes into pyproject.toml in the SAME task that introduces
  it. Never pip install or uv add without recording it. check.sh runs against
  the installed venv; CI builds from pyproject alone. Three phases of green
  local checks masked a red pipeline because of this.
- Before fixing a CI failure, run `gh run view --log-failed` and read the
  actual error. Runs #10 and #12 were fixes pushed without reading the log;
  both introduced new failures. Diagnose, then change. Before pushing a fix for a CI failure, read the failure log and name the failing step. Do not push a speculative fix.
- A phase is not complete until CI is green on main. Phases 6 and 7 were
  tagged against a red pipeline.

## Environment

LOCAL development. Application runs in `./.venv` against local PostgreSQL 16 and Redis.
Alerts come from a local open-source monitoring estate under `estate/`, not from production.
Code lives in a private remote repo.

Python:
- Verify the venv before installing: `which python` must resolve to `<project>/.venv/bin/python`.
  If not, STOP and say so. Never install into system Python.
- `python -m pip install ...`; pin every dependency in pyproject.toml.
- No application Dockerfile. The estate is containerised; our app is not.

Git:
- You may `git add` and `git commit` on the current phase branch. Conventional commits.
- NEVER push, merge, rebase, tag, force-push, or commit to `main`. A human does that. The agent must never merge to `main`, never create or merge a pull request, and never commit directly to `main` — including when a prompt describes those steps as context.
- NEVER commit `.env`, credentials, tokens, or anything under `logs/`, `results/`,
  `holdout-results/`, `notifications/`, `estate/data/`, `estate/captures/`, `eval/captures/`,
  `.venv/`.
- Run `git status` before committing; confirm nothing gitignored is staged.
- New config variables go in `.env` and in `.env.example` as a placeholder.

## Repository layout — follow exactly, do not invent directories

Package root is `src/ace/`. Import as `ace.correlation.decision`, etc.

```
src/ace/
  main.py config.py logging.py metrics.py
  api/          health, incidents, feedback, dependencies, root_cause, webhooks/
  db/           session, base, models/, repositories/
  ingestion/    adapters/ (base, alertmanager, zabbix, blackbox), models, severity, resolver
  queue/        streams, consumer
  bypass/       health, canary, router
  pipeline/     fingerprint, dedup, damping
  dependency/   otlp, extractor, inventory, graph, reachability, health
  correlation/  engine, decision, containment, window, lifecycle, text_normalise, signals/
  ranking/      ranker, scoring, confidence, features/
  notification/ dispatcher, render, senders/
  itsm/         sync, adapters/
  jobs/         cooccurrence, graph_refresh
  workers/      ingest_worker, correlation_worker

tests/    mirrors src/ace/ one-for-one, plus fixtures/
estate/   the monitoring estate — NEVER imports from src/ace/
eval/     the harness — imports src/ace/, never the reverse
alembic/  migrations
scripts/  operational scripts, not application code
docs/     DECISIONS, PROGRESS, ESTATE, CONTEXT, EVALUATION, TUNING, HOLDOUT, REPORT, RUNBOOK
```

LAYOUT RULES
- One concept per module. Do not create a file outside this tree without saying why first.
- No `utils.py`, `helpers.py`, or `common.py`. Name the concept.
- These modules are PURE — data in, data out, NO database, Redis, HTTP, clock, or randomness:
  `correlation/decision.py`, `correlation/containment.py`, `correlation/text_normalise.py`,
  `pipeline/fingerprint.py`, `ranking/scoring.py`, `ranking/features/*`
  All I/O lives in `engine.py`, `ranker.py`, and the workers. This is what makes replay-based
  evaluation possible. A DB call inside any of them is a defect, not a shortcut.
- `config.py` holds EVERY tunable. A numeric literal in `correlation/`, `ranking/`, or
  `pipeline/` is a defect.
- Dependency direction: api → correlation/ranking → dependency/db. Never the reverse.
- `ingestion/resolver.py` is shared by ingestion AND dependency. Import it; never copy it.
- Adding a monitoring tool = one new file in `ingestion/adapters/` + one webhook route. If it
  needs changes anywhere else, the adapter interface is wrong — stop and report.

## What this system does

Operations teams receive thousands of alerts a week; only a small fraction are genuinely
separate problems. The rest are duplicate reports of one failure, arriving FROM DIFFERENT
TOOLS and different layers of the stack.

Worked example from the design doc: a database server fills its disk at 2:14 AM. Within
ninety seconds, eight alerts fire from six different tools. There is one problem. This system
turns those eight pages into one page with the cause attached.

CROSS-TOOL IS THE POINT. A version that only ingests Prometheus does not solve the stated
problem. Component identity resolution across tools that name things differently is core, not
plumbing. Phase 0 measured a 35% unresolved component rate as the starting point — see below.

## The five-stage pipeline

1. Normalise    — one format, matched to a component
2. Deduplicate  — collapse repeat alerts
3. Damp flapping— suppress oscillating alerts
4. Correlate    — group alerts into incidents        <- core value
5. Rank cause   — top three candidates with evidence <- core value

Stages 1-3 are mechanical. Stages 4-5 are where the difficulty sits.

## The four correlation signals

- Same component          — both alerts refer to the same server or service
- Dependency proximity    — components within three hops in the map
- Text similarity         — alert labels and messages highly similar
- Historical co-occurrence— these types fire together far more often than chance

Built and measured SEPARATELY so each contribution is known. Never merge two signals into one
scoring function without being told to.

## Containment — read before touching correlation

Signals propose. Containment disposes. The rule is NOT bare "any signal fires":

1. CENTROID, NOT ANY-MEMBER. An alert joins an incident only if it scores against the incident
   as a whole. Chaining A-B on text and B-C on proximity must NOT produce {A,B,C}.
2. NO TRANSITIVE CLOSURE. Grouping is never connected-components over a pairwise graph.
3. DIAMETER CAP. Beyond MAX_INCIDENT_HOPS, stop accreting. Further alerts open a NEW incident,
   LINKED as "possibly related", not merged.
4. SIZE CAP. Beyond MAX_INCIDENT_ALERTS, stop accreting and flag. One incident containing
   everything is the failure mode that destroys operator trust.
5. HARD PARTITIONS. Never merge across environment or tenant. Refusals, not scores.
6. SPLIT EXISTS. Every merge is reversible and audited.

Every signal added raises recall AND raises over-merge. Containment is what keeps the
over-merge target reachable. NEVER relax containment to hit a recall number.

## Availability — fail open

This sits between monitoring and on-call. If it fails silently it causes the outage it was
built to prevent.

- Pipeline unhealthy, lagging beyond MAX_PIPELINE_LAG, or any dependency down -> alerts route
  RAW to the notifier, unmodified. Degraded, never silent.
- A canary alert is injected on a fixed interval and must be seen emerging. If not, bypass
  activates automatically. Deadman, not dashboard.
- Notifications carry a visible banner when degraded or bypassed.
- Severity >= CRITICAL_BYPASS_SEVERITY notifies IMMEDIATELY, never waits for a window.
- Redis: persistence on, `noeviction`.

## Operating envelope — MEASURED IN PHASE 0, NOT ASSUMED

| Parameter                           | Value                                                     | Source  |
| ----------------------------------- | --------------------------------------------------------- | ------- |
| Steady-state alert rate             | 0.0 /hour (30-min idle window, all three tools)           | Phase 0 |
| Peak burst during an injected fault | 1 /minute                                                 | Phase 0 |
| Measured duplicate rate             | 47.5% within 5 min; 72.5% within 1 hour                   | Phase 0 |
| Unresolved component identifiers    | 35% (26 of 40 resolved)                                   | Phase 0 |
| Detection lag floor                 | ~2 min (collector metric_expiration 60s + rule `for: 1m`) | Phase 0 |
| Alerts per fault, per tool          | see below                                                 | Phase 0 |

Alerts per fault (Prometheus / Zabbix / Blackbox):

| Fault          | P   | Z   | B   |
| -------------- | --- | --- | --- |
| disk_fill      | 1   | 1   | 0   |
| kill_service   | 6   | 0   | 2   |
| partition      | 1   | 0   | 3   |
| cpu_saturation | 3   | 0   | 1   |
| inject_latency | 0   | 0   | 0   |

These are demo-estate numbers. They size the build; they are NOT claims about production.
Every reported metric carries the qualifier "on the OpenTelemetry Demo under injected faults".

### The cross-tool evidence (Gate A)

One disk-fill fault, two independent tools, 135 seconds apart, with genuinely divergent
identifiers for the same filesystem:

| Component        | Prometheus           | Zabbix           | Blackbox                                     |
| ---------------- | -------------------- | ---------------- | -------------------------------------------- |
| /mnt/valkey-data | `node-exporter:9100` | `docker-host-01` | (none)                                       |
| cart             | (unlabelled)         | (none)           | `cart:8080`, `http://frontend:8080/api/cart` |
| vm               | `node-exporter:9100` | (none)           | (none)                                       |

No shared substring between `node-exporter:9100` and `docker-host-01`. Fuzzy matching alone
will NOT connect them — Phase 4's resolver needs explicit alias handling. This is the real
cross-tool problem the project exists to solve, and it is the test data for Phase 4.

## Complexity triggers — do not build ahead of these

| Deferral                                | Trigger                                    |
| --------------------------------------- | ------------------------------------------ |
| NetworkX -> custom adjacency arrays     | graph > 10k nodes OR p99 traversal > 50 ms |
| Brute-force text compare -> MinHash/LSH | > 500 open-incident alerts in the window   |
| Single machine -> Kubernetes            | never, for this project                    |

At demo scale most of these will NOT fire. If an acceptance criterion asks you to prove a
technique is faster and it is not at the measured scale, report that honestly and keep the
simpler implementation. Shipping LSH over 40 alerts to look sophisticated is a defect.

## Scope

IN:  receiving alerts from multiple existing monitoring tools; building the dependency map
     from observed traffic; grouping alerts into incidents; ranking root cause with evidence;
     notification and ITSM ticket sync.

OUT: collecting metrics/logs ourselves; dashboards and visualisation; ticketing and service
     desk workflow; automatic remediation; security threat detection.

If a task seems to need something from the OUT list, stop and say so.

## Tech stack (fixed — do not substitute)

Python 3.12, FastAPI, Pydantic, Uvicorn | Redis Streams + Redis key-value | PostgreSQL 16,
SQLAlchemy, Alembic | NetworkX | xxhash, datasketch, mlxtend, pyroaring, rapidfuzz |
Alertmanager, Zabbix, Blackbox exporter, OTLP | pytest, hypothesis, ruff, mypy, pre-commit,
GitHub Actions.

Only the application layer is written by us.

## Success metrics

| Metric                    | Meaning                                         | Target                   |
| ------------------------- | ----------------------------------------------- | ------------------------ |
| Noise reduction           | alert volume shrink vs measured baseline        | 70%+                     |
| Grouping precision        | of what we grouped, how much belonged           | 85%+                     |
| Grouping recall           | of what should have grouped, how much we caught | 75%+                     |
| Over-merge rate           | two real incidents merged into one              | <=5%                     |
| Root cause, top 3         | true cause in the top three                     | 80%+                     |
| Cross-tool grouping rate  | multi-tool alert sets correctly unified         | tracked                  |
| Added latency             | delay before first notification                 | <= envelope              |
| Unresolved component rate | alerts we could not map to a component          | < 5% (from 35% baseline) |

Scored on the TUNING set at Gate B and the FROZEN HOLD-OUT set at Gate C. Gate C governs.

## Known estate limitations — do not treat these as bugs to fix

Recorded in `docs/CONTEXT.md`. Summarised here because they shape what any phase can prove:

- No production alert feed. The estate is the entire evidence base.
- `product-catalog` crash-loops on startup; the image is distroless so the cause is
  undiagnosable. Removed permanently.
- Consequently `checkout` returns 500s permanently and is EXCLUDED from all measurements.
  Any rule on frontend error rate has a poisoned baseline.
- `cart` exports no request/duration metrics, only `dotnet_exceptions_total` and feature-flag
  metrics. `HighLatency` was cut for lack of a metric source.
- Blackbox does not detect partial degradation: the frontend returns 200 with cart dead.
- ~2 minute detection lag floor. Faults shorter than ~2.5 min may be missed entirely.
- 4 fault types measured, one topology, one labeller.
- `cadvisor` and `toxiproxy` removed for memory (8 GB host, 5 GB Colima VM).

## Engineering rules

- Full type hints, mypy strict on `src/`.
- Structured JSON logging to stdout and `./logs/app.log`, trace id carried end to end.
- Alembic migration for every schema change. No manual DDL.
- pytest for units; hypothesis for grouping invariants.
- `docs/DECISIONS.md`: date, decision, alternatives rejected, reason.
- `docs/PROGRESS.md`: a paragraph per phase.

## Database safety — non-negotiable
- NEVER run `alembic downgrade`, DROP, TRUNCATE, or DELETE against ace_db. Not to reset
  state, not to get a clean run, not for any reason. If a task seems to require it, STOP
  and ask.
- Before any task that runs against the live database, run scripts/db_snapshot.sh and
  paste the resulting filename as the first line of the walkthrough.
- Report row counts for alerts, incidents and incident_alerts at task start and task end.
  Any decrease is a task failure regardless of the finding.
- The alerts table is an immutable ledger. Investigations read it. They never reset it.
- No ad-hoc scripts connecting to the live database outside the test harness.

## Database access

Four connection strings exist across two databases (`ace_db` for development, `ace_db_eval` for Phase 12 evaluation). Use the correct one.

Investigation, verification, and any read of the ledger:
  postgresql://ace_readonly:ace_readonly@localhost:5433/ace_db
  postgresql://ace_readonly:ace_readonly@localhost:5433/ace_db_eval

This role has SELECT only. Writes fail at the database with a permission error.

Application runtime and Alembic migrations only:
  postgresql+psycopg://ace_user:ace_password@localhost:5433/ace_db
  postgresql+psycopg://ace_user:ace_password@localhost:5433/ace_db_eval

Never use the `ace_user` DSN for investigation, verification, or ad-hoc scripts on either database. If a task appears to require a write outside a migration, stop and ask. The strict safety rules apply equally to `ace_db_eval`.

## What counts as evidence
- Evidence is output produced by a command run in THIS task, pasted raw.
- The prompt's description of a symptom is NOT evidence. Quoting it back is circular.
- What the source code implies SHOULD happen is NOT evidence that it DID happen.
- If a check was run and produced nothing, say so in words. Silence about a
  command you ran is a task failure.

## Task hygiene — added after task 8.9
- Exactly ONE snapshot per task, as the first command. Report that filename. Do not
  take further snapshots during the task.
- If you need clean database or Redis state to demonstrate something, STOP and ask.
  A test that requires an empty ledger is designed wrong. Wiping state to escape an
  error you caused is never the answer — investigate the error.
- Never run flushdb, or any command that clears Redis, against the running estate.
- Acceptance evidence comes from the estate. Hand-posted curl payloads, sed-edited
  fixtures, and fabricated timestamps are not acceptance evidence. If the estate
  cannot produce the condition, say so and stop.
- Never change config at runtime to make a test pass. Say so and stop.
- Never delete a branch, run git reset --hard, git clean, or discard uncommitted work.
  A rejected task's work is EVIDENCE. If you think something should go, say so and stop.
- Never commit command output files, scratch directories, or test artifacts.
- Commit your work on the phase branch BEFORE reporting a task complete. End every
  walkthrough with `git log --oneline -1` and `git status`, pasted. A branch with no
  commits is not a completed task, whatever the summary says.
