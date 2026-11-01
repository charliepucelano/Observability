# Observability (A9_Mega)

- Root: `D:\observability`. Scripts legacy still under `D:\scripts` until migrate.
- Local agent entry: `bin\agent-cli.cmd` / `bin\agent-cli.ps1` (Linus). Prefer this over ad-hoc shells for agent work.
- Weekly DevOps brief: OWUI Local (`analyze_local.py` / `weekly-analysis.ps1 -Engine Local`). Do not route through OpenClaw; OpenClaw stays stopped.
- After Docker/host updates: `D:\scripts\Test-PostUpdateHealth.ps1` (OWUI must answer HTTP 200 on `http://127.0.0.1:11000/api/version`).
- Document material changes at the top of `recent_fixes.md`.
- Charlie: concise, critical, evidence over guesses; Spanish or English to match him; never German in replies to him.
