<#
.SYNOPSIS
  Genera themes-manifest.json (con sha256 de cada tema) y reúne los assets de
  temas para subir a un GitHub Release. Es lo único necesario para publicar una
  actualización SOLO de temas (sin reconstruir el .exe).

.OUTPUTS
  dist/release-assets/themes-manifest.json
  dist/release-assets/<cada-tema>.json
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ThemesDir = Join-Path $Root "themes"
$OutDir = Join-Path $Root "dist/release-assets"

New-Item -ItemType Directory -Force $OutDir | Out-Null

$version = (Select-String -Path (Join-Path $Root "src/pptx2web/__init__.py") `
    -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value

$themes = @{}
foreach ($file in Get-ChildItem -Path $ThemesDir -Filter *.json) {
    $sha = (Get-FileHash -Path $file.FullName -Algorithm SHA256).Hash.ToLower()
    $themes[$file.Name] = $sha
    Copy-Item -Force $file.FullName (Join-Path $OutDir $file.Name)
}

$manifest = [ordered]@{ version = $version; themes = $themes }
$manifest | ConvertTo-Json -Depth 5 |
    Set-Content -Path (Join-Path $OutDir "themes-manifest.json") -Encoding UTF8

Write-Host "themes-manifest.json generado con $($themes.Count) tema(s) en $OutDir"
