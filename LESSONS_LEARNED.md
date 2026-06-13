# Observability Stack Lessons Learned

## Infrastructure Knowledge
- **TSDB and Log Bloat**: Be incredibly careful when committing Grafana, Prometheus, or Loki configurations to GitHub. `prometheus/data/`, `loki/data/` and `grafana/data/` can quickly balloon to gigabytes of TSDB files and SQLite databases. Always add them to `.gitignore` from day one!

## Python vs PowerShell on Windows
- **UnicodeEncodeError with Python**: When a Python script prints UTF-8 symbols (like Emojis `✅`, `⚠️`) to `sys.stdout` and is executed by PowerShell, Windows will often crash the script with a `UnicodeEncodeError`. 
  - **The Fix**: Explicitly reconfigure the standard output inside your Python script: `sys.stdout.reconfigure(encoding='utf-8')` before printing any rich text or emojis that will be consumed by PowerShell (`$output = python script.py`).
