# agent-cli: terse homelab orientation for agents on A9 Mega. Read-only. No secrets, no .env.
# Usage: agent-cli <paths|aida|docker|health|services|architecture|help> [--json]
$ErrorActionPreference = 'Stop'
$Json = $false; $rest = @()
foreach ($a in $args) { if ($a -eq '--json' -or $a -eq '-json') { $Json = $true } else { $rest += $a } }
$Cmd = if ($rest.Count -gt 0) { "$($rest[0])".ToLower() } else { 'help' }

function Out-Result($obj, [string[]]$text) {
  if ($Json) { $obj | ConvertTo-Json -Depth 5 -Compress } else { $text | ForEach-Object { Write-Output $_ } }
}

$Commands = [ordered]@{
  paths        = 'key absolute paths + service ports'
  aida         = 'newest AIDA64 CSV + last sample (CPU Diode/GPU)'
  docker       = 'docker ps name/status/ports (read-only)'
  health       = 'docker version + container counts; points to full health script'
  services     = 'NSSM/Windows service status (CloudflareTunnel, ContainerWatchdog, GeekomBot, ProcessMonitor, RAGWatcher)'
  architecture = 'system_architecture.md path + top headings'
  help         = 'this list'
}

function Cmd-Help {
  $t = @('agent-cli <command> [--json]') + ($Commands.GetEnumerator() | ForEach-Object { '  {0,-13} {1}' -f $_.Key, $_.Value })
  Out-Result ([pscustomobject]@{ commands = $Commands }) $t
}

function Cmd-Paths {
  $p = [ordered]@{
    observability_root   = 'D:\observability'
    observability_lessons= 'D:\observability\LESSONS_LEARNED.md'
    observability_fixes  = 'D:\observability\recent_fixes.md'
    observability_compose= 'D:\observability\docker-compose.yml'
    scripts_legacy_tasks = 'D:\scripts'
    health_script        = 'D:\scripts\Test-PostUpdateHealth.ps1'
    system_architecture  = 'D:\dev\system_architecture.md'
    global_lessons       = 'D:\dev\global_lessons_learned.md'
    aida_logs            = 'D:\AIDALOGS'
    knowledge_sync       = 'D:\AI_Knowledge_Sync'
  }
  $ports = [ordered]@{
    immich     = '0.0.0.0:2283 (immich_server)'
    open_webui = '127.0.0.1:11000'
    grafana    = '0.0.0.0:3010'
    loki       = '0.0.0.0:3100'
  }
  $notes = @(
    'fotos.leyforge.com = view/share only (Cloudflare Access, 100 MB request cap).',
    'Large Immich uploads/backups: private path to A9:2283 via Tailscale (preferred) or Flint 3 WireGuard.'
  )
  $t = @()
  foreach ($k in $p.Keys) { $t += ('{0,-22} {1}{2}' -f $k, $p[$k], $(if (Test-Path $p[$k]) { '' } else { '  (missing)' })) }
  foreach ($k in $ports.Keys) { $t += ('port:{0,-17} {1}' -f $k, $ports[$k]) }
  $t += ($notes | ForEach-Object { "note: $_" })
  Out-Result ([pscustomobject]@{ paths = $p; ports = $ports; notes = $notes }) $t
}

function Cmd-Aida {
  $f = Get-ChildItem 'D:\AIDALOGS' -Filter '*_log.csv' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if (-not $f) { $f = Get-ChildItem 'D:\AIDALOGS' -Filter '*.csv' -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 }
  if (-not $f) { Out-Result ([pscustomobject]@{ error = 'no AIDA CSV in D:\AIDALOGS' }) @('no AIDA CSV in D:\AIDALOGS'); exit 1 }
  $info = [ordered]@{ path = $f.FullName; mtime = $f.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'); size_mb = [math]::Round($f.Length/1MB,1) }
  $sample = $null
  try {
    $head = Get-Content $f.FullName -TotalCount 20
    $hi = -1; for ($i=0; $i -lt $head.Count; $i++) { if ($head[$i] -like '"Date",*') { $hi = $i; break } }
    if ($hi -ge 0) {
      $cols  = $head[$hi].Trim('"') -split '","'
      $units = ($head[$hi+1] -split ',') | ForEach-Object { $_.Trim('"') }
      $last  = Get-Content $f.FullName -Tail 15 | Where-Object { $_ -match '^"\d\d/\d\d/\d{4}"' } | Select-Object -Last 1
      if ($last) {
        $v = $last.Trim('"') -split '","'
        $s = [ordered]@{ time = "$($v[0]) $($v[8])" }
        $want = @('CPU Diode','CPU Package','GPU','GPU SoC','Used Memory')
        for ($i=0; $i -lt $cols.Count; $i++) {
          if ($want -contains $cols[$i] -and $i -lt $v.Count) {
            $u = if ($i -lt $units.Count) { $units[$i] -replace '[^\x20-\x7E]','' } else { '' }
            $key = if ($u) { "$($cols[$i]) [$u]" } else { $cols[$i] }
            if (-not $s.Contains($key)) { $s[$key] = $v[$i] }
          }
        }
        $sample = $s
      }
    }
  } catch { $sample = $null }
  $info['last_sample'] = $sample
  $t = @("$($info.path)  mtime=$($info.mtime)  $($info.size_mb)MB")
  if ($sample) { $t += ($sample.GetEnumerator() | ForEach-Object { '  {0}: {1}' -f $_.Key, $_.Value }) } else { $t += '  (no parsable sample)' }
  $t += '  note: AIDA "CPU" temp sensor reads ~20C (dead); use CPU Diode.'
  Out-Result ([pscustomobject]$info) $t
}

function Get-DockerOk { [bool](Get-Command docker -ErrorAction SilentlyContinue) }

function Cmd-Docker {
  if (-not (Get-DockerOk)) { Out-Result ([pscustomobject]@{ error = 'docker not found' }) @('docker not found'); exit 1 }
  $raw = & docker ps --format '{{.Names}}|{{.Status}}|{{.Ports}}' 2>$null
  if ($LASTEXITCODE -ne 0) { Out-Result ([pscustomobject]@{ error = 'docker engine unavailable' }) @('docker engine unavailable (Docker Desktop not running?)'); exit 1 }
  $rows = @($raw | Where-Object { $_ } | ForEach-Object { $n,$s,$p = $_ -split '\|',3; [pscustomobject]@{ name=$n; status=$s; ports=$p } } | Sort-Object name)
  $t = @("$($rows.Count) running") + ($rows | ForEach-Object { '{0,-28} {1,-28} {2}' -f $_.name, $_.status, $_.ports })
  Out-Result ([pscustomobject]@{ count = $rows.Count; containers = $rows }) $t
}

function Cmd-Health {
  $script = 'D:\scripts\Test-PostUpdateHealth.ps1'
  $h = [ordered]@{ full_check_script = $(if (Test-Path $script) { $script } else { $null }) }
  if (Get-DockerOk) {
    $ver = & docker version --format '{{.Server.Version}}' 2>$null
    if ($LASTEXITCODE -eq 0) {
      $all = @(& docker ps -a --format '{{.Status}}' 2>$null)
      $h['docker_server'] = "$ver"
      $h['containers_total'] = $all.Count
      $h['running'] = @($all | Where-Object { $_ -like 'Up*' }).Count
      $h['unhealthy'] = @($all | Where-Object { $_ -like '*unhealthy*' }).Count
      $h['exited'] = @($all | Where-Object { $_ -like 'Exited*' }).Count
    } else { $h['docker_server'] = 'unavailable' }
  } else { $h['docker_server'] = 'docker not found' }
  $t = @($h.GetEnumerator() | Where-Object { $_.Key -ne 'full_check_script' } | ForEach-Object { '{0}: {1}' -f $_.Key, $_.Value })
  if ($h.full_check_script) { $t += "full check: run $script" }
  Out-Result ([pscustomobject]$h) $t
  if ($h['docker_server'] -in @('unavailable','docker not found')) { exit 1 }
}

function Cmd-Services {
  $names = 'CloudflareTunnel','ContainerWatchdog','GeekomBot','ProcessMonitor','RAGWatcher'
  $rows = foreach ($n in $names) {
    $s = Get-Service -Name $n -ErrorAction SilentlyContinue
    [pscustomobject]@{ name = $n; status = $(if ($s) { "$($s.Status)" } else { 'not found' }); start = $(if ($s) { "$($s.StartType)" } else { '' }) }
  }
  Out-Result ([pscustomobject]@{ services = @($rows) }) ($rows | ForEach-Object { '{0,-18} {1,-10} {2}' -f $_.name, $_.status, $_.start })
}

function Cmd-Architecture {
  $f = 'D:\dev\system_architecture.md'
  if (-not (Test-Path $f)) { Out-Result ([pscustomobject]@{ error = "missing $f" }) @("missing $f"); exit 1 }
  $fence = $false; $heads = @(Get-Content $f -Encoding UTF8 | Where-Object { if ($_ -match '^\s*```') { $fence = -not $fence; return $false }; (-not $fence) -and ($_ -match '^#{1,2} ') } | Select-Object -First 15)
  $mt = (Get-Item $f).LastWriteTime.ToString('yyyy-MM-dd HH:mm')
  Out-Result ([pscustomobject]@{ path = $f; mtime = $mt; headings = $heads }) (@("$f  mtime=$mt") + ($heads | ForEach-Object { "  $_" }))
}

switch ($Cmd) {
  'help'         { Cmd-Help }
  'paths'        { Cmd-Paths }
  'aida'         { Cmd-Aida }
  'docker'       { Cmd-Docker }
  'health'       { Cmd-Health }
  'services'     { Cmd-Services }
  'architecture' { Cmd-Architecture }
  default {
    if ($Json) { [pscustomobject]@{ error = "unknown command: $Cmd"; commands = @($Commands.Keys) } | ConvertTo-Json -Compress }
    else { Write-Output "unknown command: $Cmd"; Cmd-Help }
    exit 2
  }
}
exit 0