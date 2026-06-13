import json

with open('d:/observability/uptime-dashboard.json', 'r') as f:
    dashboard = json.load(f)

for panel in dashboard.get('panels', []):
    if panel['id'] == 5:
        # Uptime and SSL Certificates Overview
        # Ensure format: table
        for target in panel.get('targets', []):
            target['format'] = 'table'
        
        # Remove renaming from organize
        for t in panel.get('transformations', []):
            if t['id'] == 'organize':
                t['options']['renameByName'] = {}
                t['options']['excludeByName'] = {
                    "Time": True, "Time 1": True, "Time 2": True, "Time 3": True, "job": True
                }
        
        # Change overrides to match by Frame Ref ID instead of name!
        # Frame Ref ID 'A' -> Uptime Status
        # Frame Ref ID 'B' -> HTTP Status Code
        # Frame Ref ID 'C' -> SSL Certificate Expiry
        # Wait, joinByField might merge frames into a single frame, making byFrameRefID invalid!
        # If we use joinByField, all columns are in one frame.
        # Instead, match by regex:
        # /.*success.*/ or similar? No, columns are named "Value", "Value 1", "Value 2" or "Value #A"
        panel['fieldConfig']['overrides'] = [
            {
                "matcher": {"id": "byRegexp", "options": ".*Value.*A.*|.*Value$"},
                "properties": [
                    {"id": "displayName", "value": "Uptime Status"},
                    {"id": "mappings", "value": [
                        {"type": "value", "options": {"0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}}}
                    ]},
                    {"id": "custom.cellOptions", "value": {"type": "color-background"}}
                ]
            },
            {
                "matcher": {"id": "byRegexp", "options": ".*Value.*B.*|.*Value 1.*"},
                "properties": [
                    {"id": "displayName", "value": "HTTP Status Code"},
                    {"id": "decimals", "value": 0},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 200}, {"color": "yellow", "value": 300}, {"color": "red", "value": 400}]}},
                    {"id": "custom.cellOptions", "value": {"type": "color-text"}}
                ]
            },
            {
                "matcher": {"id": "byRegexp", "options": ".*Value.*C.*|.*Value 2.*"},
                "properties": [
                    {"id": "displayName", "value": "SSL Certificate Expiry"},
                    {"id": "unit", "value": "d"},
                    {"id": "decimals", "value": 0},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 15}, {"color": "green", "value": 30}]}},
                    {"id": "custom.cellOptions", "value": {"type": "color-text"}}
                ]
            }
        ]
        
    if panel['id'] == 7:
        # SSL Certificate Expiration Warnings
        for t in panel.get('transformations', []):
            if t['id'] == 'organize':
                t['options']['renameByName'] = {}
                t['options']['excludeByName'] = {"Time": True, "job": True}
        
        panel['fieldConfig']['overrides'] = [
            {
                "matcher": {"id": "byRegexp", "options": ".*Value.*"},
                "properties": [
                    {"id": "displayName", "value": "Days Until Expiration"},
                    {"id": "custom.cellOptions", "value": {"type": "color-text"}}
                ]
            }
        ]

with open('d:/observability/uptime-dashboard.json', 'w') as f:
    json.dump(dashboard, f, indent=2)

print("Fixed dashboard JSON")
