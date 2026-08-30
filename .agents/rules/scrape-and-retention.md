---
trigger: always_on
---

# Scrape & Retention Standards

## Cadence Invariants
- `global.scrape_interval: 60s`
- `global.evaluation_interval: 60s`
- VictoriaMetrics `-dedup.minScrapeInterval=60s`
- Speedtest exporter interval: `10800s` (3h)

## Scrape Target Discipline
- Separate targets into `tier: prod` and `tier: dev`.
- Do not add on-demand or local dev servers to 24/7 uptime monitoring.
