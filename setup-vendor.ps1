# Checks out the two vendor/ submodules (hermes-agent at the pinned upstream commit, keepsakedb at its release tag)
# and builds the Hermes venv. vendor/ is never edited; re-run this on a fresh clone or after deleting the venv.
param([string]$LocalKeepsake = "")   # a KeepsakeDB checkout (e.g. D:\dev\KeepsakeDB) installed editable while developing it; default = the submodule
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Engine = Join-Path $Root "vendor\hermes-agent"

# the pins live in .gitmodules; hermes-agent is fetched shallow (its full history is over 1 GB)
git -C $Root submodule update --init --depth 1 vendor/hermes-agent
git -C $Root submodule update --init vendor/keepsakedb
Push-Location $Engine
uv venv .venv --python 3.11
uv pip install --python .venv\Scripts\python.exe -e . mem0ai qdrant-client
Pop-Location
Write-Host ("vendor/hermes-agent ready (upstream " + (git -C $Engine rev-parse --short HEAD) + ")")

# plugins/ -> home/plugins/ (Hermes loads user plugins from HERMES_HOME/plugins/<name>/)
New-Item -ItemType Directory -Force home\plugins | Out-Null
Get-ChildItem plugins -Directory | ForEach-Object { if (-not (Test-Path (Join-Path 'home\plugins' $_.Name))) { New-Item -ItemType Junction -Path (Join-Path 'home\plugins' $_.Name) -Target $_.FullName | Out-Null } }
# KeepsakeDB (our memory engine, upstream Yooouuuuuuu/KeepsakeDB) into the Hermes venv: the submodule at its release
# tag, or a local checkout while developing it (release, bump the submodule, then run this again without -LocalKeepsake)
if ($LocalKeepsake -ne "") {
  uv pip install --python vendor\hermes-agent\.venv\Scripts\python.exe -e $LocalKeepsake
} else {
  uv pip install --python vendor\hermes-agent\.venv\Scripts\python.exe -e vendor\keepsakedb
}
uv pip install --python vendor\hermes-agent\.venv\Scripts\python.exe ddgs   # keyless web search for the web-search extension
