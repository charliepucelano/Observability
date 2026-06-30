# Observability Stack

This repository contains the configuration and infrastructure as code for the home lab's observability stack. It is built around the modern Grafana/Prometheus/Loki ecosystem and runs as a set of Docker containers via `docker-compose`.

## Architecture Overview

The observability stack includes the following core components:

* **[Grafana](https://grafana.com/):** The visual dashboarding engine. Runs on port `3000`.
* **[Prometheus](https://prometheus.io/):** The time-series database and scraping engine for metrics. Runs on port `9090`.
* **[Prometheus Pushgateway](https://prometheus.io/docs/practices/pushing/):** An intermediary service for ephemeral and batch jobs (like our AIDA64 powershell script) to push metrics to. Runs on port `9091`.
* **[VictoriaMetrics](https://victoriametrics.com/):** High-performance, scalable time-series database configured for 1-year long-term retention of Prometheus metrics via remote write. Runs on port `8428`.
* **[Loki](https://grafana.com/oss/loki/):** The log aggregation system, designed to be highly cost-effective and easy to operate. Runs on port `3100`.
* **[Promtail](https://grafana.com/docs/loki/latest/clients/promtail/):** The agent that ships local logs to the Loki instance.
* **[Speedtest Exporter](https://github.com/MiguelNDeCarvalho/speedtest-exporter):** Runs hourly automated ISP speed tests to monitor network degradation.

## Installation & Usage

1. Ensure Docker and Docker Compose are installed on the host.
2. Clone this repository to your target directory (e.g., `D:\observability`).
3. Run `docker-compose up -d` to start the stack.
4. Access Grafana at `http://localhost:3000`.

### Data Persistence

By default, the `docker-compose.yml` mounts several local directories for persistent storage:
* `prometheus/data`: Persistent storage for recent Prometheus metrics (14 days).
* `victoriametrics/data`: Persistent storage for long-term metrics (1 year).
* `grafana/data`: Persistent storage for Grafana plugins, dashboards, and SQLite database.
* `grafana/provisioning`: Configuration files to automatically provision Grafana Dashboards, Alerting Contact Points (Telegram), and Notification Policies.
* `loki/data`: Persistent storage for Loki logs and chunks.

*Note: Data directories are excluded from version control to prevent committing large databases. Provisioning configurations are tracked in Git.*

## Dashboards

Several pre-configured dashboards are included in the repository as `.json` files inside `grafana/provisioning/dashboards/json/`:

* `aida64-dashboard.json`: PC health and thermal monitoring via AIDA64 metrics.
* `dashboard-node-optimized.json`: Node exporter metrics (CPU, Memory, Disk, Network).
* `cadvisor-dashboard-improved.json`: Docker container metrics (cAdvisor).
* `loki-dashboard-improved.json`: System and container log viewing.
* `uptime-dashboard.json`: Status, SLO tracking, and uptime monitoring.
* `blackbox-dashboard-optimized.json`: Network probing and endpoint health.

These dashboards are automatically provisioned by Grafana on startup. You do not need to import them manually.

## AIDA64 Integration

This stack integrates with AIDA64 to capture hardware thermals, fan speeds, and voltages.
The process works as follows:

1. AIDA64 is configured to write a metrics log file (or WMI).
2. A PowerShell scheduled task (`aida-to-pushgateway.ps1`) runs continuously in the background, parsing the AIDA64 metrics.
3. The script formats the data into Prometheus format and `POST`s it to the `Pushgateway` (`http://localhost:9091`).
4. Prometheus scrapes the Pushgateway and stores the historical thermal data.
5. Grafana visualizes the data using the `aida64-dashboard.json` dashboard.

## AI Integration: Proactive Silent Error Hunter

This stack is deeply integrated with the host's local AI (LM Studio running `Qwen3-30B`). A daily scheduled job (`silent_error_hunter.py`) connects to Loki at 07:30 AM to query for logs matching `(?i)(error|warn|exception|panic)` over the last 24 hours.

Instead of flooding alerts for every warning, it packages the raw logs and asks the local frontier model to summarize the top 3 critical, non-crashing (silent) issues. The output is pushed to Telegram and appended to the weekly DevOps dump for broader architectural context.

**New:** The bot uses a Universal Interactive Execution flow. If the AI proposes an automated fix using an `<execute>` block, the Telegram message will include interactive "Approve/Reject" buttons, allowing you to run the PowerShell fix locally with one tap.

## AI Integration: Homelab Chat & RAG

The observability stack includes a local RAG (Retrieval-Augmented Generation) system built on ChromaDB. This allows you to chat directly with your homelab via Telegram using the `/ask` command.

1. `rag_ingest.py` indexes your local documentation (e.g., `system_architecture.md`, `recent_fixes.md`).
2. When you send `/ask <query>` to the Telegram bot, `ask_homelab.py` queries ChromaDB for context.
3. The context and your query are sent to the local LM Studio instance (`qwen/qwen3-30b-a3b-2507`) to generate an accurate, context-aware answer. If the AI detects an issue that can be solved via PowerShell, it proposes a fix using the `<execute>` tags, spawning interactive Approve/Reject buttons in Telegram.
4. The bot can also proactively triage crashed Docker containers by fetching their last logs from Loki and diagnosing them via the LLM, again proposing automated one-touch interactive fixes.

## OpenClaw Skills

This repository also hosts the custom OpenClaw AI agent skills used by the homelab, located in the `skills/` directory.

* `skills/devops_analyzer`: Analyzes weekly DevOps metrics (like Loki logs, Prometheus thermal data, and memory stats) via Perplexity/Qwen.

These skills are centrally version-controlled here but are symlinked into the OpenClaw workspace (`D:\openclaw\data\skills`) so the agent can execute them.

## Automation & Maintenance Scripts

The `D:\scripts` directory contains various PowerShell and Node automation tasks running as scheduled tasks or NSSM services:

* **Container Watchdog (`container-watchdog.ps1`):** A continuous NSSM background service that polls for exited containers and automatically restarts them, escalating to Telegram if the restart limit is breached.
* **Backup Verification (`verify-backup.ps1`):** A weekly scheduled task that verifies the integrity and existence of backups across services (Paperless, OpenClaw, Veeam, Firebase) and pushes alerts via Telegram.
* **RAG File Watcher (`rag-file-watcher.ps1`):** An NSSM service that watches core documentation (like `README.md` and `recent_fixes.md`) for changes and automatically triggers a ChromaDB RAG re-index.
* **Process Monitor (`process-monitor.ps1`):** A background service that samples top CPU/RAM usage every 60s and ships it to Loki for correlation.
* **Synthetic User Journeys (`synthetic-tests/`):** Playwright scripts (e.g., `immich-journey.js`) orchestrated by `run-synthetic-tests.ps1` to test full E2E application usability (e.g., uploading and verifying a test image).

## Maintenance

### Resetting Data
If you need to completely wipe the metrics or logs (e.g., due to corruption or to free up space), you can stop the containers and clear the respective data directories:

```bash
docker-compose down
# Clear Prometheus metrics
rm -rf prometheus/data/*
# Clear Loki logs
rm -rf loki/data/*
docker-compose up -d
```
