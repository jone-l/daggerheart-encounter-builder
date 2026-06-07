# build.ps1 — Build Daggerheart Encounter Builder into a standalone executable.
#
# Output: dist\DaggerheartEncounterBuilder\DaggerheartEncounterBuilder.exe
#
# Usage:
#   .\build.ps1
#
# After a successful build, create a Windows shortcut (or taskbar pin) pointing to
# the exe in dist\DaggerheartEncounterBuilder\. The folder must stay in place —
# the exe loads its resources from sibling files in that directory.

$spec = 'daggerheart-encounter-builder.spec'

Write-Host 'Building Daggerheart Encounter Builder...' -ForegroundColor Cyan

# PyInstaller's --clean uses shutil.rmtree which fails on read-only .pyc files it
# creates itself. Pre-delete with Remove-Item -Force which handles read-only files.
foreach ($dir in @('build', 'dist')) {
    if (Test-Path $dir) {
        Write-Host "Cleaning $dir..." -ForegroundColor DarkGray
        Remove-Item $dir -Recurse -Force
    }
}

python -m PyInstaller $spec --noconfirm

if ($LASTEXITCODE -ne 0) {
    Write-Host 'Build failed.' -ForegroundColor Red
    exit 1
}

$exePath = (Resolve-Path 'dist\DaggerheartEncounterBuilder\DaggerheartEncounterBuilder.exe').Path
Write-Host ''
Write-Host 'Build complete!' -ForegroundColor Green
Write-Host "Executable: $exePath"
Write-Host ''
Write-Host 'Pin to taskbar: right-click the exe in Explorer -> Show more options -> Pin to taskbar'
