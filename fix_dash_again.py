import json

filepath = 'd:/observability/grafana/provisioning/dashboards/json/loki-dashboard-improved.json'
with open(filepath, 'r', encoding='utf-8-sig') as f:
    d = json.load(f)

# The old bad regex we injected:
old_bad_regex = '|~ "(?i)(?:^|\\\\s)(level[=\\"\\\']?${level:regex}[\\"\\\']?|\\\\[${level:regex}\\\\]|^${level:regex})"'

# The new good regex:
# We use ${level:pipe} and explicit parentheses.
# Matches:
# 1) level=error, level="error", level: error
# 2) [error]
# 3) error at the beginning of the line
new_good_regex = '|~ "(?i)(level[=:]\\\\s*\\\\\"?(${level:pipe})\\\\\"?|\\\\[(${level:pipe})\\\\]|^(${level:pipe})\\\\b)"'

def replace_exprs(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'expr' and isinstance(v, str):
                if old_bad_regex in v:
                    obj[k] = v.replace(old_bad_regex, new_good_regex)
            else:
                replace_exprs(v)
    elif isinstance(obj, list):
        for item in obj:
            replace_exprs(item)

replace_exprs(d)

with open(filepath, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2)

print("Dashboard updated with new regex.")
