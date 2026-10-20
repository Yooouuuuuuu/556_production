# install-character.ps1 — put one of the versioned characters (characters/<id>/) into a profile.
#   .\install-character.ps1 -Name <id>              (creates the profile with new-companion.ps1 if missing)
# Copies SOUL.md, companion.json, psyche.json and people/*.md over the profile's files. Seed memories are
# loaded separately with seed-memories.py while 556d's embedder is up and the character is NOT running.
param([Parameter(Mandatory = $true)][string]$Name)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Src = Join-Path $Root "characters\$Name"
if (-not (Test-Path $Src)) { throw "no such character: $Src" }
$Dir = Join-Path $Root "home\profiles\$Name"
$cj = Get-Content (Join-Path $Src "companion.json") -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not (Test-Path $Dir)) {
    & (Join-Path $Root "new-companion.ps1") -Name $Name -DisplayName $cj.display_name -AvatarModel $cj.avatar_model
}
$utf8 = New-Object Text.UTF8Encoding $false
foreach ($f in @("SOUL.md", "companion.json", "psyche.json")) {
    [IO.File]::WriteAllText((Join-Path $Dir $f), (Get-Content (Join-Path $Src $f) -Raw -Encoding UTF8), $utf8)
}
# kokoro.json keys of the character (e.g. address_default: how she addresses you until Settings has your name)
$kk = Join-Path $Src "kokoro.json"
if (Test-Path $kk) {
    $dst = Join-Path $Dir "kokoro.json"
    $cur = Get-Content $dst -Raw -Encoding UTF8 | ConvertFrom-Json
    $add = Get-Content $kk -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($prop in $add.PSObject.Properties) {
        if ($cur.PSObject.Properties[$prop.Name]) { $cur.($prop.Name) = $prop.Value } else { $cur | Add-Member -NotePropertyName $prop.Name -NotePropertyValue $prop.Value }
    }
    [IO.File]::WriteAllText($dst, ($cur | ConvertTo-Json -Depth 10), $utf8)
}
New-Item -ItemType Directory -Force (Join-Path $Dir "people") | Out-Null
Get-ChildItem (Join-Path $Src "people") -File | ForEach-Object {
    [IO.File]::WriteAllText((Join-Path $Dir ("people\" + $_.Name)), (Get-Content $_.FullName -Raw -Encoding UTF8), $utf8)
}
Write-Host "installed $($cj.display_name) ($Name) into $Dir"
