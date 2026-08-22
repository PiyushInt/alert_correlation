import os
import json
import sys
import argparse
import datetime
from datetime import timezone

def parse_iso(dt_str):
    dt_str = dt_str.replace("Z", "+00:00")
    return datetime.datetime.fromisoformat(dt_str)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fault_filter", help="<fault_type|latest>")
    parser.add_argument("--faults-file", default=os.path.join(REPO_ROOT, "estate", "captures", "faults.jsonl"))
    parser.add_argument("--payloads-dir", default=os.path.join(REPO_ROOT, "estate", "captures", "payloads"))
    args = parser.parse_args()
    
    # Read faults
    fault = None
    if os.path.exists(args.faults_file):
        with open(args.faults_file, "r") as f:
            lines = f.readlines()
            for line in reversed(lines):
                if not line.strip(): continue
                rec = json.loads(line)
                if args.fault_filter == "latest" or rec.get("fault_type") == args.fault_filter or rec.get("fault_id") == args.fault_filter:
                    fault = rec
                    break
                    
    if not fault:
        print(f"No fault found for {args.fault_filter}. Using generic window.")
        now = datetime.datetime.now(timezone.utc)
        fault = {
            "start_time": (now - datetime.timedelta(minutes=10)).isoformat(),
            "end_time": now.isoformat(),
            "fault_type": "unknown",
            "target": "unknown"
        }
        
    start_dt = parse_iso(fault["start_time"]) - datetime.timedelta(seconds=60)
    end_dt = parse_iso(fault["end_time"]) + datetime.timedelta(seconds=300)
    target = fault.get("target", "unknown")
    
    print(f"Fault: {fault['fault_type']} on {target}")
    print(f"Window: {start_dt.isoformat()} to {end_dt.isoformat()}")
    
    # Read payloads
    alerts = []
    
    if os.path.exists(args.payloads_dir):
        for fname in os.listdir(args.payloads_dir):
            if not fname.endswith(".json"): continue
            
            with open(os.path.join(args.payloads_dir, fname), "r") as f:
                try:
                    payload = json.load(f)
                    recv_dt = parse_iso(payload["received_at"])
                    if start_dt <= recv_dt <= end_dt:
                        raw_body_str = payload.get("raw_body", "")
                        raw_body = json.loads(raw_body_str) if raw_body_str else {}
                        path = payload.get("path", "")
                        
                        if "value" in raw_body and "trigger_name" in raw_body["value"]:
                            # This handles Zabbix webhook wrapper
                            try:
                                inner = json.loads(raw_body["value"])
                                ts = inner.get("event_time", payload["received_at"])
                                if ts and "T" in ts:
                                    ts = ts.replace(".", "-")
                                alerts.append({
                                    "tool": "Zabbix",
                                    "name": inner.get("trigger_name", "Unknown Zabbix Trigger"),
                                    "component": inner.get("host", "Unknown Host"),
                                    "severity": inner.get("severity", "Unknown"),
                                    "timestamp": ts
                                })
                            except json.JSONDecodeError:
                                pass
                        elif "alertmanager" in path:
                            body = raw_body
                            for al in body.get("alerts", []):
                                labels = al.get("labels", {})
                                alertname = labels.get("alertname", "Unknown")
                                job = labels.get("job", "")
                                
                                if job == "blackbox" or "probe" in alertname.lower():
                                    tool = "Blackbox"
                                else:
                                    tool = "Prometheus"
                                    
                                component = labels.get("instance") or labels.get("pod") or labels.get("host") or "Unknown"
                                severity = labels.get("severity", "Unknown")
                                
                                alerts.append({
                                    "tool": tool,
                                    "name": alertname,
                                    "component": component,
                                    "severity": severity,
                                    "timestamp": payload["received_at"]
                                })
                except Exception as e:
                    print(f"Error parsing {fname}: {e}")
                    
    # Print table
    print("\n| Tool | Alert Name | Component | Severity | Timestamp |")
    print("|---|---|---|---|---|")
    counts = {"Prometheus": 0, "Zabbix": 0, "Blackbox": 0}
    
    comp_map = {"Prometheus": "(none)", "Zabbix": "(none)", "Blackbox": "(none)"}
    
    for a in sorted(alerts, key=lambda x: x["timestamp"]):
        print(f"| {a['tool']} | {a['name']} | {a['component']} | {a['severity']} | {a['timestamp']} |")
        counts[a['tool']] = counts.get(a['tool'], 0) + 1
        if comp_map[a['tool']] == "(none)":
            comp_map[a['tool']] = a['component']
        
    print("\n--- Summary ---")
    for t, c in counts.items():
        print(f"{t}: {c} alerts")
        
    print("\n--- Markdown Fragment for docs/ESTATE.md ---")
    print("## Measured Values")
    print(f"* Alerts per fault ({fault['fault_type']}):")
    for t, c in counts.items():
        print(f"  * {t}: {c}")
        
    print("\n## Naming Divergence (Sample)")
    print("| Component (Target) | Prometheus | Zabbix | Blackbox |")
    print("|---|---|---|---|")
    print(f"| {target} | {comp_map['Prometheus']} | {comp_map['Zabbix']} | {comp_map['Blackbox']} |")

if __name__ == "__main__":
    main()
