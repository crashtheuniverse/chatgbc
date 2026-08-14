# Fetches every external dependency into project-local tools/ and .venv/.
# Nothing is installed system-wide. Idempotent; -Force re-downloads.
param([switch]$Force)

$ErrorActionPreference = 'Stop'
$root  = $PSScriptRoot
$tools = Join-Path $root 'tools'

$RGBDS_VER   = 'v1.0.3'
$SAMEBOY_VER = 'v1.0.3'

# Extracts $url into $dest, then verifies a file named $exeName exists somewhere
# underneath (archive layouts differ between projects) and reports where.
function Get-Archive($url, $dest, $exeName) {
    $found = if (Test-Path $dest) { Get-ChildItem -Recurse -Filter $exeName $dest } else { $null }
    if ($found -and -not $Force) {
        Write-Host "  skip (present): $($found[0].FullName)"
        return
    }
    Write-Host "  downloading $url"
    $zip = Join-Path $tools 'dl.zip'
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Expand-Archive -Path $zip -DestinationPath $dest -Force
    Remove-Item $zip -Force
    $found = Get-ChildItem -Recurse -Filter $exeName $dest
    if (-not $found) { throw "no $exeName found under $dest after extracting $url" }
    Write-Host "  -> $($found[0].FullName)"
}

function Get-File($url, $path) {
    if ((Test-Path $path) -and -not $Force) { Write-Host "  skip (present): $path"; return }
    New-Item -ItemType Directory -Force -Path (Split-Path $path) | Out-Null
    Write-Host "  downloading $url"
    Invoke-WebRequest -Uri $url -OutFile $path -UseBasicParsing
}

New-Item -ItemType Directory -Force -Path $tools | Out-Null

Write-Host "[1/5] RGBDS $RGBDS_VER"
Get-Archive "https://github.com/gbdev/rgbds/releases/download/$RGBDS_VER/rgbds-win64.zip" `
            (Join-Path $tools 'rgbds') 'rgbasm.exe'

Write-Host "[2/5] SameBoy $SAMEBOY_VER"
Get-Archive "https://github.com/LIJI32/SameBoy/releases/download/$SAMEBOY_VER/sameboy_winsdl_$SAMEBOY_VER.zip" `
            (Join-Path $tools 'sameboy') 'sameboy.exe'

Write-Host "[3/5] hardware.inc (gbdev)"
Get-File 'https://raw.githubusercontent.com/gbdev/hardware.inc/master/hardware.inc' `
         (Join-Path $root 'src\hardware.inc')

Write-Host "[4/5] font8x8 (Daniel Hepper, public domain)"
Get-File 'https://raw.githubusercontent.com/dhepper/font8x8/master/font8x8_basic.h' `
         (Join-Path $tools 'font8x8_basic.h')

Write-Host "[5/6] TinyStories-260K checkpoint + tokenizer"
$hf = 'https://huggingface.co/karpathy/tinyllamas/resolve/main/stories260K'
Get-File "$hf/stories260K.bin" (Join-Path $root 'models\stories260K.bin')
Get-File "$hf/tok512.bin"      (Join-Path $root 'models\tok512.bin')

Write-Host "[6/6] Python venv"
$venv = Join-Path $root '.venv'
$py   = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $py)) { & python -m venv $venv }
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r (Join-Path $root 'requirements.txt')

Write-Host ''
& (Join-Path $tools 'rgbds\bin\rgbasm.exe') --version
& $py -c "import numpy, importlib.metadata as m; print('pyboy', m.version('pyboy'), '| numpy', numpy.__version__)"
Write-Host 'bootstrap OK'
