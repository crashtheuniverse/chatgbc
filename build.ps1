# Assembles src/ into build/chatgbc.gbc (CGB-only, MBC5).
param([switch]$Quiet)

$ErrorActionPreference = 'Stop'
$root  = $PSScriptRoot
$rgbds = Join-Path $root 'tools\rgbds\bin'
$build = Join-Path $root 'build'
$py    = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path (Join-Path $rgbds 'rgbasm.exe'))) { throw 'toolchain missing - run .\bootstrap.ps1' }
New-Item -ItemType Directory -Force -Path $build | Out-Null

# Generated sources
& $py (Join-Path $root 'py\gen_font.py')
if ($LASTEXITCODE -ne 0) { throw 'gen_font.py failed' }

$sources = Get-ChildItem (Join-Path $root 'src') -Filter *.asm | Sort-Object Name
$objects = @()
foreach ($s in $sources) {
    $o = Join-Path $build ($s.BaseName + '.o')
    if (-not $Quiet) { Write-Host "  rgbasm $($s.Name)" }
    & (Join-Path $rgbds 'rgbasm.exe') -Weverything -I (Join-Path $root 'src') -o $o $s.FullName
    if ($LASTEXITCODE -ne 0) { throw "rgbasm failed on $($s.Name)" }
    $objects += $o
}

$rom = Join-Path $build 'chatgbc.gbc'
& (Join-Path $rgbds 'rgblink.exe') -o $rom `
    -n (Join-Path $build 'chatgbc.sym') -m (Join-Path $build 'chatgbc.map') $objects
if ($LASTEXITCODE -ne 0) { throw 'rgblink failed' }

# -C: CGB only. -v: fix header checksums and logo. -p 0xFF: pad.
& (Join-Path $rgbds 'rgbfix.exe') -C -m MBC5 -t CHATGBC -i CGBX -p 0xFF -v $rom
if ($LASTEXITCODE -ne 0) { throw 'rgbfix failed' }

Write-Host "built $rom ($((Get-Item $rom).Length) bytes)"
