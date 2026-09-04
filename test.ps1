# Build both ROMs from this directory, then run the suite.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot 'build.ps1') -Quiet
    & (Join-Path $PSScriptRoot 'build.ps1') -Quiet -Lab
    & (Join-Path $PSScriptRoot '.venv/Scripts/python.exe') -m pytest (Join-Path $PSScriptRoot 'py/tests') -q
} finally { Pop-Location }
