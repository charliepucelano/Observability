# Observability Stack

This repository contains the configuration and infrastructure as code for the home lab's observability stack. It is built around the modern Grafana/Prometheus/Loki ecosystem and runs as a set of Docker containers via `docker-compose`.

## Architecture Overview

The observability stack includes the following core components:

* **[Grafana](https://grafana.com/):** The visual dashboarding engine. Runs on port `3000`.
* **[Prometheus](https://prometheus.io/):** The time-series database and scraping engine for metrics. Runs on port `9090`.
* **[Prometheus Pushgateway](https://prometheus.io/docs/practices/pushing/):** An intermediary service for ephemeral and batch jobs (like our AIDA64 powershell script) to push metrics to. Runs on port `9091`.
* **[Loki](https://grafana.com/oss/loki/):** The log aggregation system, designed to be highly cost-effective and easy to operate. Runs on port `3100`.
* **[Promtail](https://grafana.com/docs/loki/latest/clients/promtail/):** The agent that ships local logs to the Loki instance.

## Installation & Usage

1. Ensure Docker and Docker Compose are installed on the host.
2. Clone this repository to your target directory (e.g., `D:\observability`).
3. Run `docker-compose up -d` to start the stack.
4. Access Grafana at `http://localhost:3000`.

### Data Persistence

By default, the `docker-compose.yml` mounts several local directories for persistent storage:
* `prometheus/data`: Persistent storage for Prometheus metrics.
* `grafana/data`: Persistent storage for Grafana plugins, dashboards, and SQLite database.
* `grafana/provisioning`: Configuration files to automatically provision Grafana Alert Rules as Code.
* `loki/data`: Persistent storage for Loki logs and chunks.

*Note: Data directories are excluded from version control to prevent committing large databases. Provisioning configurations are tracked in Git.*

## Dashboards

Several pre-configured dashboards are included in the repository as `.json` files:

* `aida64-dashboard.json`: PC health and thermal monitoring via AIDA64 metrics.
* `dashboard-node-optimized.json`: Node exporter metrics (CPU, Memory, Disk, Network).
* `cadvisor-dashboard-improved.json`: Docker container metrics (cAdvisor).
* `loki-dashboard-improved.json`: System and container log viewing.
* `uptime-dashboard.json`: Status and uptime monitoring.
* `blackbox-dashboard-optimized.json`: Network probing and endpoint health.

These can be imported directly into Grafana via the UI (`Dashboards` -> `Import` -> `Upload JSON file`).

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
