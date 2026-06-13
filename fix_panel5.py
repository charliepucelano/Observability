import json

with open('d:/observability/uptime-dashboard.json', 'r') as f:
    dashboard = json.load(f)

for panel in dashboard.get('panels', []):
    if panel['id'] == 5:
        # We will use "Merge" transformation instead of "joinByField"
        # And we'll use format="time_series" with legendFormat.
        
        # Targets
        panel['targets'][0]['format'] = 'time_series'
        panel['targets'][0]['legendFormat'] = 'Uptime Status'
        
        panel['targets'][1]['format'] = 'time_series'
        panel['targets'][1]['legendFormat'] = 'HTTP Status Code'
        
        panel['targets'][2]['format'] = 'time_series'
        panel['targets'][2]['legendFormat'] = 'SSL Certificate Expiry'
        
        # Transformations
        panel['transformations'] = [
            {
                "id": "merge",
                "options": {}
            },
            {
                "id": "organize",
                "options": {
                    "excludeByName": {
                        "Time": True,
                        "job": True
                    },
                    "indexByName": {},
                    "renameByName": {
                        "instance": "Service URL"
                    }
                }
            }
        ]
        
        # Overrides - now we match exactly by the legendFormat names
        panel['fieldConfig']['overrides'] = [
            {
                "matcher": {"id": "byName", "options": "Uptime Status"},
                "properties": [
                    {"id": "mappings", "value": [
                        {"type": "value", "options": {"0": {"text": "DOWN", "color": "red"}, "1": {"text": "UP", "color": "green"}}}
                    ]},
                    {"id": "custom.cellOptions", "value": {"type": "color-background"}}
                ]
            },
            {
                "matcher": {"id": "byName", "options": "HTTP Status Code"},
                "properties": [
                    {"id": "decimals", "value": 0},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 200}, {"color": "yellow", "value": 300}, {"color": "red", "value": 400}]}},
                    {"id": "custom.cellOptions", "value": {"type": "color-text"}}
                ]
            },
            {
                "matcher": {"id": "byName", "options": "SSL Certificate Expiry"},
                "properties": [
                    {"id": "unit", "value": "d"},
                    {"id": "decimals", "value": 0},
                    {"id": "thresholds", "value": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "yellow", "value": 15}, {"color": "green", "value": 30}]}},
                    {"id": "custom.cellOptions", "value": {"type": "color-text"}}
                ]
            }
        ]

with open('d:/observability/uptime-dashboard.json', 'w') as f:
    json.dump(dashboard, f, indent=2)

print("Panel 5 updated to use Merge and time_series")
