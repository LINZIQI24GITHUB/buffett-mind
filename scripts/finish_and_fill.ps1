# Wait for the current batch to finish, free C: (model + venv), then retry the failed years.
$ErrorActionPreference = "Continue"
$root = "C:\Users\Administrator\Documents\deepseek-harness\default-workspace\buffett-pack"
$skill = "$root\skills\buffett-mind"
$log = "$skill\out\finish.log"
New-Item -ItemType Directory -Force -Path "$skill\out" | Out-Null

function Count-Transcribing {
  return (Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    Where-Object { $_.CommandLine -match 'transcribe_video' } | Measure-Object).Count
}

"[$(Get-Date -Format 'HH:mm')] waiting for current batch" | Tee-Object -FilePath $log -Append
for ($i = 0; $i -lt 240; $i++) {
  if ((Count-Transcribing) -eq 0) {
    Start-Sleep -Seconds 45
    if ((Count-Transcribing) -eq 0) { break }
  }
  Start-Sleep -Seconds 60
}

"[$(Get-Date -Format 'HH:mm')] batch idle, cleaning C: copies" | Tee-Object -FilePath $log -Append
Remove-Item "$root\.models" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$root\.venv-whisper" -Recurse -Force -ErrorAction SilentlyContinue
$free = [math]::Round((Get-PSDrive C).Free / 1GB, 2)
"[$(Get-Date -Format 'HH:mm')] C free = $free GB" | Tee-Object -FilePath $log -Append

"[$(Get-Date -Format 'HH:mm')] retry 2018,2016,2014" | Tee-Object -FilePath $log -Append
powershell -NoProfile -ExecutionPolicy Bypass -File "$skill\scripts\overnight_corpus.ps1" -Years 2018,2016,2014
"[$(Get-Date -Format 'HH:mm')] retry finished" | Tee-Object -FilePath $log -Append
