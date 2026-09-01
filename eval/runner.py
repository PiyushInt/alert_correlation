import argparse
import json
import logging
import os
import subprocess
import time
import uuid
import yaml
import httpx
from datetime import datetime, UTC
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Setup basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("eval.runner")

# Safety check
db_url = os.environ.get("DATABASE_URL", "")
if not db_url.endswith("ace_db_eval"):
    logger.error("FATAL: DATABASE_URL does not end with ace_db_eval. Refusing to run against production.")
    exit(1)

engine = create_engine(db_url)
SessionLocal = sessionmaker(bind=engine)

API_URL = "http://localhost:8000/webhooks"

def query_incidents_for_run(db, run_id):
    """
    Finds all incidents that contain at least one alert with ace_eval_run_id == run_id.
    Returns a list of dicts representing the incident structure.
    """
    sql = text("""
        SELECT DISTINCT i.id as incident_id, i.root_cause_component_id
        FROM incidents i
        JOIN incident_alerts ia ON i.id = ia.incident_id
        JOIN alerts a ON ia.alert_id = a.id
        WHERE a.labels->>'ace_eval_run_id' = :run_id
           OR a.raw_payload->>'ace_eval_run_id' = :run_id
    """)
    incidents = []
    rows = db.execute(sql, {"run_id": run_id}).fetchall()
    
    for row in rows:
        inc_id = row.incident_id
        # Get members and their source tools
        members_sql = text("""
            SELECT a.source_tool, a.labels->>'alertname' as alertname, a.severity
            FROM alerts a
            JOIN incident_alerts ia ON a.id = ia.alert_id
            WHERE ia.incident_id = :inc_id
            ORDER BY a.source_tool, a.received_at
        """)
        members = db.execute(members_sql, {"inc_id": inc_id}).fetchall()
        
        # We also need the source tools involved
        source_tools = sorted(list(set(m.source_tool for m in members)))
        
        incidents.append({
            "member_count": len(members),
            "source_tools": source_tools,
            "root_cause_component_id": str(row.root_cause_component_id) if row.root_cause_component_id else None,
            "members": [
                {"source_tool": m.source_tool, "alertname": m.alertname, "severity": m.severity}
                for m in members
            ]
        })
    
    # Sort incidents by member count then by source tools to ensure deterministic order
    incidents.sort(key=lambda x: (x["member_count"], ",".join(x["source_tools"])))
    return incidents

def inject_run_id(payload_dict, source_tool, run_id, scenario_name):
    """
    Injects ace_eval_run_id and ace_eval_scenario into the payload.
    For zabbix, we have to put it in the top level.
    For prometheus/blackbox, we put it in labels.
    """
    if source_tool in ("prometheus", "blackbox"):
        if "labels" not in payload_dict:
            payload_dict["labels"] = {}
        payload_dict["labels"]["ace_eval_run_id"] = run_id
        payload_dict["labels"]["ace_eval_scenario"] = scenario_name
    else:
        payload_dict["ace_eval_run_id"] = run_id
        payload_dict["ace_eval_scenario"] = scenario_name
    return payload_dict

def run_capture(scenario_file, scenario_data):
    run_id = str(uuid.uuid4())
    logger.info(f"--- Starting CAPTURE Mode (run_id: {run_id}) ---")
    
    fault_script = scenario_data.get("fault_script")
    args = scenario_data.get("arguments", [])
    duration = scenario_data.get("duration_seconds", 300)
    
    logger.info(f"Executing fault script: {fault_script} {' '.join(args)}")
    start_time = datetime.now(UTC)
    
    try:
        if fault_script.endswith(".sh"):
            subprocess.run(["bash", fault_script] + args, check=True)
        else:
            subprocess.run([fault_script] + args, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Fault script failed: {e}")
        return None
        
    logger.info(f"Waiting {duration} seconds for alerts to form naturally...")
    time.sleep(duration)
    
    # Now query ace_db_eval for all alerts that occurred after start_time
    # Since we can't easily filter by "my fault" without a run_id, 
    # we assume the estate is quiet EXCEPT for our fault during eval.
    db = SessionLocal()
    sql = text("""
        SELECT id, source_tool, raw_payload, received_at
        FROM alerts
        WHERE received_at >= :start
        ORDER BY received_at ASC
    """)
    rows = db.execute(sql, {"start": start_time}).fetchall()
    
    captured_payloads = []
    for row in rows:
        # DB stores raw_payload as JSONB (or dict in python)
        payload = row.raw_payload
        if isinstance(payload, str):
            payload = json.loads(payload)
            
        captured_payloads.append({
            "source_tool": row.source_tool,
            "received_at": row.received_at.isoformat(),
            "raw_payload": payload
        })
        
    db.close()
    
    logger.info(f"Captured {len(captured_payloads)} alert payloads.")
    
    scenario_name = os.path.splitext(os.path.basename(scenario_file))[0]
    capture_file = f"eval/captures/{scenario_name}.json"
    
    with open(capture_file, "w") as f:
        json.dump(captured_payloads, f, indent=2)
        
    logger.info(f"Capture written to {capture_file}")
    return capture_file

def run_replay(capture_file, scenario_name):
    run_id = str(uuid.uuid4())
    logger.info(f"--- Starting REPLAY Mode (run_id: {run_id}, scenario: {scenario_name}) ---")
    
    # Wait for the correlation window to elapse to ensure replay isolation.
    # We use a fixed sleep because we cannot rely on incidents from prior runs 
    # being 'resolved' to know when they are closed (e.g. capture incidents 
    # can stay open if the dedup window is shorter than the fault duration).
    wait_time = 350 # DEDUP_WINDOW (330) + margin
    logger.info(f"Sleeping for {wait_time}s to isolate this replay from prior open incidents...")
    time.sleep(wait_time)
    
    with open(capture_file, "r") as f:
        payloads = json.load(f)
        
    logger.info(f"Loaded {len(payloads)} payloads for replay.")
    
    last_received_at = None
    failed_sends = 0
    total_sends = len(payloads)
    
    for p in payloads:
        source_tool = p["source_tool"]
        raw = p["raw_payload"]
        
        current_received_at = datetime.fromisoformat(p.get("received_at", datetime.now().isoformat()))
        
        if last_received_at is not None:
            # Sleep to preserve original inter-arrival gap
            gap = (current_received_at - last_received_at).total_seconds()
            if gap > 0:
                logger.info(f"Sleeping {gap:.1f}s to preserve inter-arrival gap...")
                time.sleep(gap)
                
        last_received_at = current_received_at
        
        # Inject run_id and scenario_name
        raw = inject_run_id(raw, source_tool, run_id, scenario_name)
        
        # Wrap for Prometheus/Blackbox
        if source_tool in ("prometheus", "blackbox"):
            # DB stores individual alert_data. API expects AlertmanagerPayload.
            raw = {
                "status": raw.get("status", "firing"),
                "alerts": [raw]
            }
            url = f"{API_URL}/alertmanager"
        elif source_tool == "zabbix":
            raw = {
                "value": json.dumps(raw)
            }
            url = f"{API_URL}/zabbix"
        else:
            url = f"{API_URL}/{source_tool}"

        try:
            r = httpx.post(url, json=raw, timeout=5.0)
            if r.status_code not in (200, 202):
                logger.error(f"Failed to post {source_tool} payload to {url}: {r.status_code} {r.text}")
                failed_sends += 1
            else:
                logger.info(f"Successfully posted {source_tool} payload")
        except Exception as e:
            logger.error(f"Exception posting {source_tool} payload to {url}: {e}")
            failed_sends += 1
            
    if failed_sends > 0:
        import sys
        logger.error(f"FATAL: {failed_sends} out of {total_sends} payloads failed to send. Aborting run.")
        sys.exit(1)
        
    # Wait for pipeline to settle
    wait_time = 305  # CORRELATION_WINDOW is 300s
    logger.info(f"Waiting {wait_time} seconds for pipeline correlation...")
    time.sleep(wait_time)
    
    db = SessionLocal()
    incidents = query_incidents_for_run(db, run_id)
    db.close()
    
    logger.info(f"Replay {run_id} produced {len(incidents)} incidents.")
    return incidents

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", required=True, help="Path to scenario YAML (e.g. cascade/disk_fill)")
    parser.add_argument("--capture", action="store_true", help="Run capture mode")
    parser.add_argument("--replay", action="store_true", help="Run replay mode")
    parser.add_argument("--holdout", action="store_true", help="Allow running hold-out scenarios")
    
    args = parser.parse_args()
    
    # Resolve scenario file
    scenario_file = args.scenario
    if not scenario_file.endswith(".yaml"):
        scenario_file += ".yaml"
    if not scenario_file.startswith("eval/scenarios/") and not scenario_file.startswith("eval/holdout/"):
        scenario_file = os.path.join("eval/scenarios", scenario_file)
        
    if "eval/holdout/" in scenario_file and not args.holdout:
        logger.error(f"Refusing to run holdout scenario {scenario_file} without --holdout flag.")
        sys.exit(1)
        
    with open(scenario_file, "r") as f:
        scenario_data = yaml.safe_load(f)
        
    scenario_name = os.path.splitext(os.path.basename(scenario_file))[0]
    capture_file = f"eval/captures/{scenario_name}.json"
    
    # If neither flag is passed, run end-to-end
    run_e2e = not (args.capture or args.replay)
    
    if args.capture or run_e2e:
        capture_file_out = run_capture(scenario_file, scenario_data)
        if not capture_file_out:
            logger.error("Capture failed. Exiting.")
            return
            
    if args.replay or run_e2e:
        if not os.path.exists(capture_file):
            logger.error(f"Capture file {capture_file} not found. Run --capture first.")
            return
            
        scenario_name = os.path.splitext(os.path.basename(scenario_file))[0]
        incidents_run1 = run_replay(capture_file, scenario_name)
        incidents_run2 = run_replay(capture_file, scenario_name)
        
        # Compare structural equality
        logger.info("--- Comparing Replays ---")
        logger.info(f"Run 1 Incidents: {json.dumps(incidents_run1, indent=2)}")
        logger.info(f"Run 2 Incidents: {json.dumps(incidents_run2, indent=2)}")
        
        if incidents_run1 == incidents_run2:
            logger.info("SUCCESS: Two replays produced identical incidents.")
        else:
            logger.error("FAILURE: Replays produced different incidents!")
            
        # Check ground truth
        gt = scenario_data.get("ground_truth", {})
        expected_incidents_list = gt.get("expected_incidents", [])
        gt_incidents = len(expected_incidents_list) if isinstance(expected_incidents_list, list) else 0
        
        if len(incidents_run1) == gt_incidents:
            logger.info(f"[SMOKE TEST] MATCH: Found {gt_incidents} incidents as expected.")
        else:
            logger.error(f"[SMOKE TEST] MISMATCH: Expected {gt_incidents} incidents, got {len(incidents_run1)}.")

if __name__ == "__main__":
    main()
