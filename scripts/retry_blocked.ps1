# Retry years blocked by YouTube's bot check, spaced out so the block can expire.
$ErrorActionPreference = "Continue"
$root = "C:\Users\Administrator\Documents\deepseek-harness\default-workspace\buffett-pack"
$skill = "$root\skills\buffett-mind"
$log = "$skill\out\retry.log"
New-Item -ItemType Directory -Force -Path "$skill\out" | Out-Null

$years = @(2017, 2014)

function Test-Done([int]$y) {
  $f = Join-Path $skill ("data\video\" + $y + "-meeting.jsonl")
  if (-not (Test-Path $f)) { return $false }
  return ((Get-Content $f | Measure-Object).Count -gt 500)
}

for ($round = 1; $round -le 4; $round++) {
  $pending = @($years | Where-Object { -not (Test-Done $_) })
  if ($pending.Count -eq 0) {
    "[$(Get-Date -Format 'HH:mm')] all done" | Tee-Object -FilePath $log -Append
    break
  }
  "[$(Get-Date -Format 'HH:mm')] round $round, waiting 30 min for pending: $($pending -join ',')" | Tee-Object -FilePath $log -Append
  Start-Sleep -Seconds 1800
  $list = ($pending | ForEach-Object { [string]$_ }) -join ","
  "[$(Get-Date -Format 'HH:mm')] round $round retry: $list" | Tee-Object -FilePath $log -Append
  powershell -NoProfile -ExecutionPolicy Bypass -Command "& '$skill\scripts\overnight_corpus.ps1' -Years $list"
}
"[$(Get-Date -Format 'HH:mm')] retry script finished" | Tee-Object -FilePath $log -Append
