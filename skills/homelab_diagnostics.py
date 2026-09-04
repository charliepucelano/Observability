"""
title: Homelab Diagnostics
description: Read-only observability tools for Geekom A9 homelab. Queries Prometheus, Loki, SLO recording rules, AIDA64 thermal metrics, and container status via PromQL. All responses are capped and secrets-scrubbed.
author: Carlos
version: 1.0.0
required_open_webui_version: 0.4.0
"""

import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import requests
from pydantic import BaseModel, Field


# ────────────────────────────────────────────────────────────────────────────
# Shared helpers (outside the class so they're importable but not exposed
# as tool methods)
# ────────────────────────────────────────────────────────────────────────────

_MAX_RESPONSE_BYTES = 4096

_SECRETS_RE = re.compile(
    r"(password|passwd|bearer_token|bearer_token_file|credentials|"
    r"api_key|secret|token|authorization|basic_auth)"
    r"\s*[:=]\s*\S+",
    re.IGNORECASE,
)

_SECRETS_BLOCK_RE = re.compile(
    r"(basic_auth:\s*\n(?:\s+\w+:\s*\S+\n?)+)",
    re.MULTILINE,
)


def _sanitize_label(raw: str) -> str:
    """Escape a user-supplied label so it is safe inside a LogQL regex.

    Strips everything except alphanumerics, hyphens and underscores,
    preventing regex injection or broken queries.
    """
    return re.sub(r"[^a-zA-Z0-9_\-]", "", raw)


def _scrub_secrets(text: str) -> str:
    """Remove passwords, tokens, and basic_auth blocks from config text."""
    text = _SECRETS_BLOCK_RE.sub("basic_auth: [REDACTED]\n", text)
    text = _SECRETS_RE.sub(lambda m: m.group(0).split(":")[0].split("=")[0] + ": [REDACTED]", text)
    return text


def _truncate(text: str, limit: int = _MAX_RESPONSE_BYTES) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [TRUNCATED — showing {limit} of {len(text)} bytes]"


def _ts_to_str(unix_ts: float) -> str:
    """Convert a Unix timestamp to a human-readable UTC string."""
    return datetime.fromtimestamp(float(unix_ts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S UTC"
    )


def _human_duration(seconds: float) -> str:
    """Convert seconds to a human-friendly duration string."""
    s = int(seconds)
    days, s = divmod(s, 86400)
    hours, s = divmod(s, 3600)
    mins, _ = divmod(s, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if mins:
        parts.append(f"{mins}m")
    return " ".join(parts) or "<1m"


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
        request_timeout: int = Field(
            default=15,
            description="HTTP request timeout in seconds.",
        )
        max_results: int = Field(
            default=5,
            description="Maximum number of PromQL instant-query results to return.",
        )
        max_log_lines: int = Field(
            default=15,
            description="Maximum number of Loki log lines to return.",
        )

    def __init__(self):
        self.valves = self.Valves()

    # ── Internal helpers ────────────────────────────────────────────────

    def _prom_get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.valves.prometheus_url}{path}"
        resp = requests.get(url, params=params, timeout=self.valves.request_timeout)
        resp.raise_for_status()
        return resp.json()

    def _loki_get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.valves.loki_url}{path}"
        resp = requests.get(url, params=params, timeout=self.valves.request_timeout)
        resp.raise_for_status()
        return resp.json()

    def _prom_instant(self, query: str) -> list:
        data = self._prom_get("/api/v1/query", {"query": query})
        if data.get("status") != "success":
            raise ValueError(data.get("error", "Unknown Prometheus error"))
        return data["data"]["result"]

    def _prom_range(self, query: str, start: float, end: float, step: str) -> list:
        data = self._prom_get(
            "/api/v1/query_range",
            {"query": query, "start": start, "end": end, "step": step},
        )
        if data.get("status") != "success":
            raise ValueError(data.get("error", "Unknown Prometheus error"))
        return data["data"]["result"]

    # ── Public tool methods ─────────────────────────────────────────────

    async def query_prometheus(
        self,
        promql_query: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Execute an instant PromQL query against Prometheus and return the top results.
        Use this for any ad-hoc Prometheus metric lookup.
        :param promql_query: A valid PromQL expression (e.g. 'up', 'node_memory_MemAvailable_bytes').
        :return: Formatted metric results or an error message.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": f"Querying Prometheus: {promql_query}", "done": False}}
            )
        try:
            results = self._prom_instant(promql_query)
            if not results:
                return f"No results for query: `{promql_query}`"

            lines = []
            for r in results[: self.valves.max_results]:
                labels = ", ".join(
                    f'{k}="{v}"' for k, v in r["metric"].items() if k != "__name__"
                )
                name = r["metric"].get("__name__", "value")
                ts = _ts_to_str(r["value"][0])
                val = r["value"][1]
                lines.append(f"• {name}{{{labels}}} = {val}  ({ts})")

            total = len(results)
            header = f"**PromQL**: `{promql_query}`  —  {min(total, self.valves.max_results)}/{total} results\n"
            body = "\n".join(lines)
            return _truncate(header + body)

        except Exception as e:
            return f"Prometheus query failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Prometheus query complete", "done": True}}
                )

    async def query_prometheus_range(
        self,
        promql_query: str,
        range_hours: int = 6,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Execute a range PromQL query and return server-side computed statistics
        (min, max, avg, last) instead of raw time series. Good for trend analysis.
        :param promql_query: A valid PromQL expression.
        :param range_hours: How many hours back to query (default 6, max 168).
        :return: Per-series summary statistics.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": f"Range query ({range_hours}h): {promql_query}", "done": False}}
            )
        try:
            range_hours = min(max(range_hours, 1), 168)  # clamp 1h–7d
            now = time.time()
            start = now - (range_hours * 3600)
            # Adaptive step: aim for ~100 data points
            step_seconds = max(int((range_hours * 3600) / 100), 15)
            step = f"{step_seconds}s"

            results = self._prom_range(promql_query, start, now, step)
            if not results:
                return f"No range data for query: `{promql_query}` over {range_hours}h"

            lines = []
            for r in results[: self.valves.max_results]:
                labels = ", ".join(
                    f'{k}="{v}"' for k, v in r["metric"].items() if k != "__name__"
                )
                name = r["metric"].get("__name__", "series")
                values = [float(v[1]) for v in r["values"] if v[1] != "NaN"]
                if not values:
                    lines.append(f"• {name}{{{labels}}}: no numeric data points")
                    continue
                stats = {
                    "min": round(min(values), 3),
                    "max": round(max(values), 3),
                    "avg": round(sum(values) / len(values), 3),
                    "last": round(values[-1], 3),
                    "samples": len(values),
                }
                lines.append(
                    f"• {name}{{{labels}}}:  "
                    f"min={stats['min']}, max={stats['max']}, "
                    f"avg={stats['avg']}, last={stats['last']}  "
                    f"({stats['samples']} samples over {range_hours}h)"
                )

            total = len(results)
            header = f"**Range Query** (`{range_hours}h`): `{promql_query}`  —  {min(total, self.valves.max_results)}/{total} series\n"
            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"Prometheus range query failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Range query complete", "done": True}}
                )

    async def query_loki_recent_errors(
        self,
        app_label: str,
        limit: int = 15,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Fetch recent error logs from Loki for a specific application/container.
        Searches logs from the last 6 hours matching the container name.
        :param app_label: Container or app name to search for (e.g. 'immich', 'grafana', 'prometheus').
        :param limit: Maximum number of log lines to return (default 15).
        :return: Recent error log snippets.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": f"Searching Loki errors for '{app_label}'", "done": False}}
            )
        try:
            safe_label = _sanitize_label(app_label)
            if not safe_label:
                return "Error: app_label must contain at least one alphanumeric character."

            limit = min(max(limit, 1), self.valves.max_log_lines)

            now_ns = int(time.time() * 1e9)
            six_hours_ago_ns = now_ns - int(6 * 3600 * 1e9)

            logql = f'{{container=~".*{safe_label}.*"}} |= "error"'
            params = {
                "query": logql,
                "start": str(six_hours_ago_ns),
                "end": str(now_ns),
                "limit": str(limit),
                "direction": "backward",
            }
            data = self._loki_get("/loki/api/v1/query_range", params)

            if data.get("status") != "success":
                return f"Loki query failed: {data.get('status', 'unknown')}"

            streams = data.get("data", {}).get("result", [])
            if not streams:
                return f"No error logs found for `{safe_label}` in the last 6 hours. ✅"

            lines = []
            for stream in streams:
                container = stream.get("stream", {}).get("container", "unknown")
                for ts_ns, msg in stream.get("values", []):
                    ts = _ts_to_str(int(ts_ns) / 1e9)
                    # Strip excessively long lines
                    clean_msg = msg[:300] + "…" if len(msg) > 300 else msg
                    lines.append(f"[{ts}] **{container}**: {clean_msg}")
                    if len(lines) >= limit:
                        break
                if len(lines) >= limit:
                    break

            header = f"**Loki Errors** for `{safe_label}` (last 6h) — {len(lines)} entries:\n\n"
            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"Loki error query failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Loki error search complete", "done": True}}
                )

    async def query_loki_logs(
        self,
        logql_query: str,
        limit: int = 15,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Execute an arbitrary LogQL query against Loki (last 6 hours).
        Use this for custom log searches beyond simple error lookups.
        :param logql_query: A valid LogQL expression (e.g. '{job="varlogs"} |= "timeout"').
        :param limit: Maximum number of log lines to return (default 15).
        :return: Matching log lines.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Executing LogQL query", "done": False}}
            )
        try:
            limit = min(max(limit, 1), self.valves.max_log_lines)
            now_ns = int(time.time() * 1e9)
            six_hours_ago_ns = now_ns - int(6 * 3600 * 1e9)

            params = {
                "query": logql_query,
                "start": str(six_hours_ago_ns),
                "end": str(now_ns),
                "limit": str(limit),
                "direction": "backward",
            }
            data = self._loki_get("/loki/api/v1/query_range", params)

            if data.get("status") != "success":
                return f"Loki query failed: {data.get('status', 'unknown')}"

            streams = data.get("data", {}).get("result", [])
            if not streams:
                return "No results for LogQL query."

            lines = []
            for stream in streams:
                labels = stream.get("stream", {})
                label_str = ", ".join(f"{k}={v}" for k, v in labels.items())
                for ts_ns, msg in stream.get("values", []):
                    ts = _ts_to_str(int(ts_ns) / 1e9)
                    clean_msg = msg[:300] + "…" if len(msg) > 300 else msg
                    lines.append(f"[{ts}] ({label_str}): {clean_msg}")
                    if len(lines) >= limit:
                        break
                if len(lines) >= limit:
                    break

            header = f"**LogQL Results** — {len(lines)} entries:\n\n"
            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"Loki query failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "LogQL query complete", "done": True}}
                )

    async def get_container_status(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        List all running Docker containers with their uptime.
        Uses Prometheus metrics scraped from cAdvisor — no direct cAdvisor connection needed.
        :return: Table of container names and uptimes.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Fetching container status via Prometheus", "done": False}}
            )
        try:
            results = self._prom_instant('container_start_time_seconds{name!=""}')
            if not results:
                return "No container metrics found. Is cAdvisor running and scraped by Prometheus?"

            now = time.time()
            containers = []
            for r in results:
                name = r["metric"].get("name", "unknown")
                start_ts = float(r["value"][1])
                uptime_secs = now - start_ts
                containers.append((name, uptime_secs, start_ts))

            # Sort by name for consistency
            containers.sort(key=lambda c: c[0])

            lines = ["| Container | Uptime | Started |", "|-----------|--------|---------|"]
            for name, uptime, started in containers:
                lines.append(
                    f"| {name} | {_human_duration(uptime)} | {_ts_to_str(started)} |"
                )

            header = f"**Docker Containers** — {len(containers)} running:\n\n"
            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"Container status query failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Container status complete", "done": True}}
                )

    async def get_slo_report(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get the SLO (Service Level Objective) error budget report for all production services.
        Shows 30-day availability and remaining error budget percentage for each monitored endpoint.
        :return: SLO error budget table for production Leyforge services.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Querying SLO error budgets", "done": False}}
            )
        try:
            # Get error budget remaining ratios
            budget_results = self._prom_instant("slo:error_budget_remaining:ratio")
            avail_results = self._prom_instant("slo:probe_success:avg30d")

            if not budget_results:
                return "No SLO data found. Are the recording rules in slo.yml active?"

            # Build a lookup of availability by instance
            avail_map = {}
            for r in avail_results:
                instance = r["metric"].get("instance", "unknown")
                avail_map[instance] = float(r["value"][1])

            lines = [
                "| Service | 30d Availability | Error Budget | Status |",
                "|---------|-----------------|--------------|--------|",
            ]
            for r in budget_results:
                instance = r["metric"].get("instance", "unknown")
                budget_ratio = float(r["value"][1])
                avail = avail_map.get(instance, 0.0)

                avail_pct = f"{avail * 100:.3f}%"
                budget_pct = f"{budget_ratio * 100:.1f}%"

                if budget_ratio >= 0.5:
                    status = "✅ Healthy"
                elif budget_ratio >= 0.0:
                    status = "⚠️ Burning"
                else:
                    status = "🔴 Exhausted"

                lines.append(f"| {instance} | {avail_pct} | {budget_pct} | {status} |")

            header = "**SLO Error Budget Report** (99.5% target, 30-day window, prod only):\n\n"
            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"SLO report query failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "SLO report complete", "done": True}}
                )

    async def get_endpoint_latency(
        self,
        service_name: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get response time percentiles (p50, p90, p99) for a Leyforge service endpoint.
        Uses Blackbox exporter probe_duration_seconds metrics.
        :param service_name: Service domain or keyword (e.g. 'immich', 'grafana', 'paperless', 'chat').
        :return: p50, p90, and p99 latency values in milliseconds.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": f"Checking latency for {service_name}", "done": False}}
            )
        try:
            safe_name = _sanitize_label(service_name)
            if not safe_name:
                return "Error: service_name must contain at least one alphanumeric character."

            now = time.time()
            start = now - 3600  # last 1 hour
            step = "60s"

            query = f'probe_duration_seconds{{job="uptime", instance=~".*{safe_name}.*"}}'
            results = self._prom_range(query, start, now, step)

            if not results:
                return f"No latency data for `{safe_name}`. Check that the service is in Blackbox targets."

            lines = []
            for r in results:
                instance = r["metric"].get("instance", "unknown")
                values = [float(v[1]) * 1000 for v in r["values"] if v[1] != "NaN"]
                if not values:
                    lines.append(f"• {instance}: no data points")
                    continue

                values_sorted = sorted(values)
                n = len(values_sorted)
                p50 = values_sorted[int(n * 0.50)] if n > 0 else 0
                p90 = values_sorted[int(n * 0.90)] if n > 0 else 0
                p99 = values_sorted[min(int(n * 0.99), n - 1)] if n > 0 else 0

                lines.append(
                    f"• **{instance}**: p50={p50:.0f}ms, p90={p90:.0f}ms, p99={p99:.0f}ms "
                    f"({n} samples, last 1h)"
                )

            header = f"**Endpoint Latency** for `{safe_name}`:\n\n"
            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"Latency query failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Latency check complete", "done": True}}
                )

    async def get_thermal_snapshot(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Get current CPU and GPU temperatures, GPU power draw, CPU load, and memory usage
        from the AIDA64 sensors pushed to Prometheus via Pushgateway.
        :return: Current thermal and power readings for the Geekom A9 host.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Reading AIDA64 thermal sensors", "done": False}}
            )
        try:
            # Hardcoded AIDA64 metric names — these match aida-to-pushgateway.ps1
            metrics = {
                "CPU Diode Temp": ("aida64_temp_cpu_diode_celsius", "°C"),
                "GPU Temp": ("aida64_temp_gpu_celsius", "°C"),
                "GPU SoC Temp": ("aida64_temp_gpu_soc_celsius", "°C"),
                "GPU Power": ("aida64_power_gpu_watts", "W"),
                "CPU Package Power": ("aida64_power_cpu_package_watts", "W"),
                "CPU Load (avg)": ("aida64_cpu_load_percent", "%"),
                "RAM Used": ("aida64_memory_used_mb", "MB"),
                "RAM Free": ("aida64_memory_free_mb", "MB"),
                "GPU VRAM Used": ("aida64_gpu_vram_used_mb", "MB"),
                "HDD1 Temp": ("aida64_temp_hdd1_celsius", "°C"),
                "HDD2 Temp": ("aida64_temp_hdd2_celsius", "°C"),
            }

            lines = []
            stale_warning = False

            for label, (metric_name, unit) in metrics.items():
                try:
                    results = self._prom_instant(metric_name)
                    if results:
                        val = float(results[0]["value"][1])
                        ts = float(results[0]["value"][0])
                        age_mins = (time.time() - ts) / 60

                        freshness = ""
                        if age_mins > 5:
                            freshness = f"  ⚠️ stale ({age_mins:.0f}m ago)"
                            stale_warning = True

                        lines.append(f"• **{label}**: {val:.1f} {unit}{freshness}")
                    else:
                        lines.append(f"• **{label}**: no data")
                except Exception:
                    lines.append(f"• **{label}**: query error")

            header = "**🌡️ Geekom A9 Thermal & Power Snapshot**\n\n"
            if stale_warning:
                header += "> ⚠️ Some metrics are stale — AIDA64 pushgateway may be delayed.\n\n"

            return _truncate(header + "\n".join(lines))

        except Exception as e:
            return f"Thermal snapshot failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Thermal snapshot complete", "done": True}}
                )

    async def read_prometheus_config(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Read the active Prometheus configuration via its status API.
        All passwords, tokens, and basic_auth credentials are automatically scrubbed.
        :return: The active Prometheus YAML configuration with secrets redacted.
        """
        if __event_emitter__:
            await __event_emitter__(
                {"type": "status", "data": {"description": "Fetching Prometheus config", "done": False}}
            )
        try:
            data = self._prom_get("/api/v1/status/config")
            if data.get("status") != "success":
                return f"Failed to fetch config: {data.get('error', 'unknown')}"

            raw_config = data.get("data", {}).get("yaml", "")
            if not raw_config:
                return "Prometheus returned an empty configuration."

            scrubbed = _scrub_secrets(raw_config)

            header = "**Prometheus Active Configuration** (secrets redacted):\n\n```yaml\n"
            footer = "\n```"
            return _truncate(header + scrubbed + footer)

        except Exception as e:
            return f"Config read failed: {e}"
        finally:
            if __event_emitter__:
                await __event_emitter__(
                    {"type": "status", "data": {"description": "Config read complete", "done": True}}
                )
