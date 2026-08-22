import urllib.request
import urllib.error
import urllib.parse
import json
import socket
import os
import sys

def check(name, test_func):
    try:
        res = test_func()
        if res is True:
            print(f"[{name}] PASS")
        elif isinstance(res, tuple) and res[0] is True:
            print(f"[{name}] PASS - {res[1]}")
        else:
            msg = res[1] if isinstance(res, tuple) else "Check failed"
            print(f"[{name}] FAIL - {msg}")
            return False
    except Exception as e:
        print(f"[{name}] FAIL - Exception: {str(e)}")
        return False
    return True

def get_json(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.loads(response.read().decode())

def post_json(url, payload, auth=None):
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    if auth: req.add_header("Authorization", auth)
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.loads(response.read().decode())

def preflight():
    success = True
    
    # 1. Zabbix API Auth (required for mount check)
    ZABBIX_USER = os.environ.get("POSTGRES_USER", "zabbix")
    ZABBIX_PASS = os.environ.get("POSTGRES_PASSWORD", "zabbix")
    zabbix_token = None
    def check_zabbix_auth():
        nonlocal zabbix_token
        res = post_json("http://localhost:8082/api_jsonrpc.php", {
            "jsonrpc": "2.0", "method": "user.login", "params": {"username": ZABBIX_USER, "password": ZABBIX_PASS}, "id": 1
        })
        if "result" in res:
            zabbix_token = res["result"]
            return True
        return False, "Zabbix auth failed"
    success &= check("Zabbix Authentication", check_zabbix_auth)

    # 2. MOUNTPOINT CHECK (Loud)
    def check_mount():
        prom_mnt = "NOT FOUND"
        try:
            data = get_json("http://localhost:9090/api/v1/query?query=node_filesystem_size_bytes")
            for res in data.get('data', {}).get('result', []):
                mnt = res['metric'].get('mountpoint', '')
                if "valkey" in mnt:
                    prom_mnt = mnt
                    break
        except:
            prom_mnt = "API ERROR"
            
        zab_mnt = "NOT FOUND"
        if zabbix_token:
            try:
                res = post_json("http://localhost:8082/api_jsonrpc.php", {
                    "jsonrpc": "2.0", "method": "item.get", "params": {"filter": {"host": ["docker-host-01"]}, "search": {"key_": "vfs.fs"}, "output": ["name", "key_"]}, "id": 1, "auth": zabbix_token
                })
                for item in res.get("result", []):
                    if "valkey" in item.get("key_", "") or "valkey" in item.get("name", ""):
                        zab_mnt = item.get("key_")
                        break
            except:
                zab_mnt = "API ERROR"
                
        print(f"\n==============================================")
        print(f"!!! MOUNTPOINT CHECK !!!")
        print(f"Prometheus (node-exporter) sees: {prom_mnt}")
        print(f"Zabbix (agent) sees: {zab_mnt}")
        print(f"==============================================\n")
        
        if prom_mnt in ["NOT FOUND", "API ERROR"] or zab_mnt in ["NOT FOUND", "API ERROR"]:
            return False, "Mount missing in one or both tools"
        return True
    success &= check("Shared valkey volume", check_mount)

    # Sink listening
    def check_sink():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(('localhost', 8000)) == 0:
                return True
            return False, "Port 8000 is not responding"
    success &= check("Sink listening", check_sink)

    # Prometheus targets
    def check_prom_targets():
        data = get_json("http://localhost:9090/api/v1/targets")
        down = [t['labels'].get('job', 'unknown') for t in data['data']['activeTargets'] if t['health'] != 'up']
        if down: return False, f"Targets down: {', '.join(down)}"
        if not data['data']['activeTargets']: return False, "No active targets found"
        return True
    success &= check("Prometheus /api/v1/targets", check_prom_targets)

    # Prometheus config (alertmanager)
    def check_prom_config():
        data = get_json("http://localhost:9090/api/v1/status/config")
        yaml_str = data['data']['yaml']
        if "alertmanagers" not in yaml_str: return False, "Alertmanagers block missing in config"
        return True
    success &= check("Prometheus /api/v1/status/config", check_prom_config)

    # Prometheus rules
    def check_prom_rules():
        data = get_json("http://localhost:9090/api/v1/rules")
        for group in data['data']['groups']:
            for rule in group['rules']:
                if rule['health'] != 'ok': return False, f"Rule {rule.get('name')} in error state"
        if not data['data']['groups']: return False, "No rules loaded"
        return True
    success &= check("Prometheus /api/v1/rules", check_prom_rules)

    # Alertmanager status
    def check_am():
        data = get_json("http://localhost:9093/api/v2/status")
        return True
    success &= check("Alertmanager /api/v2/status", check_am)

    # Blackbox probe
    def check_bb():
        target = urllib.parse.quote("http://frontend:8080")
        try:
            resp = urllib.request.urlopen(f"http://localhost:9115/probe?target={target}&module=http_2xx", timeout=3)
            body = resp.read().decode()
            if "probe_success 1" in body: return True
            return False, "probe_success is not 1"
        except urllib.error.URLError:
            return False, "Could not reach blackbox-exporter"
    success &= check("Blackbox /probe frontend", check_bb)

    # Zabbix host
    def check_zabbix_host():
        if not zabbix_token: return False, "No token"
        res = post_json("http://localhost:8082/api_jsonrpc.php", {
            "jsonrpc": "2.0", "method": "host.get", "params": {"filter": {"host": ["docker-host-01"]}}, "id": 1, "auth": zabbix_token
        })
        if res.get("result"):
            return True
        return False, "docker-host-01 not found"
    success &= check("Zabbix host docker-host-01", check_zabbix_host)

    if not success:
        sys.exit(1)
        
if __name__ == "__main__":
    preflight()
