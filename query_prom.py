import urllib.request
import json
req = urllib.request.urlopen('http://localhost:9090/api/v1/query?query=probe_ssl_earliest_cert_expiry%7Bjob=%22uptime%22%7D')
res = json.loads(req.read())
print(json.dumps(res, indent=2))
