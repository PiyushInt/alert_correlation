import os
import json
import sys
import argparse

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
    
    if tool == "Zabbix":
        inner = {}
        try:
            inner = json.loads(body.get("value", "{}"))
        except:
            pass
        alerts.append({
            "tool": tool,
            "component": inner.get("host", ""),
        })
    elif tool in ["Prometheus", "Blackbox"]:
        for al in body.get("alerts", []):
            labels = al.get("labels", {})
            comp = labels.get("instance") or labels.get("pod") or labels.get("host") or ""
            alerts.append({
                "tool": tool,
                "component": comp,
            })
    return alerts

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--faults-file", default=os.path.join(REPO_ROOT, "estate", "captures", "faults.jsonl"))
    parser.add_argument("--payloads-dir", default=os.path.join(REPO_ROOT, "estate", "captures", "payloads"))
    args = parser.parse_args()
    
    if not os.path.exists(args.faults_file) or not os.path.exists(args.payloads_dir):
        print("INSUFFICIENT DATA: Missing files")
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
        print("INSUFFICIENT DATA")
        return
        
    flat_alerts = []
    for p in all_payloads:
        tool = get_tool(p)
        flat_alerts.extend(extract_alerts(p, tool))
        
    # First, grouping by fault target is asked:
    # "Reads all captures, groups by fault target, and for each logical component emits one row"
    # Actually, faults.jsonl tells us the target.
    # But since multiple alerts can fire for one fault, we just use the fault's target name as the logical component.
    
    # We will map each alert to a fault based on time. We already did this in measure.py, let's keep it simple here.
    # Since we just want the divergence table, we'll extract the unique components seen per tool.
    
    import datetime
    def parse_iso(dt_str):
        if not dt_str: return None
        return datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        
    faults = []
    with open(args.faults_file, "r") as f:
        for line in f:
            if line.strip(): faults.append(json.loads(line))
            
    # Map targets -> {tool: set of components}
    divergence = {}
    
    for fault in faults:
        target = fault.get("target", "unknown")
        if target not in divergence:
            divergence[target] = {"Prometheus": set(), "Zabbix": set(), "Blackbox": set()}
            
        fs = parse_iso(fault["start_time"])
        fe = parse_iso(fault["end_time"])
        
        for p in all_payloads:
            ts = parse_iso(p["received_at"])
            if fs <= ts <= fe + datetime.timedelta(seconds=60):
                tool = get_tool(p)
                for a in extract_alerts(p, tool):
                    if tool in divergence[target] and a["component"]:
                        divergence[target][tool].add(a["component"])
                        
    print("## Naming Divergence (By Fault Target)")
    print("| Logical Component | Prometheus | Zabbix | Blackbox |")
    print("|---|---|---|---|")
    for target, tools in divergence.items():
        p_str = ", ".join(tools["Prometheus"]) or "(none)"
        z_str = ", ".join(tools["Zabbix"]) or "(none)"
        b_str = ", ".join(tools["Blackbox"]) or "(none)"
        print(f"| {target} | {p_str} | {z_str} | {b_str} |")
        
    print("\n## Raw Component Identifiers (No Grouping)")
    print("| Tool | Identifiers |")
    print("|---|---|")
    all_comps = {"Prometheus": set(), "Zabbix": set(), "Blackbox": set()}
    for a in flat_alerts:
        if a["tool"] in all_comps and a["component"]:
            all_comps[a["tool"]].add(a["component"])
            
    for t, comps in all_comps.items():
        c_str = ", ".join(comps) or "(none)"
        print(f"| {t} | {c_str} |")

if __name__ == "__main__":
    main()
