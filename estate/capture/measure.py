import os
import json
import sys
import argparse
import datetime
from collections import defaultdict

def parse_iso(dt_str):
    if not dt_str: return None
    dt_str = dt_str.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(dt_str)

def get_tool(payload):
    path = payload.get("path", "")
    if "zabbix" in path: return "Zabbix"
    if "alertmanager" in path:
        raw = payload.get("raw_body", "")
        body = json.loads(raw) if raw else {}
        for al in body.get("alerts", []):
            if "blackbox" in al.get("labels", {}).get("job", "") or "probe" in al.get("labels", {}).get("alertname", "").lower():
                return "Blackbox"
        return "Prometheus"
    return "Unknown"

def extract_alerts(payload, tool):
    alerts = []
    raw = payload.get("raw_body", "")
    body = json.loads(raw) if raw else {}
    ts = parse_iso(payload.get("received_at"))
    
    if tool == "Zabbix":
        inner = {}
        try:
            inner = json.loads(body.get("value", "{}"))
        except:
            pass
        alerts.append({
            "tool": tool,
            "name": inner.get("trigger_name", "Unknown"),
            "component": inner.get("host", ""),
            "ts": ts
        })
    elif tool in ["Prometheus", "Blackbox"]:
        for al in body.get("alerts", []):
            labels = al.get("labels", {})
            comp = labels.get("instance") or labels.get("pod") or labels.get("host") or ""
            alerts.append({
                "tool": tool,
                "name": labels.get("alertname", "Unknown"),
                "component": comp,
                "ts": ts
            })
    return alerts

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--faults-file", default=os.path.join(REPO_ROOT, "estate", "captures", "faults.jsonl"))
    parser.add_argument("--payloads-dir", default=os.path.join(REPO_ROOT, "estate", "captures", "payloads"))
    parser.add_argument("--quiet-window", nargs=2, metavar=("START", "END"), help="ISO8601 start and end")
    args = parser.parse_args()
    
    if not os.path.exists(args.payloads_dir) or not os.listdir(args.payloads_dir):
        print("INSUFFICIENT DATA: Payloads directory missing or empty")
        return
        
    all_payloads = []
    for fname in os.listdir(args.payloads_dir):
        if not fname.endswith(".json"): continue
        with open(os.path.join(args.payloads_dir, fname), "r") as f:
            try:
                all_payloads.append(json.load(f))
            except:
                pass
                
    if not all_payloads:
        print("INSUFFICIENT DATA: No valid payloads found")
        return
        
    flat_alerts = []
    for p in all_payloads:
        tool = get_tool(p)
        flat_alerts.extend(extract_alerts(p, tool))
        
    if not flat_alerts:
        print("INSUFFICIENT DATA: No alerts extracted")
        return
        
    flat_alerts.sort(key=lambda x: x["ts"])
    
    # Total alerts
    totals = {"Prometheus": 0, "Zabbix": 0, "Blackbox": 0}
    for a in flat_alerts:
        totals[a["tool"]] += 1
        
    # Steady state
    steady_state_hourly = {"Prometheus": 0.0, "Zabbix": 0.0, "Blackbox": 0.0}
    if args.quiet_window:
        qw_start = parse_iso(args.quiet_window[0])
        qw_end = parse_iso(args.quiet_window[1])
        quiet_alerts = [a for a in flat_alerts if qw_start <= a["ts"] <= qw_end]
        duration_hrs = (qw_end - qw_start).total_seconds() / 3600.0
        if duration_hrs > 0:
            for a in quiet_alerts:
                steady_state_hourly[a["tool"]] += (1.0 / duration_hrs)
                
    # Fault analysis
    peak_per_min = {"Prometheus": 0, "Zabbix": 0, "Blackbox": 0}
    fault_counts = {}
    fault_count = 0
    
    if os.path.exists(args.faults_file):
        with open(args.faults_file, "r") as f:
            for line in f:
                if not line.strip(): continue
                fault = json.loads(line)
                fault_count += 1
                fs = parse_iso(fault["start_time"])
                fe = parse_iso(fault["end_time"])
                f_alerts = [a for a in flat_alerts if fs <= a["ts"] <= fe + datetime.timedelta(seconds=60)]
                
                if fault["fault_type"] not in fault_counts:
                    fault_counts[fault["fault_type"]] = {"Prometheus": 0, "Zabbix": 0, "Blackbox": 0}
                
                # count per tool
                for a in f_alerts:
                    fault_counts[fault["fault_type"]][a["tool"]] += 1
                    
                # peak per minute sliding window
                for tool in set(a["tool"] for a in f_alerts):
                    t_alerts = [a for a in f_alerts if a["tool"] == tool]
                    max_in_60s = 0
                    for i, a1 in enumerate(t_alerts):
                        count = sum(1 for a2 in t_alerts[i:] if (a2["ts"] - a1["ts"]).total_seconds() <= 60)
                        max_in_60s = max(max_in_60s, count)
                    if max_in_60s > peak_per_min[tool]:
                        peak_per_min[tool] = max_in_60s

    # Duplicate rate
    dup_5m = 0
    dup_1h = 0
    total = len(flat_alerts)
    
    for i, a1 in enumerate(flat_alerts):
        has_5m = False
        has_1h = False
        for a2 in flat_alerts[i+1:]:
            delta = (a2["ts"] - a1["ts"]).total_seconds()
            if delta > 3600: break
            if a1["tool"] == a2["tool"] and a1["name"] == a2["name"] and a1["component"] == a2["component"]:
                has_1h = True
                if delta <= 300: has_5m = True
        if has_5m: dup_5m += 1
        if has_1h: dup_1h += 1
                
    # Component resolution
    resolvable = sum(1 for a in flat_alerts if a["component"])
    
    # Output Markdown
    print("## Measured Values")
    print("* Steady-state alert rate:")
    if not args.quiet_window:
        print("  * INSUFFICIENT DATA: quiet window not provided")
    else:
        for t, rt in steady_state_hourly.items(): print(f"  * {t}: {rt:.1f} /hour")
        
    print("* Peak burst during an injected fault:")
    if not peak_per_min: print("  * INSUFFICIENT DATA: no faults processed")
    for t, pk in peak_per_min.items(): print(f"  * {t}: {pk} /minute")
    
    print("* Alerts per fault, per tool:")
    if not fault_counts: print("  * INSUFFICIENT DATA: no faults processed")
    for ftype, tcounts in fault_counts.items():
        print(f"  * {ftype}:")
        for t, c in tcounts.items(): print(f"    * {t}: {c}")
        
    print(f"* Measured duplicate rate:")
    if total == 0:
        print("  * INSUFFICIENT DATA")
    else:
        print(f"  * 5 min: {(dup_5m/total)*100:.1f} %")
        print(f"  * 1 hour: {(dup_1h/total)*100:.1f} %")
        
    print(f"* Unresolved component rate:")
    if total == 0:
        print("  * INSUFFICIENT DATA")
    else:
        print(f"  * {((total-resolvable)/total)*100:.1f} % ({resolvable}/{total} resolved)")
        
    print("\n* Total Captured:")
    for t, c in totals.items(): print(f"  * {t}: {c}")

if __name__ == "__main__":
    main()
