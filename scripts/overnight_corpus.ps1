param([string[]]$Years = @())
# Nightly corpus batch: transcribe -> ingest -> number extraction, one meeting at a time.
# Idempotent: skips a year whose transcript already has more than 500 segments.
$ErrorActionPreference = "Continue"
$root = "C:\Users\Administrator\Documents\deepseek-harness\default-workspace\buffett-pack"
$skill = "$root\skills\buffett-mind"
$python = "D:\dsh-data\venv-whisper\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "$root\.venv-whisper\Scripts\python.exe" }
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUNBUFFERED = "1"
$log = "$skill\out\overnight.log"
New-Item -ItemType Directory -Force -Path "$skill\out" | Out-Null

$jobs = @(
  @(2023, "https://www.youtube.com/watch?v=Dv97-S9ZL-8"),
  @(2022, "https://www.youtube.com/watch?v=5_bfCPcfSdw"),
  @(2021, "https://www.youtube.com/watch?v=npRYd31diFo"),
  @(2019, "https://www.youtube.com/watch?v=geRIJQJXRVo"),
  @(2018, "https://www.youtube.com/watch?v=sYiv4AMq9Tk"),
  @(2017, "https://www.youtube.com/watch?v=kA42-y1y8PU"),
  @(2016, "https://www.youtube.com/watch?v=iciNJLMpACQ"),
  @(2015, "https://www.youtube.com/watch?v=zh0L7ObIFHQ"),
  @(2014, "https://www.youtube.com/watch?v=bkHKP07SMTY"),
  @(2013, "https://www.youtube.com/watch?v=b1-QzoQmprM"),
  @(2012, "https://www.youtube.com/watch?v=-Y6kwyWnKSM"),
  @(2011, "https://www.youtube.com/watch?v=fKTmuoU9IVE")
)

$yearFilter = @()
foreach ($y in $Years) {
  foreach ($part in ([string]$y -split ",")) {
    if ($part.Trim()) { $yearFilter += [int]$part.Trim() }
  }
}

if ($yearFilter.Count -gt 0) {
  $jobs = @($jobs | Where-Object { $yearFilter -contains $_[0] })
  $picked = ($jobs | ForEach-Object { $_[0] }) -join ","
  "years: $picked" | Tee-Object -FilePath $log -Append
}

foreach ($j in $jobs) {
  $year = $j[0]
  $url = $j[1]
  $jsonl = Join-Path $skill ("data\video\" + $year + "-meeting.jsonl")
  $lines = 0
  if (Test-Path $jsonl) { $lines = (Get-Content $jsonl | Measure-Object).Count }
  if ($lines -gt 500) {
    "[$(Get-Date -Format 'HH:mm')] skip $year ($lines segments)" | Tee-Object -FilePath $log -Append
    continue
  }
  "[$(Get-Date -Format 'HH:mm')] ==== $year start ====" | Tee-Object -FilePath $log -Append
  & $python "$skill\scripts\transcribe_video.py" --url $url --out $jsonl 2>&1 |
    Select-String -Pattern 'done|audio|model|Error|error|segments' |
    Tee-Object -FilePath $log -Append

  if (-not (Test-Path $jsonl) -or (Get-Content $jsonl | Measure-Object).Count -lt 50) {
    "[$(Get-Date -Format 'HH:mm')] $year produced nothing, skip ingest (check proxy)" | Tee-Object -FilePath $log -Append
    continue
  }
  "[$(Get-Date -Format 'HH:mm')] $year ingest" | Tee-Object -FilePath $log -Append
  $title = "$year 伯克希尔股东大会"
  python "$skill\scripts\build_video_corpus.py" --segments $jsonl --title $title --url $url --year $year 2>&1 |
    Tee-Object -FilePath $log -Append
  $tsv = Join-Path $skill ("out\" + $year + "-numbers.tsv")
  python "$skill\scripts\validate_transcript.py" --segments $jsonl --tsv $tsv --limit 1 2>&1 |
    Select-Object -First 2 | Tee-Object -FilePath $log -Append
}
"[$(Get-Date -Format 'HH:mm')] all done" | Tee-Object -FilePath $log -Append
