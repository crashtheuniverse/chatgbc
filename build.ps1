# Assembles src/ into build/chatgbc.gbc (CGB-only, MBC5).
#
# Two entry points share everything below src/. -Lab links src/lab/main.asm - no
# keyboard, no frame, driven by the harness - and writes build/chatgbc-lab.gbc.
# The default links src/app/main.asm, which is what ships.
param([switch]$Quiet, [switch]$Lab)

$ErrorActionPreference = 'Stop'
$root  = $PSScriptRoot
$rgbds = Join-Path $root 'tools\rgbds\bin'
$build = Join-Path $root 'build'
$py    = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path (Join-Path $rgbds 'rgbasm.exe'))) { throw 'toolchain missing - run .\bootstrap.ps1' }
New-Item -ItemType Directory -Force -Path $build | Out-Null

# Generated sources.
#
# src/font.inc is committed, so a clone that only wants to assemble does not
# need the .venv or the upstream font. Regenerate only when the source is here.
$fontSrc = Join-Path $root 'tools\font8x8_basic.h'
$fontInc = Join-Path $root 'src\font.inc'
if ((Test-Path $fontSrc) -and (Test-Path $py)) {
    & $py (Join-Path $root 'py\gen_font.py')
    if ($LASTEXITCODE -ne 0) { throw 'gen_font.py failed' }
} elseif (-not (Test-Path $fontInc)) {
    throw 'src\font.inc missing and cannot be generated - run .\bootstrap.ps1'
}

# The weight blobs are the model itself, far too large to commit. weights.asm
# INCBINs them, so without this step rgbasm fails on a missing file rather than
# on anything a reader could act on.
if (-not (Test-Path (Join-Path $build 'blobs\tbl_rsqrt.bin'))) {
    if (-not (Test-Path (Join-Path $root 'models\stories260K.bin'))) {
        throw 'model checkpoint missing - run .\bootstrap.ps1'
    }
    if (-not (Test-Path $py)) { throw 'python venv missing - run .\bootstrap.ps1' }
    if (-not $Quiet) { Write-Host '  exporting weights (first build only)' }
    & $py (Join-Path $root 'py\export.py')
    if ($LASTEXITCODE -ne 0) { throw 'export.py failed' }
}

$variant = if ($Lab) { 'lab' } else { 'app' }
$romName = if ($Lab) { 'chatgbc-lab' } else { 'chatgbc' }
$outDir  = Join-Path $build $variant
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$sources = @(Get-ChildItem (Join-Path $root 'src') -Filter *.asm) +
           @(Get-ChildItem (Join-Path $root "src\$variant") -Filter *.asm) |
           Sort-Object Name
$objects = @()
foreach ($s in $sources) {
    $o = Join-Path $outDir ($s.BaseName + '.o')
    if (-not $Quiet) { Write-Host "  rgbasm $($s.Name)" }
    & (Join-Path $rgbds 'rgbasm.exe') -Weverything -I (Join-Path $root 'src') -o $o $s.FullName
    if ($LASTEXITCODE -ne 0) { throw "rgbasm failed on $($s.Name)" }
    $objects += $o
}

$rom = Join-Path $build ($romName + '.gbc')
& (Join-Path $rgbds 'rgblink.exe') -o $rom `
    -n (Join-Path $build ($romName + '.sym')) `
    -m (Join-Path $build ($romName + '.map')) $objects
if ($LASTEXITCODE -ne 0) { throw 'rgblink failed' }

# -C: CGB only. -v: fix header checksums and logo. -p 0xFF: pad.
& (Join-Path $rgbds 'rgbfix.exe') -C -m MBC5 -t CHATGBC -i CGBX -p 0xFF -v $rom
if ($LASTEXITCODE -ne 0) { throw 'rgbfix failed' }

Write-Host "built $rom ($((Get-Item $rom).Length) bytes)"
