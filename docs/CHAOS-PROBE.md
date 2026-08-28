# Chaos Probe Results

This document records the alerts produced by the chaos scripts in `estate/chaos/`. These observations were made against `ace_db` on 2026-08-28.

## Methodology
- Baseline `alerts` table count: 126
- Baseline `max(received_at)`: `2026-08-28 14:14:10.518151+00`
- Each script was run via `./estate/chaos/<script>.sh` for a standard duration (e.g., 300s).
- Wait time used for querying alerts post-execution: **60 seconds**. (Note: the estate has a detection lag floor near two minutes plus Alertmanager `group_wait`, so a 60s wait is technically insufficient to definitively prove absence of delayed alerts. Absences recorded below are unconfirmed).
- Alerts were collected by observing new rows in the `alerts` table. The probe generated 13 alert rows in total.

## Results

### 1. `fill_disk.sh`
- **Target**: `/mnt/valkey-data`
- **Events**:
  - 2 firing alerts (1 Zabbix `HighDiskUsage/DiskSpaceLow`, 1 Prometheus `HostHighDiskLoad/NodeFilesystemSpaceFillingUp` equivalent)
  - 2 resolution events (1 Zabbix, 1 Prometheus)
- **Incident Formed**: `e8f05af6-1efc-40a7-98fd-591ff4ab3c8f`
  - Members: 2
  - Source Tools: 2

### 2. `kill_service.sh`
- **Target**: `cart` service container
- **Events**:
  - 2 firing alerts (1 Blackbox `CartEndpointDown`, 1 Prometheus `CartDown`)
  - 2 resolution events (1 Blackbox, 1 Prometheus)
- **Incident Formed**: `782e3b45-91ff-406c-9363-12a7a44b164e`
  - Members: 2
  - Source Tools: 2

### 3. `inject_latency.sh`
- **Target**: Network traffic between `frontend` and `cart`
- **Events**:
  - 0 firing alerts
  - 0 resolution events
- **Incident Formed**: None.
- **Note**: UNCONFIRMED due to short wait time, however, inspection of `estate/prometheus/rules.yml` reveals that no Prometheus rules are configured to trigger on latency for its target. This means this fault is intrinsically undetectable by the current Prometheus configuration, so the lack of alerts is expected.

### 4. `partition.sh`
- **Target**: `cart` container network
- **Events**:
  - 2 firing alerts (1 Blackbox `CartEndpointDown`, 1 Prometheus `CartDown`)
  - 1 resolution event observed in window (Prometheus)
- **Incident Formed**: `6acc37ca-99b6-4d83-8b4e-36c1e3521991`
  - Members: 2
  - Source Tools: 2

### 5. `stress_cpu.sh`
- **Target**: `vm`
- **Events**:
  - 1 firing alert (Prometheus `HighCpuUsage`)
  - 1 resolution event (Prometheus)
- **Incident Formed**: `e9ded922-9ed0-4899-94d4-c98bd1cedff0`
  - Members: 1
  - Source Tools: 1

## Summary for Phase 12

- **`fill_disk.sh`** — USABLE. 2 firing alerts, cross-tool (zabbix + prometheus), one two-member incident. The primary cascade scenario.
- **`kill_service.sh`** — USABLE. 2 firing alerts, cross-tool (blackbox + prometheus), one two-member incident.
- **`partition.sh`** — NOT USABLE AS A DISTINCT SCENARIO. Produces alerts identical to `kill_service.sh`. Same target, same alertnames, no observable difference.
- **`inject_latency.sh`** — NOT USABLE. No Prometheus rule exists that can fire on latency for any target, so the fault is undetectable by construction. Not a timing artifact.
- **`stress_cpu.sh`** — USABLE, SINGLE-TOOL ONLY. 1 prometheus alert, one single-member incident. Cannot demonstrate cross-tool correlation. Correct shape for the mandatory off-graph noisy-neighbour scenario.

**Conclusion**: Three distinct detectable faults exist, two of them cross-tool. The plan's five cascade scenarios cannot all be built on this estate.

## Observation: Resolution Events
Resolution events are stored as alert rows and correctly never join incidents. The 51 unattached alerts recorded earlier in the project record include 31 with resolved status, most of which are resolution events rather than correlation misses. The genuine miss figure is therefore much lower than 52% and needs recomputing over firing alerts only before any recall number is quoted in Phase 13.
