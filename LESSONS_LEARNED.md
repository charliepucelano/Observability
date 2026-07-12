# Observability Stack Lessons Learned

## Infrastructure Knowledge
- **TSDB and Log Bloat**: Be incredibly careful when committing Grafana, Prometheus, or Loki configurations to GitHub. `prometheus/data/`, `loki/data/` and `grafana/data/` can quickly balloon to gigabytes of TSDB files and SQLite databases. Always add them to `.gitignore` from day one!

## Python vs PowerShell on Windows
- **UnicodeEncodeError with Python**: When a Python script prints UTF-8 symbols (like Emojis `✅`, `⚠️`) to `sys.stdout` and is executed by PowerShell, Windows will often crash the script with a `UnicodeEncodeError`. 
  - **The Fix**: Explicitly reconfigure the standard output inside your Python script: `sys.stdout.reconfigure(encoding='utf-8')` before printing any rich text or emojis that will be consumed by PowerShell (`$output = python script.py`).
- **PowerShell 5.1 JSON Encoding**: PowerShell 5.1's \ConvertTo-Json\ command silently mangles Unicode strings and Emojis into ASCII question marks (\?\) when making API calls, even if you set the output encoding to UTF-8.
  - **The Fix**: Do not pipe your payload to \ConvertTo-Json\. Instead, pass the raw Hashtable directly to \Invoke-RestMethod -Body $body\. This forces PowerShell to send the payload natively as \pplication/x-www-form-urlencoded\, which perfectly preserves emojis and Unicode.
