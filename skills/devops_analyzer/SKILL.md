# DevOps Analyzer (Automated Weekly Analysis)

🚨 **CRITICAL: NEVER USE NATIVE BROWSER TOOLS TO TYPE OR CLICK SUBMIT** 🚨
The native `browser` tool fails on Perplexity Spaces due to dynamic re-renders. You **MUST** use the provided script.

### Step 1: Submit Dump (MANDATORY SCRIPT)
You MUST use this script to submit the weekly DevOps diagnostic dump.
```bash
bash /home/node/.openclaw/workspace/skills/devops_analyzer/scripts/analyze.sh
```

This script will:
1. Read the dump from `/home/node/.openclaw/workspace/dumps/latest.md`
2. Submit to the DevOps Perplexity Space
3. Wait for analysis via watchdog
4. Handle interactive log-fetching if Perplexity requests container logs (max 3 rounds)
5. Save the final analysis to `/home/node/.openclaw/workspace/dumps/latest-analysis.txt`

### Step 2: Verify Output
After the script completes, check that the analysis file exists:
```bash
wc -c /home/node/.openclaw/workspace/dumps/latest-analysis.txt
```
The output should be at least 1KB (typically 3-8KB of analysis).

### Notes
- The Perplexity Space system prompt instructs the AI to output `<ACTION: TAIL_LOG: container_name>` when it needs raw logs
- The script handles this automatically by querying Loki at `http://host.docker.internal:3100`
- Maximum 3 interactive rounds to prevent infinite loops
