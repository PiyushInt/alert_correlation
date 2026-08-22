# Phase 0 Capture Runbook

This guide outlines exactly how to bring up the estate, start the capture sink, inject a fault, and extract the real payloads.

## 1. Start the Sink
In a new terminal window, start the capture sink. This must be running before the estate can forward any alerts.
```bash
python estate/capture/sink.py
```
**Expected Output:**
```
Listening on port 8000 for captures...
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

## 3. Pre-flight Checks
1. **Prometheus Targets:** Visit `http://localhost:9090/targets` and confirm all jobs (demo-frontend, node-exporter, cadvisor, blackbox, etc.) show `UP`.
2. **Alertmanager Connection:** Visit `http://localhost:9090/status` and ensure Alertmanager is listed as an active target.
3. **Zabbix Provisioning:**
```bash
python estate/zabbix/provision.py
```
**Expected Output:**
```
Provisioning Zabbix...
[divergence_table] Zabbix Host / Items:
Host: docker-host-01
Items: CPU usage, Memory utilization, /valkey-data disk usage
...
```

## 4. Trigger the Gate A Cascade
```bash
cd estate/chaos
./fill_disk.sh
```

## 5. Observe the Sink
Switch back to the terminal running `sink.py`. You should see incoming requests.
- **Expected Lag:**
  - **Prometheus/Alertmanager:** ~15-45 seconds. Prometheus scrapes every 15s, and Alertmanager has a 10s `group_wait` before firing the webhook.
  - **Zabbix:** ~30-60 seconds, depending on the item polling interval configured in Zabbix.
- **Wait Time:** Wait at least **3 minutes** after running the chaos script to conclude whether an alert has failed to arrive.

## 6. Compare Payloads
Once alerts have arrived, stop the sink (`Ctrl+C`) and run the comparison script:
```bash
python estate/capture/compare.py disk_fill
```
**Expected Output:** A markdown table displaying the alerts side-by-side, along with the counts to paste into `docs/ESTATE.md`.

## Troubleshooting missing alerts

* **Prometheus alerts missing:**
  - Check `http://localhost:9090/rules` to see if the rule evaluated to true.
  - Check `http://localhost:9090/alerts` to see if it is pending/firing.
  - Check Alertmanager UI `http://localhost:9093` to see if it received the alert and if there are delivery errors to the webhook.

* **Zabbix alerts missing:**
  - Check Zabbix Web UI `http://localhost:8082` -> Monitoring -> Problems.
  - Ensure the item is actively polling the `/valkey-data` volume.
  - Check Administration -> Media types -> Correlation Engine Webhook for any delivery errors.

* **Blackbox alerts missing:**
  - Check Prometheus `http://localhost:9090/targets` to ensure the blackbox probe is successful during steady state.
  - The probe only fails when the frontend goes down, which requires the disk fill to successfully cascade to valkey -> cart -> checkout -> frontend.
