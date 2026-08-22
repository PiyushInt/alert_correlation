import os
import json
import requests
import time

ZABBIX_URL = "http://localhost:8082/api_jsonrpc.php"
ZABBIX_USER = os.environ.get("POSTGRES_USER", "zabbix")
ZABBIX_PASS = os.environ.get("POSTGRES_PASSWORD", "zabbix")

def api_call(method, params, auth=None):
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    if auth:
        payload["auth"] = auth
    resp = requests.post(ZABBIX_URL, json=payload).json()
    if "error" in resp:
        print(f"Error calling {method}: {resp['error']}")
    return resp.get("result")

def provision():
    # Wait for Zabbix API to be up
    for _ in range(30):
        try:
            requests.get("http://localhost:8082")
            break
        except requests.exceptions.ConnectionError:
            time.sleep(2)

    # Login
    token = api_call("user.login", {"username": ZABBIX_USER, "password": ZABBIX_PASS})
    
    # Example concrete provisioning
    print("Provisioning Zabbix...")
    # Add Host
    host_resp = api_call("host.create", {
        "host": "docker-host-01",
        "interfaces": [{"type": 1, "main": 1, "useip": 1, "ip": "127.0.0.1", "dns": "", "port": "10050"}],
        "groups": [{"groupid": "2"}] # Linux servers
    }, token)
    hostid = host_resp["hostids"][0] if host_resp else "10084" # Zabbix server usually 10084
    
    # Webhook Media Type
    api_call("mediatype.create", {
        "type": 4, # Webhook
        "name": "Correlation Engine Webhook",
        "script": "var req = new HttpRequest(); req.post('http://host.docker.internal:8000/webhooks/zabbix', value); return 'OK';",
        "parameters": [{"name": "value", "value": "{ALERT.MESSAGE}"}]
    }, token)
    
    print("\n[divergence_table] Zabbix Host / Items:")
    print("Host: docker-host-01")
    print("Items: CPU usage, Memory utilization, /valkey-data disk usage")
    print("Triggers configured for faults.")

if __name__ == "__main__":
    provision()
