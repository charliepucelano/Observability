import json

with open('d:/observability/grafana/provisioning/dashboards/json/loki-dashboard-improved.json', 'r', encoding='utf-8-sig') as f:
    d = json.load(f)

for p in d.get('panels', []):
    for t in p.get('targets', []):
        print(f"Panel: {p.get('title')} - Target: {t.get('expr')}")

# Also check elements (Grafana v11?)
for e in d.get('elements', []):
    pass # Wait, earlier I found out that panels is the right key? No, earlier I wrote a recursive script because panels/targets was not finding everything!

def print_exprs(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'expr' and isinstance(v, str):
                print(f"EXPR: {v}")
            else:
                print_exprs(v)
    elif isinstance(obj, list):
        for item in obj:
            print_exprs(item)

print_exprs(d)
