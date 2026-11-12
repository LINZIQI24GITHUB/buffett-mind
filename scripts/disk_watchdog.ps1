# Disk watchdog for the overnight transcription run.
# Deletes stale asr-* temp dirs only when C: free space drops below 5 GB.
# A dir is considered stale if its last write was more than 25 minutes ago.
$root = "C:\Users\Administrator\Documents\deepseek-harness\default-workspace"
$log = "$root\buffett-pack\skills\buffett-mind\out\disk-watch.log"
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

while ($true) {
  Start-Sleep -Seconds 300
  $free = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
  $stamp = Get-Date -Format "HH:mm"
  Add-Content -Path $log -Value "$stamp free=$free GB" -Encoding utf8

  if ($free -lt 5) {
    $now = Get-Date
    Get-ChildItem $root -Directory -Filter 'asr-*' -ErrorAction SilentlyContinue | ForEach-Object {
      $age = ($now - $_.LastWriteTime).TotalMinutes
      if ($age -gt 25) {
        $size = [math]::Round((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB)
        $name = $_.Name
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        Add-Content -Path $log -Value ("$stamp removed " + $name + " (" + $size + " MB, idle " + [math]::Round($age) + " min)") -Encoding utf8
      }
    }
  }
}
