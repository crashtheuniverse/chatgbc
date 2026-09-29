# ChatGBC v0.4 build: src/ -> build/chatgbc.gbc (CGB-only, MBC5). Toolchain from tools/; output in build/.
# -Lab links src/lab/main.asm (the harness-driven entry); default is src/app.
#
# -Rei builds the conversational cartridge, build/rei.gbc (rei-lab.gbc with
# -Lab): it exports the chat checkpoint (CHAT_MODE EQU 1 in src/model.inc, which
# is what switches every Rei file on), assembles the same sources, titles the
# cartridge REI, and then re-exports the story model so the tracked
# src/model.inc and src/weights.asm are back in story form and `git status`
# is clean. -Keep skips that last step and leaves the tree (and build/blobs)
# in chat form, which the Rei test suite needs; test.ps1 restores it.
# The chat checkpoint and its tokenizer: rei_env.ps1 (models/rei.bin, or
# $env:REI_PIP5 / $env:REI_TOKENIZER).
#
# The plain (non -Rei) build reads src/weights.asm's own INCBINs from
# build/blobs, which is gitignored: a fresh clone has none. If they are
# missing this exports the story checkpoint (models/ts3L_v1024.bin) first;
# once build/blobs exists, later builds skip straight to rgbasm. Delete
# build/ (or just build/blobs) to force a re-export.
param([switch]$Quiet, [switch]$Lab, [switch]$Census, [switch]$Rei, [switch]$Keep)
$ErrorActionPreference = 'Stop'
$root  = $PSScriptRoot
$python = Join-Path $root '.venv/Scripts/python.exe'
. (Join-Path $root 'rei_env.ps1')
$chatEnv = Get-ReiEnv $root
function Export-Model {
    Push-Location $root
    try {
        & $python (Join-Path $root 'py/export5.py') | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'export5 failed' }
    } finally { Pop-Location }
}
$rgbds = Join-Path $root 'tools/rgbds/bin'
$build = Join-Path $root 'build'
New-Item -ItemType Directory -Force $build | Out-Null

# -Census is the lab entry with stage timers compiled into the forward pass
# (src/census.inc); its own ROM name, so the test lab stays untouched.
# -Lab alone defines PROBES: the layer-0 snapshot copies and the extra
# selftests the suite reads (src/forward.asm, src/selftest.asm). The app
# never had a reader for them, and the census measures the shipping path,
# so neither assembles them.
if ($Census) { $Lab = $true }
$variant = if ($Lab) { 'lab' } else { 'app' }
$suffix  = if ($Census) { '-census' } elseif ($Lab) { '-lab' } else { '' }
# Typed, because a one-element array assigned from an `if` collapses to a
# scalar, and splatting a scalar hands rgbasm garbage.
[string[]]$defs = if ($Census) { @('-DCENSUS=1') } elseif ($Lab) { @('-DPROBES=1') } else { @() }

# REI_UI switches on the game screen (src/app/rei_*.asm and the IF DEF(REI_UI)
# branches). The Rei lab ROM is the plain chat lab: the suite needs no screen.
if ($Rei -and -not $Lab) { $defs += '-DREI_UI=1' }
$name  = if ($Rei) { 'rei' } else { 'chatgbc' }
$title = if ($Rei) { 'REI' } else { 'CHATGBC' }
if ($Rei) { $suffix = "-rei$suffix" }
$saved = @{}
if ($Rei) {
    foreach ($k in $chatEnv.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k)
        [Environment]::SetEnvironmentVariable($k, $chatEnv[$k])
    }
    Export-Model
} elseif (-not (Test-Path (Join-Path $build 'blobs/tbl_rsqrt.bin'))) {
    Export-Model
}
try {

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
$stem = if ($Rei) { $name + $suffix.Substring(4) } else { "$name$suffix" }
$rom = Join-Path $build "$stem.gbc"
& (Join-Path $rgbds 'rgblink.exe') -o $rom -n (Join-Path $build "$stem.sym") -m (Join-Path $build "$stem.map") @objs
if ($LASTEXITCODE -ne 0) { throw 'rgblink failed' }
# Rei keeps her conversation on the cartridge: MBC5+RAM+BATTERY, one 8 KB bank.
# The story cartridge has no RAM, and its header does not change.
[string[]]$mbc = if ($Rei) { @('-m', 'MBC5+RAM+BATTERY', '-r', '2') } else { @('-m', 'MBC5') }
& (Join-Path $rgbds 'rgbfix.exe') -C $mbc -t $title -i CGBX -p 0xFF -v $rom
if ($LASTEXITCODE -ne 0) { throw 'rgbfix failed' }
Write-Host "built $rom ($((Get-Item $rom).Length) bytes)"

} finally {
    if ($Rei) {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
        if (-not $Keep) { Export-Model }       # back to the story form git tracks
    }
}
