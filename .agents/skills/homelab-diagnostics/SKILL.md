---
name: homelab-diagnostics
description: Diagnostic runbook and procedures to inspect Geekom A9 host thermals, container health, SLO error budgets, Loki error logs, and Prometheus metrics.
---

# Homelab Diagnostics

Runbook and queries for real-time observability and health diagnostics across the Geekom A9 homelab environment.

## Endpoints Reference

| Service | Internal URL | Purpose |
| :--- | :--- | :--- |
| **Prometheus** | `http://localhost:9090` | Instant & range PromQL metrics (15d retention) |
| **VictoriaMetrics** | `http://localhost:8428` | Long-term PromQL metrics (12m retention) |
| **Loki** | `http://localhost:3100` | LogQL ingestion and querying |
| **Blackbox Exporter** | `http://localhost:9115` | HTTP/TCP synthetic availability probes |

---

## 1. Host Thermal & Power Snapshot

Inspect hardware telemetry pushed from AIDA64 via Pushgateway to Prometheus.

### PromQL Queries

* **CPU Diode Temperature:** `aida64_temp_cpu_diode_celsius` (Warning: >80°C, Critical: >90°C)
* **GPU Temperature:** `aida64_temp_gpu_celsius`
* **GPU SoC Temperature:** `aida64_temp_gpu_soc_celsius`
* **GPU Power:** `aida64_power_gpu_watts`
* **CPU Package Power:** `aida64_power_cpu_package_watts`
* **CPU Load (Average):** `aida64_cpu_load_percent`
* **RAM Used / Free:** `aida64_memory_used_mb` / `aida64_memory_free_mb`
* **Storage Thermals:** `aida64_temp_hdd1_celsius`, `aida64_temp_hdd2_celsius`

### Quick Inspection Command
```powershell
Invoke-RestMethod -Uri "http://localhost:9090/api/v1/query?query=aida64_temp_cpu_diode_celsius" | Select-Object -ExpandProperty data | Select-Object -ExpandProperty result
```

> [!NOTE]
> If thermal metrics report timestamps older than 5 minutes, the AIDA64 Pushgateway script on the host may be paused or delayed.

---

## 2. Container Status & Uptime

Audit container uptime and lifecycle events via cAdvisor metrics in Prometheus.

### PromQL Queries
* **Active Containers & Start Times:**
  ```promql
  container_start_time_seconds{name!=""}
  ```
* **High CPU Utilization Containers:**
  ```promql
  topk(5, rate(container_cpu_usage_seconds_total{name!=""}[5m]) * 100)
  ```
* **Memory Usage vs Limits:**
  ```promql
  container_memory_working_set_bytes{name!=""}
  ```

---

## 3. Production SLO Error Budget

Track 30-day availability and remaining error budgets for production services against the 99.5% SLO target.

### PromQL Queries
* **Remaining Error Budget Ratio:**
  ```promql
  slo:error_budget_remaining:ratio
  ```
  * `ratio >= 0.5`: ✅ Healthy
  * `0.0 <= ratio < 0.5`: ⚠️ Burning budget
  * `ratio < 0.0`: 🔴 Exhausted
* **30-Day Availability Percentage:**
  ```promql
  slo:probe_success:avg30d
  ```

---

## 4. Loki Container Error Log Search

Search the last 6 hours of logs in Loki for errors across specific applications.

### LogQL Query Pattern
```logql
{container=~".*<app_name>.*"} |= "error"
```

### Quick Loki Inspection (PowerShell)
```powershell
$nowNs = [int64]((Get-Date).ToUniversalTime() - (Get-Date "1970-01-01")).TotalMilliseconds * 1000000
$startNs = $nowNs - (6 * 3600 * 1000000000)
$query = [System.Web.HttpUtility]::UrlEncode('{container=~".*immich.*"} |= "error"')
Invoke-RestMethod -Uri "http://localhost:3100/loki/api/v1/query_range?query=$query&start=$startNs&end=$nowNs&limit=15"
```

---

## 5. Synthetic Endpoint Latency (Blackbox)

Evaluate p50, p90, and p99 response times for Leyforge services.

### PromQL Query
```promql
probe_duration_seconds{job="uptime", instance=~".*<service>.*"}
```

---

## 6. Prometheus Active Configuration

Retrieve active Prometheus configuration via its API with secrets redacted:
```powershell
Invoke-RestMethod -Uri "http://localhost:9090/api/v1/status/config" | Select-Object -ExpandProperty data | Select-Object -ExpandProperty yaml
```

> [!WARNING]
> Always scrub basic auth passwords, API keys, and bearer tokens when sharing or logging configuration output.
