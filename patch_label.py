
with open("estate/capture/label.py") as f:
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
    'comp = labels.get("component") or labels.get("instance") or labels.get("pod") or labels.get("host") or ""',
    'comp = labels.get("component") or RULE_COMPONENTS.get(name) or labels.get("instance") or labels.get("pod") or labels.get("host") or ""',
)

with open("estate/capture/label.py", "w") as f:
    f.write(content)
