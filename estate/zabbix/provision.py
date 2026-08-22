import os
import sys
import json
import requests
import time
import argparse
import subprocess

ZABBIX_URL = "http://localhost:8082/api_jsonrpc.php"
ZABBIX_USER = os.environ.get("ZABBIX_API_USER", "Admin")
ZABBIX_PASS = os.environ.get("ZABBIX_API_PASSWORD", "zabbix")

def api_call(method, params, auth=None):
    headers = {'Content-Type': 'application/json-rpc'}
    if auth:
        headers['Authorization'] = f'Bearer {auth}'
        
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1
    }
    
    resp = requests.post(ZABBIX_URL, json=payload, headers=headers).json()
    if "error" in resp:
        print(f"Error calling {method}: {resp['error']}")
        sys.exit(1)
        
    return resp.get("result")

def run_test_mode(token, triggerid):
    print("\n--- RUNNING IN TEST MODE ---")
    
    # 1. Lower threshold to >0
    print("Setting trigger threshold to >0 to force alert...")
    api_call("trigger.update", {
        "triggerid": triggerid,
        "expression": f"last(/docker-host-01/vfs.fs.size[/mnt/valkey-data,pused])>0"
    }, token)
    
    print("Reloading Zabbix Server config cache...")
    subprocess.run(["docker", "exec", "estate-zabbix-server-1", "zabbix_server", "-R", "config_cache_reload"], check=False)
    
    # 2. Poll problem.get for up to 3 minutes
    print("Waiting for trigger to enter PROBLEM state (up to 3 minutes)...")
    problem_found = False
    for i in range(36): # 36 * 5s = 180s = 3 minutes
        problems = api_call("problem.get", {"objectids": triggerid, "source": 0, "object": 0}, token)
        if problems:
            print(f"\nPROBLEM state reached! (Problem: {problems[0].get('name')})")
            problem_found = True
            break
        time.sleep(5)
        sys.stdout.write('.')
        sys.stdout.flush()
        
    if not problem_found:
        print("\nTimed out waiting for PROBLEM state.")
    else:
        # Wait a little bit for the action/alert to fire
        print("Waiting 10 seconds for alert delivery...")
        time.sleep(10)
        
        # 3. Check alert.get
        alerts = api_call("alert.get", {"objectids": triggerid, "eventsource": 0, "eventobject": 0}, token)
        print("\nAlert delivery status:")
        if alerts:
            for alert in alerts:
                print(f"  Alert ID {alert['alertid']}: Status={alert['status']}, Error='{alert['error']}', SendTo='{alert['sendto']}'")
        else:
            print("  No alerts found for this trigger!")

    # 4. Restore threshold
    print("\nRestoring trigger threshold to >85...")
    api_call("trigger.update", {
        "triggerid": triggerid,
        "expression": f"last(/docker-host-01/vfs.fs.size[/mnt/valkey-data,pused])>85"
    }, token)
    
    subprocess.run(["docker", "exec", "estate-zabbix-server-1", "zabbix_server", "-R", "config_cache_reload"], check=False)
    
    # Verify restore
    restored_trigger = api_call("trigger.get", {"triggerids": triggerid, "expandExpression": 1}, token)
    if restored_trigger:
        print(f"Trigger restored: {restored_trigger[0]['expression']}")
    
    print("--- TEST MODE COMPLETE ---")

def provision(test_mode=False):
    # Wait for Zabbix API to be up
    for _ in range(30):
        try:
            requests.get("http://localhost:8082")
            break
        except requests.exceptions.ConnectionError:
            time.sleep(2)

    # Login
    print("Logging into Zabbix...")
    token = api_call("user.login", {"username": ZABBIX_USER, "password": ZABBIX_PASS})
    users = api_call("user.get", {"filter": {"username": ZABBIX_USER}}, token)
    admin_userid = users[0]["userid"] if users else "1"
    
    print("Provisioning Zabbix...")
    
    # Get or Create Hostgroup
    groups = api_call("hostgroup.get", {"filter": {"name": ["Linux servers"]}}, token)
    if not groups:
        group_resp = api_call("hostgroup.create", {"name": "Linux servers"}, token)
        groupid = group_resp["groupids"][0]
    else:
        groupid = groups[0]["groupid"]

    # Get, Create, or Update Host
    hosts = api_call("host.get", {"filter": {"host": ["docker-host-01"]}}, token)
    host_params = {
        "host": "docker-host-01",
        "groups": [{"groupid": groupid}]
    }
    
    if hosts:
        hostid = hosts[0]["hostid"]
        host_params["hostid"] = hostid
        # Do NOT send interfaces on update to avoid linked item errors
        api_call("host.update", host_params, token)
        print("Updated existing host docker-host-01")
    else:
        host_params["interfaces"] = [{"type": 1, "main": 1, "useip": 0, "ip": "", "dns": "zabbix-agent", "port": "10050"}]
        host_resp = api_call("host.create", host_params, token)
        hostid = host_resp["hostids"][0]
        print("Created new host docker-host-01")

    # Add Disk Item if it doesn't exist
    items = api_call("item.get", {"hostids": hostid, "filter": {"key_": "vfs.fs.size[/mnt/valkey-data,pused]"}}, token)
    if not items:
        # Get interface ID
        interfaces = api_call("hostinterface.get", {"hostids": hostid}, token)
        interfaceid = interfaces[0]["interfaceid"] if interfaces else "1"
        
        api_call("item.create", {
            "name": "Valkey Data Disk Usage",
            "key_": "vfs.fs.size[/mnt/valkey-data,pused]",
            "hostid": hostid,
            "interfaceid": interfaceid,
            "type": 0, # Zabbix agent
            "value_type": 0, # Numeric float
            "delay": "30s"
        }, token)
        
    # Add Trigger if it doesn't exist
    triggers = api_call("trigger.get", {"hostids": hostid, "filter": {"description": "High disk usage on /mnt/valkey-data"}}, token)
    if not triggers:
        trigger_resp = api_call("trigger.create", {
            "description": "High disk usage on /mnt/valkey-data",
            "expression": f"last(/docker-host-01/vfs.fs.size[/mnt/valkey-data,pused])>85",
            "priority": 4 # High
        }, token)
        triggerid = trigger_resp["triggerids"][0]
    else:
        triggerid = triggers[0]["triggerid"]

    # Webhook Media Type
    mediatypes = api_call("mediatype.get", {"filter": {"name": "Correlation Engine Webhook"}}, token)
    webhook_script = """
var req = new HttpRequest();
req.addHeader('Content-Type: application/json');
var payload = JSON.parse(value);
if (payload.event_time) {
    payload.event_time = payload.event_time.replace(/\\./g, '-');
}
req.post('http://host.docker.internal:8000/webhooks/zabbix', JSON.stringify(payload));
return 'OK';
"""
    if not mediatypes:
        mediatype_resp = api_call("mediatype.create", {
            "type": 4, # Webhook
            "name": "Correlation Engine Webhook",
            "status": 0, # Enabled
            "script": webhook_script.strip(),
            "parameters": [{"name": "value", "value": "{ALERT.MESSAGE}"}]
        }, token)
        mediatypeid = mediatype_resp["mediatypeids"][0]
    else:
        mediatypeid = mediatypes[0]["mediatypeid"]
        # Update just in case the script needs fixing
        api_call("mediatype.update", {
            "mediatypeid": mediatypeid,
            "status": 0, # Enabled
            "script": webhook_script.strip()
        }, token)

    # Assign MediaType to Admin user so they can receive alerts
    user_medias = api_call("user.get", {"userids": admin_userid, "selectMedias": "extend"}, token)
    admin_user = user_medias[0]
    has_webhook = any(m["mediatypeid"] == mediatypeid for m in admin_user.get("medias", []))
    if not has_webhook:
        new_media = {
            "mediatypeid": mediatypeid,
            "sendto": ["admin"],
            "active": 0,
            "severity": 63,
            "period": "1-7,00:00-24:00"
        }
        medias = admin_user.get("medias", []) + [new_media]
        api_call("user.update", {"userid": admin_userid, "medias": medias}, token)

    # Create Action
    actions = api_call("action.get", {"filter": {"name": "Correlation Engine Disk Alerts"}}, token)
    if not actions:
        api_call("action.create", {
            "name": "Correlation Engine Disk Alerts",
            "eventsource": 0, # triggers
            "status": 0, # ENABLED
            "esc_period": "1h",
            "filter": {
                "evaltype": 0, # AND/OR
                "conditions": [
                    {
                        "conditiontype": 1, # Host
                        "operator": 0, # =
                        "value": hostid
                    }
                ]
            },
            "operations": [
                {
                    "operationtype": 0, # Send message
                    "esc_period": 0,
                    "esc_step_from": 1,
                    "esc_step_to": 1,
                    "opmessage_usr": [
                        {"userid": admin_userid}
                    ],
                    "opmessage": {
                        "default_msg": 0,
                        "mediatypeid": mediatypeid,
                        "subject": "Disk Alert",
                        "message": '{"host": "{HOST.NAME}", "trigger_name": "{EVENT.NAME}", "severity": "{EVENT.SEVERITY}", "item_key": "{ITEM.KEY1}", "item_value": "{ITEM.VALUE1}", "event_time": "{EVENT.DATE}T{EVENT.TIME}Z"}'
                    }
                }
            ]
        }, token)

    # Verification Print
    print("\n[divergence_table] Zabbix Host / Items Verification:")
    final_items = api_call("item.get", {"hostids": hostid, "output": ["name", "key_"]}, token)
    final_triggers = api_call("trigger.get", {"hostids": hostid, "output": ["description"]}, token)
    
    print(f"Host: docker-host-01 (ID: {hostid})")
    print("Configured Items:")
    for item in final_items:
        print(f"  - {item['name']} ({item['key_']})")
        
    print("Configured Triggers:")
    for t in final_triggers:
        print(f"  - {t['description']}")
        
    print("\nConfigured User Medias for Admin:")
    final_user_medias = api_call("user.get", {"userids": admin_userid, "selectMedias": "extend"}, token)
    if final_user_medias:
        print(json.dumps(final_user_medias[0].get("medias", []), indent=2))
        
    if test_mode:
        run_test_mode(token, triggerid)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run test mode to temporarily lower trigger threshold and check delivery")
    args = parser.parse_args()
    provision(test_mode=args.test)
