# Phase 0 Verification Runbook

Follow these commands to verify the Phase 0 Estate configuration on a host with Docker installed.

## 1. Syntax Validation
```bash
# Validate YAML files
python3 -c 'import yaml, glob; [print(f"Valid: {f}") for f in glob.glob("**/*.yml", recursive=True) + glob.glob("**/*.yaml", recursive=True) if yaml.safe_load(open(f))]'
```

## 2. Bring Up Estate
```bash
cd estate
# Bring up datastore and zabbix db first
docker compose up -d valkey zabbix-db
sleep 15
# Bring up zabbix server/web
docker compose up -d zabbix-server zabbix-web
sleep 15
# Bring up everything else
docker compose up -d
```

## 3. Provision Zabbix
```bash
# Run the provision script to setup Zabbix hosts/triggers
python3 zabbix/provision.py
```

## 4. Run Chaos Scenarios
```bash
cd chaos
# Ensure scripts are executable
chmod +x *.sh

# Execute the main Gate A scenario
./fill_disk.sh
```

## 5. Observe Payloads
After running the disk fill fault:
1. Open Prometheus at `http://localhost:9090` and verify the `HighDiskUsage` alert is firing.
2. Open Zabbix at `http://localhost:8082` (Admin/zabbix) and verify the filesystem trigger is firing.
3. Open Blackbox output or Prometheus to verify `FrontendDown` fires due to the cascaded failure.
4. Check `estate/captures/faults.jsonl` to ensure the fault was logged.
