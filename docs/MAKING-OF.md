# Making ChatGBC

A transformer that runs on a Game Boy Color, written entirely in SM83 assembly.
This is how it was built, what the measurements said, and what got thrown away.

---

## The arithmetic came first

Before a line was written, one calculation decided the shape of everything else.

A Game Boy Color in double-speed mode runs at 2,097,152 M-cycles per second.
TinyStories-260K costs about 259,000 multiply-accumulates per token. If a token
should take a handful of seconds, the budget works out to a few dozen cycles per
MAC.

The reference point — [gbc-transformer](https://github.com/maddiedreese/gbc-transformer),
the same model in GBDK C — was spending **676 cycles per MAC**, and 169 seconds
per token. A tight int8 MAC on an SM83 with a per-input product table should be
around twenty.

That gap is the entire project. The conclusion it forced was unusual and worth
stating plainly: **the assembly was never needed to reach interactive speed.**
It was needed to create headroom, and headroom is spent on model quality, not on
being fast for its own sake. Framing it that way up front stopped a lot of
premature optimization later.

Storage never mattered. MBC5 gives 8 MB of ROM and the model is a few hundred
kilobytes. Compute was the only real budget, and knowing that changed which
tricks were worth reaching for — nearly every one below trades ROM for cycles.

## Why a Game Boy at all

The honest answer is not nostalgia.

Every interesting question about making a model smaller or faster is bottlenecked
by how fast you can ask it. Train a real model and you wait hours; prepare the
data and you wait days. That buys a handful of experiments a week, and at that
rate you stop asking speculative questions, because a speculative question that
costs a day is not worth asking.

Here, an idea becomes a measured, bit-exact answer in **fifty-four seconds** —
assemble, link, boot the ROM headlessly, generate ninety-six tokens, and check
twenty-nine assertions including exact token equality against the twin. On a
laptop. That is three to four orders of magnitude more experiments per day, and
it changes which questions get asked at all.

The constraints that look like limitations are precisely what make the loop fast:

- **A 260K model** runs headless at many times real time, so a full generation is
  a unit test rather than a job.
- **Assembly** means every cycle is attributable to a line. Stub a kernel,
  re-measure, and you have its exact share.
- **The bit-exact twin** makes every answer definite. Not "this looks better" —
  identical or not identical.
- **The ROM times itself** with the hardware timer, so the number is a property
  of the machine, not of whatever ran it.

Seventeen experiments are recorded in `docs/LOG.md`. Five of them are failures
kept on purpose: sub-4-bit quantization, ternary weights, shrinking the attention
window, executing from HRAM, and a couple of dead ends inside the kernel. You
only keep your failures when running them was cheap enough that being wrong costs
nothing.

The Game Boy is not the point. It is a laboratory small enough to run the whole
loop at full speed, and small enough that every part of it fits in one head.

## Why assembly, and not the obvious thing

The obvious thing is to compile llama2.c with GBDK and be done in an afternoon.
The reason not to is that a C compiler for the SM83 cannot express the trick that
matters. The inner loop of this model wants to be *a table lookup indexed by a
register that happens to be the low byte of an HRAM address*. There is no way to
say that in C, and the compiler will not find it.

Written by hand, that loop is 19 cycles per MAC. Compiled, it was 676.

## The one thing that made it tractable

Not a technique — a contract.

`py/reference.py` is the model in fp32. `py/quant.py` is a second implementation
that is **bit-exact with the assembly**: the same quantization, the same
rounding, the same saturation, in the same order, with the same intermediate
widths. Not "numerically close". Identical, byte for byte.

Every test boots the ROM headlessly in PyBoy and asserts the assembly produces
the same tokens as the twin. When something broke — and something broke
constantly — the question was never "why does this look wrong", which is
unanswerable. It was "at which layer do the two stop agreeing", which is a
bisection with a definite answer.

Timing is held to the same standard. The ROM measures itself with the hardware
timer (DIV/TIMA at 16 kHz, one tick per 64 M-cycles), so every number in this
document is a property of the machine, not of the emulator that happened to run
it. That mattered more than expected: an emulator's wall clock would have hidden
several real problems.

## Multiplication is a table lookup

The SM83 has no multiply instruction. Shift-add multiplication of an int8
activation by sixteen weights costs about 3,200 cycles per input.

But with 4-bit weights there are only sixteen possible weight values, so for a
given activation byte there are only sixteen possible products — and there are
only 256 possible activation bytes. Every product the kernel could ever need
fits in **8 KB per matrix**, computed at export time and sitting in ROM.

The kernel copies the 32-byte table for the current activation into HRAM — about
200 cycles — and after that, multiplying is `ldh a, [c]`. One byte of the weight
stream indexes straight into it.

The inner loop unrolls four outputs at a time, so `dec b` / `jr nz` costs one
cycle per MAC instead of four. Every output count in the model is a multiple of
four, which is luck, but the kind you take.

## Everything else is a shift

There is no division anywhere in the forward pass, and no floating point at any
point after export.

Quantization exponents are calibrated offline and **rounded to powers of two**,
so every rescale between tensors is an arithmetic shift. Weight scales are
per-output-row, with 4-bit Lloyd–Max codebooks fitted per matrix. `rsqrt`, `exp`,
`sigmoid` and reciprocal are tables — RMSNorm needs an inverse square root, which
the SM83 cannot do, so it looks one up.

The rescale routine turned out to be worth a second look much later; see
*byte-stepping*, below.

## Make the products smaller, not the accumulator wider

A dot product over 172 terms of int8 by int8 needs more than 16 bits, so the
accumulator started at 24 — three bytes, touched on every single MAC.

The instinct is to make the accumulator carry-aware and squeeze 65K out of 16
bits. The cheaper move was the opposite: **shrink the products.** The exported
product tables are quarter-scaled, and at that scale the running sum provably
stays inside signed 16 bits for every matrix in the model.

That deleted a byte from the innermost loop and removed the bias correction from
requantization: **1.18x**, for a change in the exporter and none in the kernel.

Attention scores kept 24 bits. A score is `q·k` over eight terms and reaches
129,032, so it needs the width regardless of how wide the matvec accumulator
happens to be — which is why the two are separate constants and not one shared
`ACC_BYTES`. Tying them together had already caused one memorable bug.

## The ring, or: why generation does not stop

The first working ROM could generate 64 tokens and then had to stop, because the
KV cache was 64 slots and position 64 had nowhere to go.

The fix is one line of arithmetic and it is the nicest idea in the project.

**The cache slot for position `p` is `p mod 64`. RoPE keeps rotating by the
absolute `p`.**

Rotation is a function of where a token *is*. Storage is a function of where it
*fits*. They had been the same number by accident, and separating them costs a
mask instead of a bounds check. Position 64 overwrites slot 0 and carries a
rotation that has never collided with anything; from the model's point of view it
simply attends to the last 64 positions, forever.

Because 64 slots is exactly one WRAM bank per layer, the wrap is also free in
addressing terms — the slot index *is* the low bits of the pointer.

Steady-state cost measured at **2.4% slower** than the bounded version, in
exchange for unlimited output. The window stopped being a wall and became a
knob.

## The tokenizer runs on the handheld too

Early ROMs shipped a hardcoded token sequence, which is cheating in a way that
matters: a device you cannot type into is a demo, not a product.

So the BPE encoder is in assembly. It scans the vocabulary for each character,
then repeatedly finds the adjacent pair with the lowest merge rank and merges it,
exactly as the Python tokenizer does. The tables are one merged blob in a
switchable bank.

It also contains the single most humbling bug of the project. The encoder looked
up each input character as `byte + 3` — the byte-fallback token id. Those ids
exist for bytes the vocabulary has no piece for, and their "piece" is a literal
six-character string like `<0x4F>`. Nothing in the merge table ever matches that,
so BPE ran, found no merges, terminated correctly, and silently did nothing.
Every test passed. The output was fine, just from a worse tokenization.
Characters have to be looked up as pieces first.

## What changed after reading the code

Several things only surfaced when the author sat down and read what had been
written. They are recorded in `DECISIONS.md`; three are worth repeating here
because each is a different kind of miss.

**A missing space key.** The on-screen keyboard had `a..z`, a full stop and eight
punctuation marks — and no space. The default prompt is a sentence, so every
screenshot looked right, but anything typed by hand could only ever be one word.
No test could have caught this, because no test knew what a keyboard is for.

**A black block on screen.** The keyboard cursor is a CGB background attribute:
palette 1 set on exactly one cell in VRAM bank 1, so moving it is two byte writes
and no tilemap change at all. But *exactly one* is an invariant, and redrawing
the screen reset the variable tracking that cell without clearing the cell it
named. An inverted cell survived into the generation screen and painted a black
block over the text. There is now a test asserting nothing is inverted once
generation begins.

**A loop where an instruction would do.** The observation was that a shift used
as a multiply should be one instruction, not a loop. Half the answer was that it
already is — `REPT 5 / add hl, hl` is an assembler macro, not a runtime loop, and
assembles to five literal instructions.

But the other half was a real finding. `Requant_Shift` genuinely needs a runtime
loop, since its count is per-tensor calibration data. What it did *not* need was
to shift one bit at a time when the counts are 13 to 16 — **a shift of eight is a
byte move.** Peeling whole bytes off first cost about 30 cycles where the bit
loop cost about 350: **6.7% off every token**, bit-exact, from a question asked
while reading.

The peel stops at nine rather than eight, which is the kind of detail that only
looks arbitrary until it bites. The last bit to leave the value has to go one bit
at a time, because the carry it strands is the rounding bit that round-half-up
reads afterwards.

## Ideas that were tried and thrown away

The log keeps failures because they are the expensive part.

**Sub-4-bit weights: refuted.** The T-MAC-style group lookup is a genuinely
strong lever — precompute the sum for every sign pattern of a group of
activations and G MACs collapse into one lookup, worth about 4x — but it needs
three levels or fewer to keep the table small. Measuring teacher-forced top-1
agreement as the codebook shrinks:

| scheme | top-1 vs fp32 |
|---|---|
| 4-bit, 16 levels | **75.8%** |
| 3-bit, 8 levels | 52.9% |
| 2-bit, 4 levels | 12.9% |
| ternary | 2.9% |

Quality falls off a cliff. Three-bit already emits *"a boat named Tediaby"*.
**Four bits is the floor for post-training quantization of this checkpoint.** The
caveat matters: BitNet-style ternary works when a model is *trained* that way.
This refutes ternary as a post-hoc transform, not as an architecture.

**A shorter attention window: not worth it.** Attention is only 4.9% of a token
at this scale. Going from a 64-position window to 8 saves 6% of cycles and costs
4.6 points of top-1; 16, 32 and 64 sit inside the measurement's noise. Window
size should be chosen for memory layout, not for speed — which argues for 64,
since that is exactly one WRAM bank per layer.

Worth carrying: attention being O(T) is real but does not bite here. It only
reaches half a token at around 622 positions, past RoPE's training limit. And the
quality curve is flat mostly because TinyStories is locally coherent — that will
not hold for a model meant to hold a conversation.

## What the cost model actually says

Obtained by stubbing kernels one at a time and re-measuring. The output becomes
nonsense but the timing stays valid:

| component | share of a token |
|---|---|
| matvec inner loop | **48%** |
| generic 8×16 multiply (rmsnorm, rope, silu, attention) | 12% |
| requant, table copies, attention bookkeeping, plumbing | **40%** |

The plan had assumed MACs dominate. They are less than half.

Plumbing scales with *inputs + outputs*. MACs scale with *inputs × outputs*. So:

> **Fewer, larger matvecs beat more, smaller ones.** A wider model with fewer
> layers costs less per parameter than a narrow deep one, because per-element
> requantization and pointer traffic are charged per row, not per MAC.

That inverts the usual minimize-parameters instinct, and it is the most useful
thing the measurements produced.

## Four bugs worth remembering

**The stack was in banked WRAM.** It sat at `$DF00` in bank 1. Attention
switches `SVBK` per layer, which yanked the stack out from under every `call`.
The stack must live in WRAM0, which is always mapped.

**`add a, a` on a 16-bit table index.** Doubling an index in `a` to address a
two-byte table drops bit 8. `tbl_recip[128]` quietly read `tbl_recip[0]`, so the
reciprocal returned zero, so attention output was all zeros, so the model emitted
plausible-looking rubbish. The fix is `ld l, a / ld h, 0 / add hl, hl` — the same
mistake was present in three separate lookups.

**The emulator was too kind.** Everything passed under PyBoy and produced
nonsense on SameBoy. PyBoy powers up with RAM at zero; real hardware does not.
A flag that was read before it was written worked perfectly on one and not the
other. The structural fixes were to zero all eight WRAM banks at boot, split the
matvec into explicit *zero* and *accumulate* entry points rather than relying on
a flag, and add a test that scribbles a non-zero pattern over WRAM before the
CPU starts.

**The console decoded to `round(banner / 16)`.** Which is a strange enough
symptom to be a gift. `Requant_Shift` uses `b` as scratch and `Requant_Sat8` uses
`b` and `c`; two callers were holding a loop counter in `b` across those calls.
The counter was clobbered, the loop ran forever, walked all of WRAM, and shifted
every byte right by four — including the text on screen. Both routines now
document which registers they destroy.

---

*ChatGBC v0.1 — 9,658,688 M-cycles per token, measured by the cartridge itself.*
