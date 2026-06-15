<#
.SYNOPSIS
  Compila pptx2web-gui (PyInstaller onedir) + el instalador (Inno Setup) en un
  solo paso, y prepara los assets de OTA (themes-manifest.json).

.DESCRIPTION
  1. Lee la versión de src/pptx2web/__init__.py (fuente única).
  2. PyInstaller con packaging/pptx2web.spec → dist/pptx2web-gui/.
  3. Copia recursos externos (player\, themes\, bin\ffmpeg.exe) JUNTO al .exe,
     porque el código congelado los busca con Path(sys.executable).parent.
  4. Genera dist/release-assets/themes-manifest.json (canal OTA de temas).
  5. Si ISCC.exe (Inno Setup) está disponible, produce
     dist/pptx2web-setup-<version>.exe.

.NOTES
  Requiere: pip install pyinstaller  ·  Inno Setup 6 (ISCC.exe en PATH) opcional.
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$version = (Select-String -Path "src/pptx2web/__init__.py" `
    -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
Write-Host "==> Compilando pptx2web $version" -ForegroundColor Cyan

# 1. PyInstaller (onedir, sin consola)
python -m PyInstaller --clean --noconfirm "packaging/pptx2web.spec"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falló (código $LASTEXITCODE)" }

$dist = Join-Path $Root "dist/pptx2web-gui"

# 2. Recursos externos junto al .exe
Copy-Item -Recurse -Force "player" (Join-Path $dist "player")
Copy-Item -Recurse -Force "themes" (Join-Path $dist "themes")
if (Test-Path "bin/ffmpeg.exe") {
    New-Item -ItemType Directory -Force (Join-Path $dist "bin") | Out-Null
    Copy-Item -Force "bin/ffmpeg.exe" (Join-Path $dist "bin/ffmpeg.exe")
}
Write-Host "==> Recursos externos copiados al dist" -ForegroundColor Green

# 3. Manifiesto de temas para OTA
& (Join-Path $PSScriptRoot "make-themes-manifest.ps1")

# 4. Instalador (opcional)
$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($iscc) {
    & $iscc.Source "/DMyAppVersion=$version" "packaging/installer.iss"
    if ($LASTEXITCODE -ne 0) { throw "ISCC falló (código $LASTEXITCODE)" }
    Write-Host "==> Instalador: dist/pptx2web-setup-$version.exe" -ForegroundColor Green
} else {
    Write-Warning "ISCC.exe (Inno Setup) no está en PATH; se omite el instalador. El dist en $dist ya es ejecutable."
}
