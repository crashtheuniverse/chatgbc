# Builds both ROMs, then runs the headless PyBoy suite against them.
#
# The suite runs mostly against the lab build; the keyboard tests need the demo.
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'build.ps1') -Quiet
& (Join-Path $PSScriptRoot 'build.ps1') -Quiet -Lab
& (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -m pytest (Join-Path $PSScriptRoot 'py\tests') -q
exit $LASTEXITCODE
