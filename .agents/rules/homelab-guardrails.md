---
trigger: always_on
---

# Observability Repository Guardrails

## Configuration & Safety Rules
1. Every container in `docker-compose.yml` must specify explicit `mem_limit` and `cpus` resource constraints.
2. Enable Docker `json-file` log rotation (`max-size: 10m`, `max-file: 3`) across all services.
3. Keep persistent state in mapped volumes (`D:/observability/...`) and never store runtime positions in ephemeral `/tmp`.
4. Run `docker compose config` before reloading stacks.
