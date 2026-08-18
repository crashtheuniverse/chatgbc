# ChatGBC

A language model that runs on a Game Boy Color. Not an emulator on a phone
pretending to be a Game Boy — a 512 KB cartridge, an 8 MHz SM83, 32 KB of RAM,
and a transformer doing a full forward pass per token in **hand-written
assembly**.

![ChatGBC generating text](docs/chatgbc.gif)

*One frame per token, which plays back about 40x faster than the hardware. On
the handheld this is 96 tokens over eight minutes — roughly two seconds per
character.*

## What it does

You get an on-screen keyboard. You type a prompt. It generates, and keeps
generating — the text scrolls, and it does not stop at a context limit.

Everything happens on the device. There is no host, no companion app, no
network. The cartridge contains the tokenizer, the weights, and the entire
inference stack.

## Numbers

| | |
|---|---|
| Model | TinyStories-260K — 5 layers, dim 64, 8 heads / 4 KV heads, vocab 512 |
| Weights | 4-bit, Lloyd–Max codebooks, per-output-row scales |
| Arithmetic | int8 activations, signed 16-bit accumulators, no floating point |
| Speed | **10,266,240 M-cycles per token** = 4.9 s/token ≈ 2 s/character |
| Kernel | 19 M-cycles per multiply-accumulate in the inner loop |
| Context | unbounded output; 64-token attention window in a ring buffer |
| ROM | 512 KB, MBC5 |
| Language | SM83 assembly (RGBDS). No C, anywhere. |

Timing is measured **inside the ROM** using the hardware timer, not by the
emulator's wall clock, so the number above is what the hardware does.

For scale: the reference implementation that inspired this,
[gbc-transformer](https://github.com/maddiedreese/gbc-transformer), runs the
same model in GBDK C at 169 s/token. This is about **34x faster**, which is what
you get for writing the kernel yourself.

## Why it is fast

**The multiply is a table lookup.** The SM83 has no multiplier. With 4-bit
weights there are only sixteen possible weight values, so for every activation
byte there are only sixteen possible products — 4 KB of precomputed products per
matrix, sitting in ROM — 8 KB per matrix, all 256 of them. The kernel copies the
32-byte table for the current activation into HRAM, and from there the
"multiply" is `ldh a, [c]`: sixteen shift-add multiplies, about 3,200 cycles,
collapse into one 200-cycle copy. ROM is the one resource this project has in
abundance. Cycles are the scarce one.

**Every rescale is a shift.** Quantization exponents are calibrated offline and
rounded to powers of two, so nothing in the forward pass ever divides. Products
are exported pre-scaled by a quarter, which keeps every accumulator inside
signed 16 bits and drops a byte out of the innermost loop.

**Nothing transcendental is computed.** `rsqrt`, `exp`, `sigmoid` and reciprocal
are all tables.

## Why generation is unbounded

The KV cache is a ring. The cache slot for position `p` is `p mod 64`, while
RoPE keeps rotating by the **absolute** `p`.

That separation is the whole trick: rotation is a function of where a token
*is*, storage is a function of where it *fits*. Keeping them apart costs one
mask instead of a bounds check, and the model never learns that anything wrapped
— it simply attends to the last 64 positions, forever.

## Build it

Windows, PowerShell. Everything is fetched into the project; nothing touches
your PATH.

```powershell
.\bootstrap.ps1   # RGBDS, SameBoy, hardware.inc, a .venv with PyBoy
.\build.ps1       # -> build\chatgbc.gbc
.\test.ps1        # build, then the headless test suite
```

Then either drop `build\chatgbc.gbc` on a flashcart, or:

```powershell
.\tools\sameboy\sameboy.exe build\chatgbc.gbc
```

**Controls:** d-pad moves, `A` types, `B` deletes, `SELECT` flips case, `START`
generates. Press `START` again when it finishes to go back to the keyboard.

## How it is kept honest

There is a Python model in `py/` that is not a reference in the loose sense —
it is a **bit-exact integer twin**. It implements the same quantization, the same
rounding, the same saturation, in the same order. The test suite boots the ROM
headlessly in PyBoy and asserts the assembly produces the identical token
sequence, not a similar one.

That contract is what made the project tractable. Every bug became a question
with a definite answer: at which layer do the two stop agreeing?

```
py/reference.py   fp32 model, the ground truth
py/quant.py       the integer twin the assembly must match exactly
py/export.py      checkpoint -> 4-bit blobs, product tables, src/weights.asm
py/harness.py     boots the ROM in PyBoy, reads its WRAM back out
```

## Reading the source

One concept per file. `AGENTS.md` has the suggested order, but the short version:
`matvec.asm` is the kernel everything else is measured against, `state.asm` holds
the requantization, and `forward.asm` is the layer loop that ties it together.

- [`docs/MAKING-OF.md`](docs/MAKING-OF.md) — how it was built, and what was tried
  and thrown away
- [`docs/LOG.md`](docs/LOG.md) — every experiment with before/after cycle counts,
  including the ones that failed
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — decisions made after reading the code

## Credits

- [karpathy/tinyllamas](https://huggingface.co/karpathy/tinyllamas) —
  `stories260K`, the model being run
- [gbc-transformer](https://github.com/maddiedreese/gbc-transformer) — the
  reference point that set the target
- [dhepper/font8x8](https://github.com/dhepper/font8x8) — public-domain font
- [RGBDS](https://rgbds.gbdev.io), [gbdev hardware.inc](https://github.com/gbdev/hardware.inc),
  [PyBoy](https://github.com/Baekalfen/PyBoy), [SameBoy](https://sameboy.github.io)
