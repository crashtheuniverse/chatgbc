"""Where do the cycles go now? Stub one component at a time and re-measure.

The output turns to nonsense; the timing stays valid. Measured at token 70, past
saturation for the 32-slot window.
"""
import re, subprocess, sys
from pathlib import Path

ROOT = Path(r"C:\crashcode\chatgbc_x")
sys.path.insert(0, str(ROOT / "py"))
FWD, ATT = ROOT / "src" / "forward.asm", ROOT / "src" / "attention.asm"
ORIG = {p: p.read_text(encoding="utf-8") for p in (FWD, ATT)}
STEPS = 70


def build_measure(label):
    r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", f"cd '{ROOT}'; .\\build.ps1 -Quiet -Lab"],
                       capture_output=True, text=True)
    if "built" not in r.stdout:
        print(r.stdout[-800:], r.stderr[-800:]); raise SystemExit(f"build failed: {label}")
    from harness import Rom
    rom = Rom(lab=True)
    rom.lab_run(steps=STEPS)
    c = rom.read_u32("wTokCycles")
    rom.close()
    return c


def stub(path, pattern, count=None):
    """Replace `call X` with `nop` for the matching call sites."""
    text = ORIG[path]
    hits = [0]
    def sub(m):
        hits[0] += 1
        if count is None or hits[0] <= count:
            return "    nop  ; stubbed"
        return m.group(0)
    path.write_text(re.sub(pattern, sub, text), encoding="utf-8")


def main():
    results = {}
    try:
        results["(full)"] = build_measure("full")
        cases = [
            ("attn: scores",     ATT, r"    call Attn_Scores"),
            ("attn: softmax",    ATT, r"    call Attn_Softmax"),
            ("attn: weighted",   ATT, r"    call Attn_Weighted"),
            ("rmsnorm",          FWD, r"    call RmsNorm"),
            ("rope",             FWD, r"    call Rope"),
            ("matvecs (layers)", FWD, r"    call Matvec_Run\b"),
            ("classifier",       FWD, r"    call Matvec_RunCls(Accum)?"),
            ("residual adds",    FWD, r"    call AddSaturating"),
            ("swiglu",           FWD, r"    call SiluMul"),
        ]
        for label, path, pat in cases:
            stub(path, pat)
            results[label] = build_measure(label)
            path.write_text(ORIG[path], encoding="utf-8")
    finally:
        for p, t in ORIG.items():
            p.write_text(t, encoding="utf-8")

    full = results["(full)"]
    print(f"\n  token {STEPS}, window 32, full = {full:,} cycles\n")
    print(f"  {'component':<20}{'cycles':>12}{'share':>9}")
    acc = 0
    for k, v in sorted(results.items(), key=lambda kv: kv[1]):
        if k == "(full)":
            continue
        d = full - v
        acc += d
        print(f"  {k:<20}{d:>12,}{d / full * 100:>8.1f}%")
    print(f"  {'accounted for':<20}{acc:>12,}{acc / full * 100:>8.1f}%")
    print(f"  {'everything else':<20}{full - acc:>12,}{(full - acc) / full * 100:>8.1f}%")


if __name__ == "__main__":
    main()
