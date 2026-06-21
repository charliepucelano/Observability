#!/bin/bash
# analyze.sh — DevOps Analyzer for Perplexity Space
# Submits weekly diagnostic dump, handles interactive log-fetching loop,
# saves final analysis. Modeled after general_researcher/research_and_save.sh.

set -euo pipefail

PROFILE="host-chrome"
SPACE_URL="https://www.perplexity.ai/spaces/devops-8flIgxFsQMutVXkb3dOtjQ"
DUMP_FILE="/home/node/.openclaw/workspace/dumps/latest.md"
OUTPUT_FILE="/home/node/.openclaw/workspace/dumps/latest-analysis.txt"
TMP_RAW="/tmp/devops_raw.txt"
LOKI_URL="http://host.docker.internal:3100"
MAX_ROUNDS=3
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Lock ────────────────────────────────────────────────────────────────────
LOCK_FILE="/tmp/devops_analyze.lock"
if [ -f "$LOCK_FILE" ]; then echo "ALREADY_RUNNING"; exit 0; fi
touch "$LOCK_FILE"; trap 'rm -f "$LOCK_FILE"' EXIT

# ── Validate dump exists ───────────────────────────────────────────────────
if [ ! -f "$DUMP_FILE" ]; then
  echo "[ERROR] Dump file not found: $DUMP_FILE"
  exit 1
fi

DUMP_SIZE=$(wc -c < "$DUMP_FILE")
echo "[analyze] Dump file: $DUMP_FILE ($DUMP_SIZE bytes)"

if [ "$DUMP_SIZE" -lt 1000 ]; then
  echo "[ERROR] Dump file too small ($DUMP_SIZE bytes), likely corrupt"
  exit 1
fi

# Read the dump content, escaping for JS injection
DUMP_CONTENT=$(cat "$DUMP_FILE" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | tr '\n' '\\' | sed 's/\\/\\n/g')

# ── Step 1: Navigate to Perplexity Space ───────────────────────────────────
echo "[Step 1] Navigating to DevOps Space..."
openclaw browser --profile $PROFILE navigate "$SPACE_URL"
sleep 3

# ── Step 2: Submit dump via reactive JS injection ──────────────────────────
echo "[Step 2] Submitting dump via reactive JS injection..."

# Prepare the content for JS - use a file-based approach for large content
cat "$DUMP_FILE" | node -e "
const fs = require('fs');
let text = '';
process.stdin.resume();
process.stdin.setEncoding('utf8');
process.stdin.on('data', d => text += d);
process.stdin.on('end', () => {
  // Escape for JS string embedding
  const escaped = text
    .replace(/\\\\/g, '\\\\\\\\')
    .replace(/\"/g, '\\\\\"')
    .replace(/\\n/g, '\\\\n')
    .replace(/\\r/g, '')
    .replace(/\\t/g, '\\\\t');
  fs.writeFileSync('/tmp/devops_dump_escaped.txt', escaped);
});
"

ESCAPED_CONTENT=$(cat /tmp/devops_dump_escaped.txt)

JS_SUBMIT="() => {
  return new Promise(async (resolve) => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const fullText = \"$ESCAPED_CONTENT\";
    const CHUNK_SIZE = 12000;
    const totalChunks = Math.ceil(fullText.length / CHUNK_SIZE);
    
    for (let i = 0; i < totalChunks; i++) {
      const isLast = (i === totalChunks - 1);
      const chunkText = fullText.substring(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
      const promptSuffix = isLast 
        ? '\\n\\n[End of Dump ' + (i+1) + '/' + totalChunks + '] Please provide the final DevOps analysis.' 
        : '\\n\\n[Part ' + (i+1) + '/' + totalChunks + '] Do not analyze yet. Just reply \"Acknowledged\" and wait for the rest.';
      
      const payload = chunkText + promptSuffix;
      let attempts = 0;
      let submitted = false;
      
      while (!submitted && attempts < 50) {
        attempts++;
        const box = document.querySelector('div[contenteditable=\"true\"]') || document.querySelector('textarea');
        
        if (!box) {
          const placeholders = Array.from(document.querySelectorAll('*')).filter(el => 
            el.textContent && (el.textContent.includes('Ask a follow-up') || el.textContent.includes('ask anything'))
          );
          if (placeholders.length > 0) placeholders[placeholders.length - 1].click();
          await sleep(200);
          continue;
        }
        
        if (box && !box.hasAttribute('data-typed')) {
          box.focus();
          const dt = new DataTransfer();
          dt.setData('text/plain', payload);
          box.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true }));
          if (!box.textContent.trim()) document.execCommand('insertText', false, payload);
          box.dispatchEvent(new Event('input', { bubbles: true }));
          box.setAttribute('data-typed', 'true');
        }
        
        if (box && box.hasAttribute('data-typed')) {
          let parent = box.parentElement;
          let submitBtn = null;
          for (let j = 0; j < 5; j++) {
            if (!parent) break;
            submitBtn = Array.from(parent.querySelectorAll('button')).find(b => {
              const aria = (b.getAttribute('aria-label') || '').toLowerCase();
              return !b.disabled && (aria.includes('submit') || aria.includes('send'));
            });
            if (submitBtn) break;
            parent = parent.parentElement;
          }
          
          if (submitBtn) {
            submitBtn.click();
            submitted = true;
          } else if (attempts > 15) {
            box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            submitted = true;
          }
        }
        await sleep(200);
      }
      
      if (!isLast) {
        // Wait for acknowledgment before next chunk
        await sleep(5000); 
        // Wait until generation stops (the Stop button disappears)
        let generating = true;
        let genWait = 0;
        while(generating && genWait < 30) {
          genWait++;
          generating = Array.from(document.querySelectorAll('button')).some(b => 
            (b.getAttribute('aria-label') || '').toLowerCase().includes('stop') ||
            (b.textContent || '').toLowerCase().includes('stop')
          );
          await sleep(1000);
        }
        await sleep(1000);
      }
    }
    resolve('SUCCESS: Submitted all ' + totalChunks + ' chunks');
  });
}"

openclaw browser --profile $PROFILE evaluate --fn "$JS_SUBMIT" || true
echo "[Step 2] Dump submitted in chunks. Waiting for final generation..."
sleep 5

# ── Step 3: Watchdog — wait for response ───────────────────────────────────
echo "[Step 3] Running Watchdog (waiting for text stability)..."
WATCHDOG_JS="() => new Promise(r => { let last='', stable=0; const i = setInterval(() => { const t = Array.from(document.querySelectorAll('.prose, .break-words, div[dir=\"auto\"]')).pop()?.innerText || ''; if (t && t === last && t.length > 50) { if (++stable > 8) { clearInterval(i); r(t); } } else { last = t; stable = 0; } }, 500); setTimeout(() => { clearInterval(i); r(last || 'TIMEOUT'); }, 180000); })"

openclaw browser --profile $PROFILE evaluate --fn "$WATCHDOG_JS" > "$TMP_RAW" 2>/dev/null || true

RESULT_SIZE=$(wc -c < "$TMP_RAW")
echo "[Step 3] Watchdog captured $RESULT_SIZE bytes"

if [ "$RESULT_SIZE" -lt 50 ]; then
  echo "[ERROR] Watchdog returned empty or too-short result"
  exit 1
fi

# ── Step 4: Interactive Log-Fetching Loop ──────────────────────────────────
ROUND=0
while [ $ROUND -lt $MAX_ROUNDS ]; do
  ROUND=$((ROUND + 1))
  echo "[Step 4] Checking for ACTION tags (round $ROUND/$MAX_ROUNDS)..."

  # Check for <ACTION: TAIL_LOG: container_name>
  CONTAINER=$(grep -oP '<ACTION:\s*TAIL_LOG:\s*\K[^>]+' "$TMP_RAW" | head -1 | tr -d ' ')

  if [ -z "$CONTAINER" ]; then
    echo "[Step 4] No ACTION tags found. Analysis complete."
    break
  fi

  echo "[Step 4] Perplexity requested logs for: $CONTAINER"

  # Fetch logs from Loki via curl
  LOKI_QUERY="{job=\"docker\",container=\"$CONTAINER\"}"
  ENCODED_QUERY=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$LOKI_QUERY'))" 2>/dev/null || echo "$LOKI_QUERY")
  END_NS=$(date +%s)000000000
  START_NS=$(( $(date +%s) - 86400 ))000000000

  LOGS=$(curl -s "${LOKI_URL}/loki/api/v1/query_range?query=${ENCODED_QUERY}&start=${START_NS}&end=${END_NS}&limit=50&direction=backward" 2>/dev/null | \
    node -e "
      const fs = require('fs');
      let d = '';
      process.stdin.on('data', c => d += c);
      process.stdin.on('end', () => {
        try {
          const j = JSON.parse(d);
          const lines = [];
          for (const s of (j.data?.result || [])) {
            for (const v of (s.values || [])) {
              lines.push(v[1]);
            }
          }
          process.stdout.write(lines.slice(0, 50).join('\n'));
        } catch(e) { process.stdout.write('Log fetch failed: ' + e.message); }
      });
    ")

  if [ -z "$LOGS" ]; then
    LOGS="No logs found for container: $CONTAINER"
  fi

  echo "[Step 4] Fetched $(echo "$LOGS" | wc -l) log lines for $CONTAINER"

  # Prepare follow-up message
  FOLLOWUP="Here are the last 50 log lines for $CONTAINER:\n\n$LOGS"
  FOLLOWUP_ESCAPED=$(echo "$FOLLOWUP" | node -e "
    let t = '';
    process.stdin.on('data', d => t += d);
    process.stdin.on('end', () => {
      process.stdout.write(t.replace(/\\\\/g, '\\\\\\\\').replace(/\"/g, '\\\\\"').replace(/\\n/g, '\\\\n').replace(/\\r/g, ''));
    });
  ")

  # Submit follow-up
  JS_FOLLOWUP="() => {
    return new Promise((resolve) => {
      let attempts = 0;
      const TEXT = \"$FOLLOWUP_ESCAPED\";
      const interval = setInterval(() => {
        attempts++;
        const box = document.querySelector('div[contenteditable=\"true\"]') || document.querySelector('textarea');
        if (box && !box.hasAttribute('data-followup')) {
          box.focus();
          const dt = new DataTransfer();
          dt.setData('text/plain', TEXT);
          box.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true }));
          if (!box.textContent.trim()) document.execCommand('insertText', false, TEXT);
          box.dispatchEvent(new Event('input', { bubbles: true }));
          box.setAttribute('data-followup', 'true');
        }
        if (box && box.hasAttribute('data-followup')) {
          let parent = box.parentElement;
          let submitBtn = null;
          for (let i = 0; i < 5; i++) {
            if (!parent) break;
            submitBtn = Array.from(parent.querySelectorAll('button')).find(b => {
              const aria = (b.getAttribute('aria-label') || '').toLowerCase();
              return !b.disabled && (aria.includes('submit') || aria.includes('send'));
            });
            if (submitBtn) break;
            parent = parent.parentElement;
          }
          if (submitBtn) { clearInterval(interval); submitBtn.click(); resolve('SUCCESS'); }
          else if (attempts > 15) {
            box.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true }));
            clearInterval(interval); resolve('SUCCESS');
          }
        }
        if (attempts > 50) { clearInterval(interval); resolve('TIMEOUT'); }
      }, 200);
    });
  }"

  openclaw browser --profile $PROFILE evaluate --fn "$JS_FOLLOWUP" || true
  sleep 5

  # Watchdog again
  openclaw browser --profile $PROFILE evaluate --fn "$WATCHDOG_JS" > "$TMP_RAW" 2>/dev/null || true
  echo "[Step 4] Round $ROUND watchdog captured $(wc -c < "$TMP_RAW") bytes"
done

# ── Step 5: Clean and save final result ────────────────────────────────────
echo "[Step 5] Cleaning and saving final analysis..."

node << 'NODESCRIPT'
const fs = require('fs');
let text = fs.readFileSync('/tmp/devops_raw.txt', 'utf-8');

// Remove ANSI escape codes and OpenClaw CLI spinner garbage
text = text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
text = text.replace(/\[1G\[J/g, '');
text = text.replace(/\[\?25[lh]/g, '');
text = text.replace(/[◒◐◓◑│◇]/g, '');
text = text.replace(/Gateway browser\.request/g, '');
text = text.trim();

// Strip wrapping quotes from evaluate output
if (text.startsWith('"') && text.endsWith('"')) {
  text = text.slice(1, -1);
}

// Unescape JSON-encoded newlines and tabs
text = text.replace(/\\n/g, '\n').replace(/\\t/g, ' ');

// Strip inline bracket citations [1][2][3]
text = text.replace(/\[\d+\]/g, '');

// Collapse 3+ consecutive newlines into 2
text = text.replace(/\n{3,}/g, '\n\n');

text = text.trim();

const outputFile = '/home/node/.openclaw/workspace/dumps/latest-analysis.txt';
fs.writeFileSync(outputFile, text, 'utf-8');
console.log('Saved analysis: ' + text.length + ' chars to ' + outputFile);
NODESCRIPT

echo "=== ANALYZE COMPLETE ==="
