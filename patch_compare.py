with open("estate/capture/compare.py") as f:
    content = f.read()

fallback_code = """
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
"""

content = content.replace("def main():", fallback_code + "\ndef main():")
content = content.replace(
    'component = labels.get("instance") or labels.get("pod") or labels.get("host") or "Unknown"',
    'component = labels.get("component") or RULE_COMPONENTS.get(alertname) or labels.get("instance") or labels.get("pod") or labels.get("host") or "Unknown"',
)

with open("estate/capture/compare.py", "w") as f:
    f.write(content)
