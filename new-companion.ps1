# new-companion.ps1 — create a 556 character as a Hermes profile under home/profiles/<name>.
#   .\new-companion.ps1 -Name sayo -DisplayName "小夜"
# Creates the profile with Hermes (cloned config), installs the template (companion.json, kokoro.json
# with the fixed memory subject, psyche.json, SOUL skeleton, people/<you>.md, env.example), links the kokoro and
# psyche plugins.
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
foreach ($rel in @("companion.json", "kokoro.json", "psyche.json", "SOUL.md", ("people\" + [char]0x4F60 + ".md"))) {
    $src = Join-Path $Tpl $rel
    $dst = Join-Path $Dir $rel
    New-Item -ItemType Directory -Force (Split-Path -Parent $dst) | Out-Null
    $text = (Get-Content $src -Raw -Encoding UTF8).Replace("{{display}}", $DisplayName).Replace("{{avatar}}", $AvatarModel)
    [IO.File]::WriteAllText($dst, $text, (New-Object Text.UTF8Encoding $false))  # no BOM: JSON readers choke on it
}
Copy-Item (Join-Path $Tpl "env.example") (Join-Path $Dir "env.example")
foreach ($d in @("memory", "backups", "logs", "plugins", "people")) { New-Item -ItemType Directory -Force (Join-Path $Dir $d) | Out-Null }
$link = Join-Path $Dir "plugins\kokoro"
if (-not (Test-Path $link)) { New-Item -ItemType Junction -Path $link -Target (Join-Path $Root "plugins\kokoro") | Out-Null }
$link = Join-Path $Dir "plugins\psyche"
if (-not (Test-Path $link)) { New-Item -ItemType Junction -Path $link -Target (Join-Path $Root "plugins\psyche") | Out-Null }
# tools: baseline = none (0.8.6; memory is injected, not a tool); Hermes's built-in memory writer off; extensions via Settings
$cfgPath = Join-Path $Dir "config.yaml"
$raw = Get-Content $cfgPath -Raw -Encoding UTF8
if ($raw -match '(?m)^memory:\s*\r?\n\s+provider: kokoro') {
    $raw = $raw -replace '(?m)^memory:\s*\r?\n(\s+)provider: kokoro', "memory:`n`$1provider: kokoro`n`$1memory_enabled: false`n`$1user_profile_enabled: false"
} else {
    $raw = $raw.TrimEnd() + "`nmemory:`n    provider: kokoro`n    memory_enabled: false`n    user_profile_enabled: false`n"
}
# her inner life: the psyche plugin must be on the opt-in list (plugins.enabled); kokoro is activated by memory.provider
if ($raw -match '(?m)^plugins:\s*
?
\s+enabled: \[\]') { $raw = $raw -replace '(?m)^plugins:\s*
?
(\s+)enabled: \[\]', "plugins:`n`$1enabled: [psyche]" }
elseif ($raw -notmatch '(?m)^plugins:') { $raw = $raw.TrimEnd() + "`nplugins:`n    enabled: [psyche]`n" }
if ($raw -notmatch '(?m)^platform_toolsets:') { $raw = $raw.TrimEnd() + "`nplatform_toolsets:`n    api_server: []`n    telegram: []`n    cli: []`n" }
Set-Content $cfgPath -Encoding UTF8 -NoNewline -Value $raw
# starting and stopping her is routine in 556: no "Gateway shutting down" pings in her DM (dev knob telegram.restart_notice)
$cfg = Join-Path $Dir "config.yaml"
if ((Get-Content $cfg -Raw -Encoding UTF8) -notmatch '(?m)^platforms:') {
    Add-Content $cfg -Encoding UTF8 -Value "`nplatforms:`n    telegram:`n        gateway_restart_notification: false`n        allow_admin_from: [`"556-no-admin`"]`n        user_allowed_commands: []`n"
}

Write-Host ""
Write-Host "Created $DisplayName at $Dir"
Write-Host "  - edit SOUL.md (her persona), people/<you>.md (how she addresses you), psyche.json (her personality)"
Write-Host "  - channels: copy env.example to .env and fill her OWN bot tokens + your user ids (see docs/structure/structure.md)"
Write-Host "  - she is on the roster now (off duty); start her from the app's 名單 tab"
