# Phase 0 Capture Runbook

This guide outlines exactly how to bring up the estate, start the capture sink, inject a fault, and extract the real payloads.

## 0. Preflight Check
Before running any faults, ensure the estate is fully functional.
```bash
python estate/capture/preflight.py
```
**Expected Output:** PASS for all checks. Fix any FAIL before proceeding.

## 1. Start the Sink
In a new terminal window, start the capture sink. This must be running before the estate can forward any alerts.
```bash
python estate/capture/sink.py
```

## 2. Bring Up the Estate
In another terminal, bring up the estate following the layered approach.
```bash
cd estate
docker compose up -d valkey zabbix-db
sleep 15
docker compose up -d zabbix-server zabbix-web
sleep 15
docker compose up -d
```

## 3. Zabbix Provisioning
```bash
python estate/zabbix/provision.py
```

## 4. Run All Faults
```bash
cd estate/chaos
./run_all.sh
```
*Note the quiet window start/end times printed at the beginning.*

## 5. Measure and Report
Once all faults have run, stop the sink (`Ctrl+C`) and generate the metrics:
```bash
python estate/capture/measure.py --faults-file estate/captures/faults.jsonl --payloads-dir estate/captures/payloads --quiet-window <START> <END>
python estate/capture/naming_table.py --faults-file estate/captures/faults.jsonl --payloads-dir estate/captures/payloads
```
Fill out `docs/ESTATE.md` with the output.

## 6. Baseline Labeling
Pick one fault ID from `faults.jsonl` and run:
```bash
python estate/capture/label.py --fault-id <fault_id> --faults-file estate/captures/faults.jsonl --payloads-dir estate/captures/payloads
```
Open the generated CSV in `estate/captures/labels/`, manually label the `same_incident` column (Y/N), and then run:
```bash
python estate/capture/label.py --summarise estate/captures/labels/<fault_id>.csv
```
Record the result in `docs/ESTATE.md`.

## Detection Latency Budget (CartDown)
The current `CartDown` rule relies on `absent(dotnet_exceptions_total)`. Its detection latency budget is:
- **metric_expiration**: 90s
- **for**: 60s
- **scrape/eval jitter**: ~30s-90s
**Total latency**: ~4m
*Warning*: This is perilously close to the 5m fault window. Any fault shorter than ~4.5m risks a false negative, which will look like a tool failure when it's just slow detection.

## Zabbix Baseline Note
Zabbix is configured with exactly one trigger (`vfs.fs.size` on the `/mnt/valkey-data` volume) by design. It does not monitor container liveness, memory, or CPU for the estate's services. Therefore, it will report 0 alerts for faults like `kill_service` or `partition`. This is intentional: Zabbix is present as a minimal infrastructure baseline, reflecting a common real-world scenario where different tools cover different strata of the stack. Its zeros reflect its configuration scope, NOT a tool capability failure.
