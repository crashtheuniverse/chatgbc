# Rei's export environment, for build.ps1 -Rei and test.ps1 (dot-sourced).
#
# The checkpoint is models/rei.bin. Its tokenizer follows its vocabulary: a
# 1,024-piece Rei is trained on models/tok_rei1024.bin, the release tokenizer,
# which carries the name opcodes <SN> and <N> and the header <NK> (src/name.asm); a 512-piece one
# (v1.0.0's) on models/tok_rei.bin. py/export5.py refuses a pair that differs
# in size.
#
# REI_PIP5 and REI_TOKENIZER override either, for trying a checkpoint without
# copying it over models/rei.bin:
#   $env:REI_PIP5 = 'C:\somewhere\candidate.bin'; .\test.ps1
function Get-ReiEnv([string]$root) {
    $ckpt = if ($env:REI_PIP5) { $env:REI_PIP5 } else { Join-Path $root 'models/rei.bin' }
    $tok = $env:REI_TOKENIZER
    if (-not $tok) {
        # PIP5 header: magic, version, dim, hidden, layers, vocab (u16 each)
        $head = New-Object byte[] 14
        $f = [IO.File]::OpenRead($ckpt)
        try { [void]$f.Read($head, 0, 14) } finally { $f.Close() }
        $vocab = [BitConverter]::ToUInt16($head, 12)
        $name = if ($vocab -eq 1024) { 'tok_rei1024.bin' } else { 'tok_rei.bin' }
        $tok = Join-Path $root "models/$name"
    }
    return @{
        CHATGBC_CHAT      = '1'
        PIP5              = $ckpt
        CHATGBC_TOKENIZER = $tok
    }
}
