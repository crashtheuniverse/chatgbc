# Builds the ROM, then runs the headless PyBoy suite against it.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'build.ps1') -Quiet
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m pytest (Join-Path $PSScriptRoot 'py\tests') -q
exit $LASTEXITCODE
