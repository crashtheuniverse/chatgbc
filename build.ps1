# ChatGBC v0.4 build: src/ -> build/chatgbc.gbc (CGB-only, MBC5). Toolchain from tools/; output in build/.
# -Lab links src/lab/main.asm (the harness-driven entry); default is src/app.
param([switch]$Quiet, [switch]$Lab, [switch]$Census)
$ErrorActionPreference = 'Stop'
$root  = $PSScriptRoot
$rgbds = Join-Path $root 'tools/rgbds/bin'
$build = Join-Path $root 'build'
New-Item -ItemType Directory -Force $build | Out-Null

# -Census is the lab entry with stage timers compiled into the forward pass
# (src/census.inc); its own ROM name, so the test lab stays untouched.
if ($Census) { $Lab = $true }
$variant = if ($Lab) { 'lab' } else { 'app' }
$suffix  = if ($Census) { '-census' } elseif ($Lab) { '-lab' } else { '' }
# Typed, because a one-element array assigned from an `if` collapses to a
# scalar, and splatting a scalar hands rgbasm garbage.
[string[]]$defs = if ($Census) { @('-DCENSUS=1') } else { @() }

$objs = @()
$sources = @(Get-ChildItem (Join-Path $root 'src') -Filter *.asm) +
           @(Get-ChildItem (Join-Path $root "src/$variant") -Filter *.asm)
foreach ($s in $sources) {
    $o = Join-Path $build ($s.BaseName + $suffix + '.o')
    if (-not $Quiet) { Write-Host "  rgbasm $($s.Name)" }
    & (Join-Path $rgbds 'rgbasm.exe') -Weverything $defs -I (Join-Path $root 'src') -o $o $s.FullName
    if ($LASTEXITCODE -ne 0) { throw "rgbasm failed on $($s.Name)" }
    $objs += $o
}
$rom = Join-Path $build "chatgbc$suffix.gbc"
& (Join-Path $rgbds 'rgblink.exe') -o $rom -n (Join-Path $build "chatgbc$suffix.sym") @objs
if ($LASTEXITCODE -ne 0) { throw 'rgblink failed' }
& (Join-Path $rgbds 'rgbfix.exe') -C -m MBC5 -t CHATGBC -i CGBX -p 0xFF -v $rom
if ($LASTEXITCODE -ne 0) { throw 'rgbfix failed' }
Write-Host "built $rom ($((Get-Item $rom).Length) bytes)"
