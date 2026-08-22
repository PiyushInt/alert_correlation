# Estate Metrics and Characterisation (TEMPLATE)

## Measured Values
* Steady-state alert rate: 
  * Prometheus: 0.0 /hour
  * Zabbix: 0.0 /hour
  * Blackbox: 0.0 /hour
  ```bash
  python estate/capture/measure.py --faults-file estate/captures/faults.jsonl --payloads-dir estate/captures/payloads --quiet-window 2026-08-21T15:03:00+00:00 2026-08-21T15:33:00+00:00
  ```
* Peak burst during fault: 
  * Prometheus: 1 /minute
  * Zabbix: 1 /minute
  * Blackbox: 1 /minute
* Alerts per fault:
  * disk_fill: Prometheus 1, Zabbix 1, Blackbox 0
  * kill_service: Prometheus 6, Zabbix 0, Blackbox 2
  * partition: Prometheus 1, Zabbix 0, Blackbox 3
  * cpu_saturation: Prometheus 3, Zabbix 0, Blackbox 1
  * inject_latency: Prometheus 0, Zabbix 0, Blackbox 0
* Duplicate rate: 
  * 5 min: 47.5 %
  * 1 hour: 72.5 %
* Unresolvable component identifiers: 
  * 35.0 % (26/40 resolved)

## Naming Divergence
| Component | Prometheus | Zabbix | Blackbox |
|---|---|---|---|
| valkey | node-exporter:9100 | docker-host-01 | (none) |
| cart | Unknown | (none) | cart:8080 |
| vm | node-exporter:9100 | (none) | (none) |

*\* Note: The checkout service is permanently broken due to product-catalog crashing. The HighErrorRate rule baseline is consistently > 0.85, meaning the rule is unusable for capturing kill_service faults cleanly.*
```bash
python estate/capture/naming_table.py --faults-file estate/captures/faults.jsonl --payloads-dir estate/captures/payloads
```

## Baseline Relatedness
Baseline relatedness (kill_service, 8 alerts, 28 pairs): 6 CartDown firings are duplicates handled by Stage 2. Beyond deduplication, the fault produced 3 distinct alerts. The frontend probe failure (`http://frontend:8080/api/cart`) shares neither component nor text with the cart alerts — no signal except dependency proximity can group them. Single observation, one fault type.

## Detection Lag Budget
* **Otel-Collector Expiration**: `metric_expiration: 60s`
* **Prometheus Rule Duration**: `for: 1m`
* **Total Expected Detection Lag**: ~2 minutes
* **Impact**: Faults shorter than ~2.5 minutes may be missed by Prometheus liveness rules like `CartDown` entirely.
