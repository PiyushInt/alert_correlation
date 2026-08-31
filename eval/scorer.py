import os
import json
import glob
import argparse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert, NotificationLog, RootCauseCandidate
from eval.labels import load_ground_truth, match_incidents, PipelineIncident

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://ace_readonly:ace_readonly@localhost:5433/ace_db_eval")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def load_scenario_mapping() -> dict:
    mapping_path = "eval/scenario_mapping.json"
    if not os.path.exists(mapping_path):
        return {}
    with open(mapping_path, "r") as f:
        return json.load(f)

def fetch_pipeline_incidents(db, run_id: str) -> list[PipelineIncident]:
    sql = text("""
        SELECT DISTINCT i.id as incident_id, i.root_cause_component_id, i.status
        FROM incidents i
        JOIN incident_alerts ia ON i.id = ia.incident_id
        JOIN alerts a ON ia.alert_id = a.id
        WHERE (a.labels->>'ace_eval_run_id' = :run_id
           OR a.raw_payload->>'ace_eval_run_id' = :run_id)
    """)
    rows = db.execute(sql, {"run_id": run_id}).fetchall()
    
    pipeline_incidents = []
    
    for row in rows:
        inc_id = row.incident_id
        # Note: Exclude fabricated signal_scores row: c9598adf-b1ca-4d06-bc43-4d0a006b32a7
        # And ONLY include firing alerts!
        members_sql = text("""
            SELECT a.id, a.source_tool, a.status
            FROM alerts a
            JOIN incident_alerts ia ON a.id = ia.alert_id
            WHERE ia.incident_id = :inc_id
              AND a.id != 'c9598adf-b1ca-4d06-bc43-4d0a006b32a7'
        """)
        members = db.execute(members_sql, {"inc_id": inc_id}).fetchall()
        
        firing_count = 0
        resolved_count = 0
        tools = set()
        
        for m in members:
            if m.status == "firing":
                firing_count += 1
                tools.add(m.source_tool)
            else:
                resolved_count += 1
                
        # If no firing alerts, skip? Or include as 0? The plan says metrics computed ONLY over status='firing'.
        if firing_count == 0:
            continue
            
        # Get true cause name
        comp_sql = text("SELECT canonical_name FROM components WHERE id = :comp_id")
        comp_row = db.execute(comp_sql, {"comp_id": row.root_cause_component_id}).fetchone()
        rc_name = comp_row.canonical_name if comp_row else None
        
        # Get top 3 candidates ordered by rank
        rc_sql = text("""
            SELECT c.canonical_name
            FROM root_cause_candidates rcc
            JOIN components c ON rcc.component_id = c.id
            WHERE rcc.incident_id = :inc_id
            ORDER BY rcc.rank ASC
            LIMIT 3
        """)
        rc_rows = db.execute(rc_sql, {"inc_id": inc_id}).fetchall()
        top_3 = [r.canonical_name for r in rc_rows]
        
        # Get notification delay
        # Time between first firing alert and notification_logs entry
        delay = None
        notif_sql = text("SELECT dispatched_at FROM notification_logs WHERE incident_id = :inc_id ORDER BY dispatched_at ASC LIMIT 1")
        notif_row = db.execute(notif_sql, {"inc_id": inc_id}).fetchone()
        
        if notif_row:
            first_alert_sql = text("""
                SELECT MIN(a.starts_at)
                FROM alerts a
                JOIN incident_alerts ia ON a.id = ia.alert_id
                WHERE ia.incident_id = :inc_id AND a.status = 'firing'
            """)
            first_alert_row = db.execute(first_alert_sql, {"inc_id": inc_id}).fetchone()
            if first_alert_row and first_alert_row[0]:
                delay = (notif_row.dispatched_at - first_alert_row[0]).total_seconds()

        pipeline_incidents.append(PipelineIncident(
            id=str(inc_id),
            firing_alerts=firing_count,
            tools=list(tools),
            root_cause_component=rc_name,
            resolved_alerts=resolved_count,
            top_3_candidates=top_3,
            first_notification_delay=delay
        ))
        
    return pipeline_incidents

def fetch_unresolved_rate(db, run_id: str) -> float:
    # Firing alerts with component_unresolved = True / Total firing alerts
    sql = text("""
        SELECT 
            COUNT(CASE WHEN component_unresolved = true THEN 1 END) as unresolved,
            COUNT(*) as total
        FROM alerts
        WHERE (labels->>'ace_eval_run_id' = :run_id OR raw_payload->>'ace_eval_run_id' = :run_id)
          AND status = 'firing'
          AND id != 'c9598adf-b1ca-4d06-bc43-4d0a006b32a7'
    """)
    row = db.execute(sql, {"run_id": run_id}).fetchone()
    if row and row.total > 0:
        return row.unresolved / row.total
    return 0.0
    
def score_scenarios():
    db = SessionLocal()
    
    scenario_files = glob.glob("eval/scenarios/**/*.yaml", recursive=True)
    
    results = {}
    
    mapping = load_scenario_mapping()
    
    for sf in scenario_files:
        scenario_name = os.path.splitext(os.path.basename(sf))[0]
        gt = load_ground_truth(sf)
        if not gt or not gt.expected_incidents:
            continue
            
        run_id = mapping.get(scenario_name)
        if not run_id:
            print(f"Skipping {scenario_name}: no run_id found in mapping.")
            continue
            
        pipeline_incidents = fetch_pipeline_incidents(db, run_id)
        
        metrics = match_incidents(pipeline_incidents, gt.expected_incidents)
        
        # Noise reduction: 1 - (incidents / firing_alerts)
        total_firing_alerts = sum(p.firing_alerts for p in pipeline_incidents)
        if total_firing_alerts > 0:
            noise_reduction = 1.0 - (len(pipeline_incidents) / total_firing_alerts)
        else:
            noise_reduction = 0.0
            
        unresolved_rate = fetch_unresolved_rate(db, run_id)
        
        # Added latency
        delays = [p.first_notification_delay for p in pipeline_incidents if p.first_notification_delay is not None]
        if delays:
            avg_latency = sum(delays) / len(delays)
        else:
            avg_latency = "NOT MEASURED"
            
        family = gt.family
        if family not in results:
            results[family] = []
            
        results[family].append({
            "scenario": scenario_name,
            "run_id": run_id,
            "noise_reduction": noise_reduction,
            "grouping_precision": metrics["precision"],
            "grouping_recall": metrics["recall"],
            "over_merge_rate": metrics["over_merge_rate"],
            "root_cause_top3_rate": metrics["root_cause_top3_rate"],
            "cross_tool_grouping": metrics["cross_tool_grouping"],
            "unresolved_component_rate": unresolved_rate,
            "added_latency": avg_latency
        })
        
    db.close()
    return results

def aggregate_family_metrics(results):
    aggregated = {}
    for family, sc_results in results.items():
        if not sc_results:
            continue
        agg = {
            "noise_reduction": sum(r["noise_reduction"] for r in sc_results) / len(sc_results),
            "grouping_precision": sum(r["grouping_precision"] for r in sc_results) / len(sc_results),
            "grouping_recall": sum(r["grouping_recall"] for r in sc_results) / len(sc_results),
            "over_merge_rate": sum(r["over_merge_rate"] for r in sc_results) / len(sc_results),
            "root_cause_top3_rate": sum(r["root_cause_top3_rate"] for r in sc_results) / len(sc_results),
            "unresolved_component_rate": sum(r["unresolved_component_rate"] for r in sc_results) / len(sc_results),
            "scenarios_scored": len(sc_results)
        }
        
        cross_tool = "No"
        if any(r["cross_tool_grouping"] == "Yes" for r in sc_results):
            cross_tool = "Yes"
        agg["cross_tool_grouping"] = cross_tool
        
        latencies = [r["added_latency"] for r in sc_results if isinstance(r["added_latency"], (int, float))]
        if latencies:
            agg["added_latency"] = sum(latencies) / len(latencies)
        else:
            agg["added_latency"] = "NOT MEASURED"
            
        aggregated[family] = agg
    return aggregated

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", help="Check for >5% regression against baseline")
    parser.add_argument("--save-baseline", help="Save output to baseline file")
    args = parser.parse_args()
    
    results = score_scenarios()
    aggregated = aggregate_family_metrics(results)
    
    print(json.dumps({"families": aggregated, "scenarios": results}, indent=2))
    
    if args.save_baseline:
        os.makedirs(os.path.dirname(args.save_baseline), exist_ok=True)
        with open(args.save_baseline, "w") as f:
            json.dump({"families": aggregated}, f, indent=2)
            
    if args.baseline:
        if not os.path.exists(args.baseline):
            print(f"Baseline file {args.baseline} not found.")
            exit(1)
        with open(args.baseline, "r") as f:
            baseline = json.load(f).get("families", {})
            
        regression = False
        for family, mets in aggregated.items():
            base_mets = baseline.get(family)
            if not base_mets:
                continue
            for metric in ["noise_reduction", "grouping_precision", "grouping_recall", "root_cause_top3_rate"]:
                # Higher is better
                b_val = base_mets.get(metric, 0)
                c_val = mets.get(metric, 0)
                if b_val - c_val > 0.05:
                    print(f"REGRESSION in {family}.{metric}: {b_val:.2f} -> {c_val:.2f} (>5% drop)")
                    regression = True
            for metric in ["over_merge_rate", "unresolved_component_rate"]:
                # Lower is better
                b_val = base_mets.get(metric, 0)
                c_val = mets.get(metric, 0)
                if c_val - b_val > 0.05:
                    print(f"REGRESSION in {family}.{metric}: {b_val:.2f} -> {c_val:.2f} (>5% increase)")
                    regression = True
                    
        if regression:
            exit(1)
        else:
            print("No regressions >5% found.")
