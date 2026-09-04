"""
title: Homelab Ops Inspector
description: Read-only operations tools for Geekom A9 homelab. Checks backup freshness via Loki logs, monitors backup drive headroom via Prometheus, audits scheduled task timelines, and optionally queries Home Assistant for power/thermal sensor data.
author: Carlos
version: 1.0.0
required_open_webui_version: 0.4.0
"""

import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import requests
from pydantic import BaseModel, Field


# ────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ────────────────────────────────────────────────────────────────────────────

_MAX_RESPONSE_BYTES = 4096


def _truncate(text: str, limit: int = _MAX_RESPONSE_BYTES) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [TRUNCATED — showing {limit} of {len(text)} bytes]"


def _ts_to_str(unix_ts: float) -> str:
    return datetime.fromtimestamp(float(unix_ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def _sanitize_label(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_\-]", "", raw)


# ────────────────────────────────────────────────────────────────────────────
# OpenWebUI Tool class
# ────────────────────────────────────────────────────────────────────────────


class Tools:
    class Valves(BaseModel):
        prometheus_url: str = Field(
            default="http://host.docker.internal:9090",
            description="Base URL of the Prometheus server.",
        )
        loki_url: str = Field(
            default="http://host.docker.internal:3100",
            description="Base URL of the Loki server.",
        )
        ha_url: str = Field(
            default="http://host.docker.internal:8123",
            description="Base URL of the Home Assistant server (optional).",
        )
        ha_token: str = Field(
            default="",
            description="Home Assistant Long-Lived Access Token (leave empty to disable HA queries).",
        )
        request_timeout: int = Field(
            default=15,
            description="HTTP request timeout in seconds.",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ── Internal helpers ────────────────────────────────────────────────

    def _prom_get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.valves.prometheus_url}{path}"
        resp = requests.get(url, params=params, timeout=self.valves.request_timeout)
        resp.raise_for_status()
        return resp.json()

    def _prom_instant(self, query: str) -> list:
        data = self._prom_get("/api/v1/query", {"query": query})
        if data.get("status") != "success":
            raise ValueError(data.get("error", "Unknown Prometheus error"))
        return data["data"]["result"]

    def _loki_get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.valves.loki_url}{path}"
        resp = requests.get(url, params=params, timeout=self.valves.request_timeout)
        resp.raise_for_status()
        return resp.json()

    def _loki_query_range(self, logql: str, hours_back: int = 48, limit: int = 20) -> list:
        now_ns = int(time.time() * 1e9)
        start_ns = now_ns - int(hours_back * 3600 * 1e9)
        params = {
            "query": logql,
            "start": str(start_ns),
            "end": str(now_ns),
            "limit": str(limit),
            "direction": "backward",
        }
        data = self._loki_get("/loki/api/v1/query_range", params)
        if data.get("status") != "success":
            raise ValueError(f"Loki query failed: {data.get('status', 'unknown')}")
        return data.get("data", {}).get("result", [])

    def _ha_get(self, path: str) -> dict:
        """Make a GET request to Home Assistant REST API."""
        if not self.valves.ha_token:
            raise ValueError("Home Assistant token not configured")
        url = f"{self.valves.ha_url}/api{path}"
        headers = {
            "Authorization": f"Bearer {self.valves.ha_token}",
            "Content-Type": "application/json",
        }
        resp = requests.get(url, headers=headers, timeout=self.valves.request_timeout)
        resp.raise_for_status()
        return resp.json()

    # ── Public tool methods ─────────────────────────────────────────────

    async def get_backup_status(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Check the status and freshness of homelab backup jobs by querying Loki
        for the most recent pre-backup, mirror, and verify-backup log entries.
        Reports whether each job completed successfully and how long ago.
        :return: Backup job status summary with freshness indicators.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Checking backup job logs in Loki", "done": False}}
            )
        try:
            # Query for backup-related logs ingested by Promtail from D:\backups\logs
            # Promtail mounts D:/backups/logs:/geekom/backup-logs:ro
            backup_jobs = {
                "Pre-Backup": '{job=~".*backup.*"} |= "pre-backup"',
                "Mirror": '{job=~".*backup.*"} |= "mirror"',
                "Verify-Backup": '{job=~".*backup.*"} |= "BACKUP VERIFICATION"',
            }

            lines = []
            now = time.time()

            for job_name, logql in backup_jobs.items():
                try:
                    streams = self._loki_query_range(logql, hours_back=72, limit=5)
                    if streams:
                        # Get the most recent log entry
                        latest_ts = 0
                        latest_msg = ""
                        for stream in streams:
                            for ts_ns, msg in stream.get("values", []):
                                ts = int(ts_ns) / 1e9
                                if ts > latest_ts:
                                    latest_ts = ts
                                    latest_msg = msg[:200]

                        if latest_ts > 0:
                            age_hours = (now - latest_ts) / 3600
                            freshness = "✅" if age_hours < 48 else "⚠️ stale"
                            lines.append(
                                f"• **{job_name}**: {freshness} — last seen {age_hours:.1f}h ago\n"
                                f"  Last entry: `{latest_msg}`"
                            )
                        else:
                            lines.append(f"• **{job_name}**: ❓ logs found but no timestamps parsed")
                    else:
                        lines.append(f"• **{job_name}**: ❌ no logs found in last 72h")
                except Exception as e:
                    lines.append(f"• **{job_name}**: query error — {e}")

            # Also check if Veeam metrics exist via pushgateway or windows_exporter
            try:
                # Try to find any filesystem metric for the F: drive (Veeam target)
                fs_results = self._prom_instant(
                    'windows_logical_disk_free_bytes{volume="F:"}'
                )
                if fs_results:
                    free_gb = float(fs_results[0]["value"][1]) / (1024**3)
                    lines.append(f"\n• **Veeam Drive (F:)**: {free_gb:.1f} GB free")
            except Exception:
                pass  # windows_exporter may not expose this label

            header = "**📦 Backup Status Report**\n\n"
            if not lines:
                return header + "No backup log data found in Loki. Check that Promtail is ingesting from `/geekom/backup-logs`."

            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"Backup status check failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Backup status check complete", "done": True}}
                )

    async def check_backup_drive_headroom(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Check available disk space on all drives using Prometheus metrics from
        Windows Exporter. Reports current usage, free space, and estimated days
        until 90% full based on recent growth rate.
        :return: Disk space report for C:, D:, and F: drives.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Checking drive headroom via Prometheus", "done": False}}
            )
        try:
            # Query Windows Exporter disk metrics
            free_results = self._prom_instant("windows_logical_disk_free_bytes")
            size_results = self._prom_instant("windows_logical_disk_size_bytes")

            if not free_results or not size_results:
                return "No disk metrics found. Is windows_exporter running and scraping logical_disk?"

            # Build lookup maps by volume label
            free_map = {}
            for r in free_results:
                vol = r["metric"].get("volume", "unknown")
                free_map[vol] = float(r["value"][1])

            size_map = {}
            for r in size_results:
                vol = r["metric"].get("volume", "unknown")
                size_map[vol] = float(r["value"][1])

            # Focus on the drives we care about
            target_drives = ["C:", "D:", "F:"]
            lines = [
                "| Drive | Total | Free | Used % | Status |",
                "|-------|-------|------|--------|--------|",
            ]

            for vol in target_drives:
                if vol not in size_map or vol not in free_map:
                    lines.append(f"| {vol} | — | — | — | not found |")
                    continue

                total_gb = size_map[vol] / (1024**3)
                free_gb = free_map[vol] / (1024**3)
                used_pct = ((size_map[vol] - free_map[vol]) / size_map[vol]) * 100

                # Status thresholds
                if used_pct >= 90:
                    status = "🔴 Critical"
                elif used_pct >= 80:
                    status = "⚠️ Warning"
                else:
                    status = "✅ OK"

                lines.append(
                    f"| {vol} | {total_gb:.0f} GB | {free_gb:.1f} GB | {used_pct:.1f}% | {status} |"
                )

            # Try to estimate days to 90% for F: drive (Veeam target)
            try:
                now = time.time()
                week_ago = now - (7 * 86400)
                range_data = self._prom_get(
                    "/api/v1/query_range",
                    {
                        "query": 'windows_logical_disk_free_bytes{volume="F:"}',
                        "start": week_ago,
                        "end": now,
                        "step": "6h",
                    },
                )
                if range_data.get("status") == "success":
                    range_results = range_data["data"]["result"]
                    if range_results and len(range_results[0]["values"]) >= 2:
                        vals = range_results[0]["values"]
                        first_free = float(vals[0][1])
                        last_free = float(vals[-1][1])
                        time_span_days = (float(vals[-1][0]) - float(vals[0][0])) / 86400

                        if time_span_days > 0 and first_free > last_free:
                            daily_consumption = (first_free - last_free) / time_span_days
                            total = size_map.get("F:", 0)
                            threshold_90 = total * 0.10  # free space at 90% used
                            remaining_bytes = last_free - threshold_90
                            if daily_consumption > 0 and remaining_bytes > 0:
                                days_to_90 = remaining_bytes / daily_consumption
                                lines.append(
                                    f"\n**F: Drive Forecast**: ~{days_to_90:.0f} days until 90% full "
                                    f"(consuming {daily_consumption / (1024**3):.1f} GB/day)"
                                )
                        elif first_free <= last_free:
                            lines.append("\n**F: Drive Forecast**: stable or freeing space ✅")
            except Exception:
                pass  # forecast is best-effort

            header = "**💾 Drive Space Report**\n\n"
            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"Drive headroom check failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Drive headroom check complete", "done": True}}
                )

    async def get_scheduled_tasks_timeline(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Query Loki for recent scheduled task execution logs (pre-backup, mirror,
        weekly-analysis, verify-backup) and present them in chronological order.
        Helps diagnose timing collisions between nightly jobs.
        :return: Chronologically sorted summary of recent scheduled task executions.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Querying scheduled task logs", "done": False}}
            )
        try:
            # Search for task execution markers in backup logs
            task_queries = {
                "Pre-Backup": '{job=~".*backup.*"} |~ "START|DONE|FAIL|pre-backup"',
                "Mirror": '{job=~".*backup.*"} |~ "mirror|ROBOCOPY"',
                "Verify-Backup": '{job=~".*backup.*"} |~ "VERIFICATION|VERIFY"',
                "Weekly-Analysis": '{job=~".*backup.*"} |~ "weekly|analysis|dump"',
            }

            all_events = []
            for task_name, logql in task_queries.items():
                try:
                    streams = self._loki_query_range(logql, hours_back=72, limit=10)
                    for stream in streams:
                        for ts_ns, msg in stream.get("values", []):
                            ts = int(ts_ns) / 1e9
                            clean_msg = msg[:150] + "…" if len(msg) > 150 else msg
                            all_events.append((ts, task_name, clean_msg))
                except Exception:
                    all_events.append((time.time(), task_name, "⚠️ query failed"))

            if not all_events:
                return "No scheduled task logs found in Loki in the last 72 hours."

            # Sort chronologically (newest first)
            all_events.sort(key=lambda e: e[0], reverse=True)

            # Deduplicate very close events (within 5 seconds)
            deduped = []
            last_ts = 0
            for ts, name, msg in all_events:
                if abs(ts - last_ts) > 5 or not deduped:
                    deduped.append((ts, name, msg))
                    last_ts = ts

            lines = []
            for ts, name, msg in deduped[:30]:  # cap at 30 events
                ts_str = _ts_to_str(ts)
                lines.append(f"• [{ts_str}] **{name}**: {msg}")

            header = f"**🗓️ Scheduled Tasks Timeline** (last 72h) — {len(lines)} events:\n\n"
            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"Scheduled tasks query failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Scheduled tasks query complete", "done": True}}
                )

    async def get_ha_power_and_thermals(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Query Home Assistant for smart plug wattage, ambient room temperature,
        and UPS battery status. Requires a Home Assistant Long-Lived Access Token
        configured in the tool's Valves settings.
        :return: Current power consumption and ambient temperature readings, or an
                 error if Home Assistant is not configured.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Querying Home Assistant sensors", "done": False}}
            )
        try:
            if not self.valves.ha_token:
                return (
                    "Home Assistant integration is not configured.\n"
                    "To enable: go to OpenWebUI → Workspace → Tools → Homelab Ops Inspector → Valves, "
                    "and set `ha_token` to a Home Assistant Long-Lived Access Token "
                    "(generated at http://homeassistant:8123/profile → Long-Lived Access Tokens)."
                )

            # Common entity IDs for homelab power monitoring
            # These are best-guess patterns — adjust in future versions
            sensor_patterns = [
                ("sensor.homelab_power", "Homelab Power Draw"),
                ("sensor.geekom_ups_battery", "UPS Battery"),
                ("sensor.geekom_power", "Geekom Power"),
                ("sensor.room_temperature", "Room Temperature"),
                ("sensor.ambient_temperature", "Ambient Temperature"),
            ]

            lines = []
            found_any = False

            # First, get all states to discover available sensors
            try:
                all_states = self._ha_get("/states")
                # Filter for power, temperature, and battery sensors
                relevant = [
                    s for s in all_states
                    if any(kw in s.get("entity_id", "").lower()
                           for kw in ["power", "watt", "temperature", "temp", "battery", "ups", "energy"])
                    and s.get("state") not in ("unavailable", "unknown", "")
                ]

                if relevant:
                    found_any = True
                    lines.append("**Discovered sensors:**\n")
                    for s in relevant[:15]:  # Cap at 15 sensors
                        entity_id = s["entity_id"]
                        state = s["state"]
                        unit = s.get("attributes", {}).get("unit_of_measurement", "")
                        friendly = s.get("attributes", {}).get("friendly_name", entity_id)
                        last_changed = s.get("last_changed", "unknown")
                        lines.append(f"• **{friendly}**: {state} {unit}  (last changed: {last_changed})")

            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 401:
                    return "Home Assistant returned 401 Unauthorized. The Long-Lived Access Token may be expired or invalid."
                raise

            if not found_any:
                return "Connected to Home Assistant but no power/temperature/battery sensors found."

            header = "**🏠 Home Assistant Sensor Report**\n\n"
            return _truncate(header + "\n".join(lines))

        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Home Assistant query failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Home Assistant query complete", "done": True}}
                )
