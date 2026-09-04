---
name: homelab-ops-inspector
description: Operational runbook to audit backup freshness, disk headroom (C:, D:, F:), scheduled task timelines, and Home Assistant sensor states.
---

# Homelab Operations Inspector

Operational runbook and auditing procedures for storage capacity, nightly backup pipelines, and scheduled task timelines.

---

## 1. Backup Job Freshness & Health

Audit the status and timeliness of backup jobs by querying Promtail-ingested logs in Loki (`D:\backups\logs`).

### LogQL Search Patterns
* **Pre-Backup Phase:**
  ```logql
  {job=~".*backup.*"} |= "pre-backup"
  ```
* **Robocopy Mirror Phase:**
  ```logql
  {job=~".*backup.*"} |= "mirror"
  ```
* **Backup Verification:**
  ```logql
  {job=~".*backup.*"} |= "BACKUP VERIFICATION"
  ```

### Freshness Thresholds
* **Healthy:** Last successful entry < 48 hours ago.
* **Warning:** Last entry between 48h and 72h ago.
* **Critical:** No log entries in the last 72 hours.

---

## 2. Drive Headroom & Growth Forecasting

Monitor storage consumption across host drives (`C:`, `D:`, `F:`) using Windows Exporter metrics in Prometheus.

### PromQL Queries
* **Free Space by Volume:**
  ```promql
  windows_logical_disk_free_bytes
  ```
* **Total Volume Capacity:**
  ```promql
  windows_logical_disk_size_bytes
  ```
* **Percent Utilization:**
  ```promql
  100 - ((windows_logical_disk_free_bytes / windows_logical_disk_size_bytes) * 100)
  ```

### Veeam Backup Target (F: Drive) Forecast
Calculate 7-day rate of consumption:
```promql
(windows_logical_disk_free_bytes{volume="F:"} offset 7d - windows_logical_disk_free_bytes{volume="F:"}) / 7
```
* **Capacity Alert:** Flag when drive usage exceeds 80% (Warning) or 90% (Critical).
* Estimate days remaining until 90% full:
  $$\text{Days to 90\%} = \frac{\text{Current Free Bytes} - (\text{Total Bytes} \times 0.10)}{\text{Daily Consumption Bytes}}$$

---

## 3. Scheduled Tasks Execution Timeline

Examine job execution timestamps in Loki over the last 72 hours to detect job overlaps or resource contention.

### Task Log Filters
* **Nightly Pre-Backup:** `{job=~".*backup.*"} |~ "START|DONE|FAIL|pre-backup"`
* **Robocopy Mirror:** `{job=~".*backup.*"} |~ "mirror|ROBOCOPY"`
* **Verification Check:** `{job=~".*backup.*"} |~ "VERIFICATION|VERIFY"`
* **Weekly Analysis:** `{job=~".*backup.*"} |~ "weekly|analysis|dump"`

### Contention Diagnostics
When investigating task failures, verify:
1. Did the Robocopy mirror run while a database container was performing a snapshot?
2. Did backup verification conflict with nightly disk-heavy scraping or log compactions?

---

## 4. Home Assistant Telemetry (Optional)

When a Home Assistant instance is active (`http://localhost:8123`) with a Long-Lived Access Token:

* Check smart plug power draw: `sensor.homelab_power` / `sensor.geekom_power`
* Check UPS battery level and state: `sensor.geekom_ups_battery`
* Check ambient lab temperatures: `sensor.room_temperature` / `sensor.ambient_temperature`
