# new-companion.ps1 — create a 556 character as a Hermes profile under home/profiles/<name>.
#   .\new-companion.ps1 -Name sayo -DisplayName "小夜"
# Creates the profile with Hermes (cloned config), installs the template (companion.json, kokoro.json
# with the fixed memory subject, SOUL skeleton, USER.md, env.example), links the kokoro plugin.
# Nothing starts: she appears on the roster, off duty, until you start her from the app.
param(
    [Parameter(Mandatory = $true)][string]$Name,
    [Parameter(Mandatory = $true)][string]$DisplayName,
    [string]$AvatarModel = "hiyori/Hiyori.model3.json",
    [string]$Description = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Home556 = Join-Path $Root "home"
$Hermes = Join-Path $Root "vendor\hermes-agent\.venv\Scripts\hermes.exe"
$Tpl = Join-Path $Root "templates\companion"
$Dir = Join-Path $Home556 "profiles\$Name"

if ($Name -notmatch '^[a-z0-9_-]+$') { throw "name must be lowercase letters, digits, _ or - (it is a folder and a Hermes profile id)" }
if (Test-Path $Dir) { throw "profile already exists: $Dir" }
if ($Description -eq "") { $Description = "556 Production — $DisplayName" }

$env:HERMES_HOME = $Home556
$env:PYTHONIOENCODING = "utf-8"
& $Hermes profile create $Name --clone --no-alias --description $Description
if ($LASTEXITCODE -ne 0) { throw "hermes profile create failed" }

# template files (UTF-8, {{display}} placeholder)
foreach ($rel in @("companion.json", "kokoro.json", "SOUL.md", "memories\USER.md")) {
    $src = Join-Path $Tpl $rel
    $dst = Join-Path $Dir $rel
    New-Item -ItemType Directory -Force (Split-Path -Parent $dst) | Out-Null
    (Get-Content $src -Raw -Encoding UTF8).Replace("{{display}}", $DisplayName).Replace("{{avatar}}", $AvatarModel) |
        Set-Content $dst -Encoding UTF8 -NoNewline
}
Copy-Item (Join-Path $Tpl "env.example") (Join-Path $Dir "env.example")
foreach ($d in @("memory", "backups", "logs", "plugins")) { New-Item -ItemType Directory -Force (Join-Path $Dir $d) | Out-Null }
$link = Join-Path $Dir "plugins\kokoro"
if (-not (Test-Path $link)) { New-Item -ItemType Junction -Path $link -Target (Join-Path $Root "plugins\kokoro") | Out-Null }
# starting and stopping her is routine in 556: no "Gateway shutting down" pings in her DM (dev knob telegram.restart_notice)
$cfg = Join-Path $Dir "config.yaml"
if ((Get-Content $cfg -Raw -Encoding UTF8) -notmatch '(?m)^platforms:') {
    Add-Content $cfg -Encoding UTF8 -Value "`nplatforms:`n    telegram:`n        gateway_restart_notification: false`n        allow_admin_from: [`"556-no-admin`"]`n        user_allowed_commands: []`n"
}

Write-Host ""
Write-Host "Created $DisplayName at $Dir"
Write-Host "  - edit SOUL.md (her persona) and memories/USER.md (how she addresses you)"
Write-Host "  - channels: copy env.example to .env and fill her OWN bot tokens + your user ids (see docs/PLAN-channels.md)"
Write-Host "  - she is on the roster now (off duty); start her from the app's 名單 tab"
