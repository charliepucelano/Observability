# Recent Corrective Fixes (Do Not Re-diagnose)

This is a running changelog of fixes and mitigations applied to the homelab. When analyzing logs and metrics, please assume these issues are already resolved and do not propose them as new solutions unless the metrics show the mitigation has explicitly failed.

- **[2026-06-12] WSL Memory Limit**: Applied a strict 6GB memory limit in `.wslconfig` to prevent `vmmemWSL` (Docker Desktop) from exhausting the host's 128GB of RAM.
- **[2026-06-13] Process Monitor Integration**: Deployed `process-monitor.ps1` as a background service to sample Top CPU/RAM processes every 60s. Promtail now ingests this into Loki (`{job="windows-processes"}`) for historical correlation.
- **[2026-06-13] Immich Thumbnail Loop Fix**: Quarantined 485 corrupt image files (bad headers) from `/data/library/admin/Camera Roll/` that were causing the Immich thumbnail generation microservices to infinitely loop, resulting in 138,000+ errors in Loki and high system load.
- **[2026-06-14] DevOps Analyzer Chunking**: Fixed devops_analyzer script causing Chrome CDP timeouts and dropping content by improving the JS chunking logic.
- **[2026-06-14] OpenClaw CLI Cleanup**: Removed stale `repo-openclaw-cli-1` container that exited 5 weeks ago.
- **[2026-06-14] Blackbox Exporter Redirects**: Updated prometheus.yml targets to their final redirect destinations (e.g., adding `/login` or `/app/`) to eliminate noisy HTTP 301/302 warnings in the blackbox exporter logs.
