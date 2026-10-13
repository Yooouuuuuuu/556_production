# Restores vendor/hermes-agent at the pinned upstream commit and builds its venv.
# vendor/ is never edited; re-run this on a fresh machine or after deleting the venv.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Engine = Join-Path $Root "vendor\hermes-agent"
$Pin = "7166071f"   # NousResearch/hermes-agent commit vendored for 556 Production

if (-not (Test-Path (Join-Path $Engine "pyproject.toml"))) {
  git clone https://github.com/NousResearch/hermes-agent $Engine
  git -C $Engine checkout $Pin
  Remove-Item -Recurse -Force (Join-Path $Engine ".git")
}
Push-Location $Engine
uv venv .venv --python 3.11
uv pip install --python .venv\Scripts\python.exe -e . mem0ai qdrant-client
Pop-Location
Write-Host "vendor/hermes-agent ready (pin $Pin)"

# plugins/ -> home/plugins/ (Hermes loads user plugins from HERMES_HOME/plugins/<name>/)
New-Item -ItemType Directory -Force home\plugins | Out-Null
Get-ChildItem plugins -Directory | ForEach-Object { if (-not (Test-Path (Join-Path 'home\plugins' $_.Name))) { New-Item -ItemType Junction -Path (Join-Path 'home\plugins' $_.Name) -Target $_.FullName | Out-Null } }
# KeepsakeDB (memory engine) into the Hermes venv
uv pip install --python vendor\hermes-agent\.venv\Scripts\python.exe -e D:\dev\KeepsakeDB
