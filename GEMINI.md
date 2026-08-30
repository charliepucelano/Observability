# Homelab Observability Stack — Antigravity Workspace Guide

Central observability infrastructure monitoring host hardware, containers, networks, and homelab services.

## Architecture & Containers
- **Prometheus** (`9090`): 60s scrape intervals, 15-day local TSDB retention (`--storage.tsdb.retention.time=15d`).
- **VictoriaMetrics** (`8428`): Long-term metric storage (12-month retention, `-dedup.minScrapeInterval=60s`).
- **Grafana** (`3000` / `grafana.leyforge.com`): Dashboards & alerts provisioned from Git.
- **Loki** (`3100`) & **Promtail**: Structured log ingestion with Docker SD and drop filters.
- **Blackbox Exporter** (`9115`): HTTP/TCP probing for `tier="prod"` services.
- **cAdvisor** (`8080`) & **Node Exporter** (`9100`): Host/container metrics.

## Project Rules & BMAD Layer
Rules are located in `.agents/rules/`:
- `homelab-guardrails.md`: Resource limits, quiet home lab profile, non-destructive edits.
- `scrape-and-retention.md`: 60s cadence standard, VictoriaMetrics deduplication, log rotation.

## Core Invariants
1. **Never lower scrape intervals below 60s**: Prevents thermal spikes and fan noise.
2. **Alert Scope**: All uptime alerts in `alerts.yaml` must filter on `tier="prod"`.
3. **Reference Past Fixes**: Always check `recent_fixes.md` before diagnosing infrastructure anomalies.
