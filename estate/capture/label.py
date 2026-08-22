import argparse
import csv
import datetime
import json
import os
import sys


def parse_iso(dt_str):
    if not dt_str:
        return None
    return datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))


def tokenize(text):
    return set(text.lower().replace("-", " ").replace("_", " ").split())


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


import yaml


def get_rule_components():
    try:
        with open(os.path.join(REPO_ROOT, "estate", "prometheus", "rules.yml")) as f:
            data = yaml.safe_load(f)
            mapping = {}
            for group in data.get("groups", []):
                for rule in group.get("rules", []):
                    alert = rule.get("alert")
                    comp = rule.get("labels", {}).get("component")
                    if alert and comp:
                        mapping[alert] = comp
            return mapping
    except:
        return {}


RULE_COMPONENTS = get_rule_components()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fault-id", help="Fault target or ID")
    parser.add_argument(
        "--faults-file", default=os.path.join(REPO_ROOT, "estate", "captures", "faults.jsonl")
    )
    parser.add_argument(
        "--payloads-dir", default=os.path.join(REPO_ROOT, "estate", "captures", "payloads")
    )
    parser.add_argument("--summarise", help="CSV file to summarise")
    args = parser.parse_args()

    if args.summarise:
        if not os.path.exists(args.summarise):
            print("INSUFFICIENT DATA: CSV file not found")
            return

        total_related = 0
        share_comp = 0
        share_text = 0
        share_neither = 0

        with open(args.summarise) as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["same_incident"].strip().lower() in ["y", "yes", "1", "true"]:
                    total_related += 1
                    sc = row["shares_component"].strip() == "True"
                    st = float(row["text_similarity_rough"]) > 0.3  # arbitrary threshold

                    if sc:
                        share_comp += 1
                    if st:
                        share_text += 1
                    if not sc and not st:
                        share_neither += 1

        if total_related == 0:
            print("INSUFFICIENT DATA: no pairs labelled")
            sys.exit(1)

        print("## Baseline Relatedness")
        print(f"Total related pairs labeled: {total_related}")
        print(f"Pairs sharing a component: {share_comp}")
        print(f"Pairs sharing similar text: {share_text}")
        print(f"Pairs sharing NEITHER (dependency map territory): {share_neither}")
        return

    if not args.fault_id:
        print("Must provide --fault-id or --summarise")
        sys.exit(1)

    # Generation mode
    faults_to_label = []
    if os.path.exists(args.faults_file):
        with open(args.faults_file) as f:
            for line in f:
                if not line.strip():
                    continue
                rec = json.loads(line)
                if (
                    rec.get("target") == args.fault_id
                    or rec.get("fault_type") == args.fault_id
                    or rec.get("fault_id") == args.fault_id
                ):
                    faults_to_label.append(rec)

    if not faults_to_label:
        print("INSUFFICIENT DATA: Fault not found")
        return

    alerts = []
    for fault in faults_to_label:
        fs = parse_iso(fault["start_time"])
        fe = parse_iso(fault["end_time"])

        for fname in os.listdir(args.payloads_dir):
            if not fname.endswith(".json"):
                continue
            with open(os.path.join(args.payloads_dir, fname)) as f:
                try:
                    p = json.load(f)
                    ts = parse_iso(p["received_at"])
                    if fs <= ts <= fe + datetime.timedelta(seconds=60):
                        raw = p.get("raw_body", "")
                        b = json.loads(raw) if raw else {}
                        # simplified extraction
                        if "zabbix" in p.get("path", ""):
                            inner = {}
                            try:
                                inner = json.loads(b.get("value", "{}"))
                            except:
                                pass
                            alerts.append(
                                {
                                    "id": f"Z_{len(alerts)}",
                                    "name": inner.get("trigger_name", ""),
                                    "comp": inner.get("host", ""),
                                }
                            )
                        else:
                            for al in b.get("alerts", []):
                                labels = al.get("labels", {})
                                name = labels.get("alertname", "")
                                job = labels.get("job", "")
                                prefix = (
                                    "B" if job == "blackbox" or "probe" in name.lower() else "P"
                                )
                                comp = (
                                    labels.get("component")
                                    or RULE_COMPONENTS.get(name)
                                    or labels.get("instance")
                                    or labels.get("pod")
                                    or labels.get("host")
                                    or ""
                                )
                                alerts.append(
                                    {"id": f"{prefix}_{len(alerts)}", "name": name, "comp": comp}
                                )
                except:
                    pass

    if not alerts:
        print("INSUFFICIENT DATA: No alerts found for this fault window")
        return

    out_dir = os.path.join(REPO_ROOT, "estate", "captures", "labels")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"{args.fault_id}.csv")

    with open(out_file, "w") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["alert_a", "alert_b", "same_incident", "shares_component", "text_similarity_rough"]
        )

        for i, a1 in enumerate(alerts):
            print(f"[{a1['id']}] {a1['name']} on {a1['comp']}")
            for a2 in alerts[i + 1 :]:
                shares_comp = a1["comp"] == a2["comp"] and bool(a1["comp"])
                t1 = tokenize(a1["name"])
                t2 = tokenize(a2["name"])
                sim = len(t1 & t2) / max(len(t1 | t2), 1)
                writer.writerow([a1["id"], a2["id"], "", shares_comp, f"{sim:.2f}"])

    print(
        f"\nSkeleton written to {out_file}. Fill 'same_incident' column and run with --summarise."
    )


if __name__ == "__main__":
    main()
