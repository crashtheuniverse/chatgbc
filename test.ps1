# Build both ROMs from this directory, then run the suite - twice: the story
# build, then Rei (the chat export and her screen, py/tests/test_rei_ui.py).
# The tree is left in story form, as git tracks it.
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
. (Join-Path $PSScriptRoot 'rei_env.ps1')
$chat = Get-ReiEnv $PSScriptRoot         # what build.ps1 -Rei exports
try {
    Write-Host '--- story ---'
    # Whatever an interrupted run left behind, start from the story export.
    foreach ($k in $chat.Keys) { [Environment]::SetEnvironmentVariable($k, $null) }
    $env:CHATGBC_LAB = $null
    & $python (Join-Path $PSScriptRoot 'py/export5.py') | Out-Null
    & (Join-Path $PSScriptRoot 'build.ps1') -Quiet
    & (Join-Path $PSScriptRoot 'build.ps1') -Quiet -Lab
    & $python (Join-Path $PSScriptRoot 'py/golden5.py') | Out-Null
    & $python -m pytest (Join-Path $PSScriptRoot 'py/tests') -q
    $story = $LASTEXITCODE

    Write-Host '--- rei ---'
    # -Keep leaves src/model.inc, build/blobs and the lab ROM the suite reads
    # in chat form until the suite has run.
    & (Join-Path $PSScriptRoot 'build.ps1') -Quiet -Rei -Keep
    & (Join-Path $PSScriptRoot 'build.ps1') -Quiet -Rei -Lab -Keep
    foreach ($k in $chat.Keys) { [Environment]::SetEnvironmentVariable($k, $chat[$k]) }
    $env:CHATGBC_LAB = 'rei-lab'
    & $python (Join-Path $PSScriptRoot 'py/golden5.py')
    & $python -m pytest (Join-Path $PSScriptRoot 'py/tests') -q
    $rei = $LASTEXITCODE
} finally {
    foreach ($k in $chat.Keys) { [Environment]::SetEnvironmentVariable($k, $null) }
    $env:CHATGBC_LAB = $null
    & $python (Join-Path $PSScriptRoot 'py/export5.py') | Out-Null   # story form again
    & $python (Join-Path $PSScriptRoot 'py/golden5.py') | Out-Null
    Pop-Location
}
if ($story -ne 0 -or $rei -ne 0) { throw "suite failed (story $story, rei $rei)" }
