# Making ChatGBC

A transformer on a Game Boy Color, in SM83 assembly. Here is how it was built,
what the measurements said, and what I threw away.

---

## Why a Game Boy

Not nostalgia. Loop latency.

Every question worth asking about small models is bottlenecked by how fast you
can ask it. Train a real model and you wait hours. Prepare the data and you wait
days. That buys a few experiments a week. At that price you stop asking
speculative questions.

Here a question costs **fifty-four seconds**. Assemble, link, boot the ROM
headless, generate 96 tokens, check 29 assertions. On a laptop.

The constraints are the instrument, not the price of it:

- A 260K model runs headless far faster than real time. A full generation is a
  unit test, not a job.
- Assembly makes every cycle attributable to a line. Stub a kernel, re-measure,
  and you have its exact share.
- The bit-exact twin makes every answer definite. Identical, or not.
- The ROM times itself, so the number survives leaving the emulator.

Seventeen experiments are in `LOG.md`. Five are failures I kept. You only keep
failures when being wrong is cheap.

The Game Boy is not the point. It is a lab small enough to run the loop at full
speed.

## The number that set the target

A GBC in double speed gives 2,097,152 M-cycles a second. This model costs about
259,000 multiply-accumulates a token.

[gbc-transformer](https://github.com/maddiedreese/gbc-transformer) got here
first, in GBDK C, and set both the model and the target. It runs at 169 s/token.
That works out to **676 cycles per MAC**. A hand-written int8 MAC on this chip
should cost about twenty.

That gap is the whole project. And it forced a conclusion I did not expect: the
assembly was never needed to reach interactive speed. It was needed to create
headroom, and headroom is spent on quality.

Storage never mattered. MBC5 gives 8 MB and the model is a few hundred KB.
Compute was the only budget. Nearly every trick below trades ROM for cycles.

## The multiply is a lookup

The SM83 has no multiplier. Shift-add costs about 3,200 cycles per input.

But weights are 4-bit. Sixteen possible values. An activation is one byte, so
256 possible activations. Every product the model can ever need fits in **8 KB
of ROM per matrix**.

So they are all precomputed. At runtime the kernel copies 32 bytes into HRAM,
and after that multiplying is `ldh a, [c]`. 3,200 cycles become 200.

A C compiler will not find this. The loop wants to be a table lookup indexed by
a register that happens to be the low byte of a hardware address. There is no
way to say that in C.

The inner loop does four outputs at a time, so the loop counter costs one cycle
per MAC instead of four.

## Everything else is a shift

No division in the forward pass. No floating point after export.

Quantization exponents are calibrated offline and rounded to powers of two, so
every rescale is an arithmetic shift. Weight scales are per-output-row, from
4-bit Lloyd–Max codebooks. `rsqrt`, `exp`, `sigmoid` and reciprocal are tables.

The accumulator started at 24 bits. The instinct is to make it carry-aware and
squeeze 65K out of 16. The cheaper move was the opposite: **shrink the
products.** The exported tables are quarter-scaled, and at that scale the sum
provably stays inside signed 16 bits. That deleted a byte from the innermost
loop. **1.18x**, from a change in the exporter and none in the kernel.

## The ring, and infinite context

This one was mine, and it is the part I like best.

The first working ROM stopped at 64 tokens. The KV cache had 64 slots and
position 64 had nowhere to go. The intuition was that if the cache can be
indexed, it can be written back into — you keep the last 64 entries and wrap the
lookup, rather than growing anything.

**The cache slot for position `p` is `p mod 64`. RoPE keeps rotating by the
absolute `p`.**

Rotation is where a token *is*. Storage is where it *fits*. Those had been the
same number by accident. Separating them costs one mask instead of a bounds
check.

Position 64 overwrites slot 0. Nothing else changes. The model attends to the
last 64 positions, forever, and never learns anything wrapped. 64 slots is
exactly one WRAM bank per layer, so the wrap is free in addressing too: the slot
index *is* the low bits of the pointer.

Generation stopped being capped. The window became a knob instead of a wall.

## The twin is the reason any of it worked

Not a technique. A contract.

`py/reference.py` is the model in fp32. `py/quant.py` is **bit-exact with the
assembly** — same quantization, rounding, saturation, order, widths. Not close.
Identical.

Every test boots the ROM headless and asserts the same token sequence. So no bug
was ever "why does this look wrong", which is unanswerable. It was "at which
layer do the two stop agreeing", which is a bisection.

Timing is held to the same standard. The ROM measures itself with the hardware
timer, so every number here is a property of the machine.

## What the measurements said

Costs come from stubbing kernels one at a time and re-measuring. The output turns
to nonsense; the timing stays valid.

On the first token: matvec 48%, generic multiplies 12%, plumbing 40%. MACs are
less than half. Plumbing scales with *inputs + outputs*; MACs scale with
*inputs × outputs*. So:

> **Fewer, larger matvecs beat more, smaller ones.** Wide and shallow costs less
> per parameter than narrow and deep, because requantization is charged per row.

That inverts the usual minimize-parameters instinct. It is the most useful thing
the project produced.

**But read those shares with their caveat**, because they nearly shipped as a
lie. They were measured on the *first* token, which attends one cached position.
Attention is O(context). Once the 64-position window fills, attention is roughly
65% of a token and those proportions collapse.

I only found that by putting a live cycle counter on screen. Every published
figure had been the cheapest token the model can produce. The honest average
over 96 tokens is 21,121,834 cycles — 10.1 s/token, not 4.6. Cross-checked
against frame count to within 0.5%.

The instrument was fine. It was pointed at one token out of ninety-six.

## What I threw away

**Sub-4-bit weights.** The T-MAC-style group lookup is a real lever, worth about
4x, but it needs three levels or fewer. Teacher-forced top-1 against fp32:

| scheme | top-1 |
|---|---|
| 4-bit, 16 levels | **75.8%** |
| 3-bit | 52.9% |
| 2-bit | 12.9% |
| ternary | 2.9% |

It falls off a cliff. 3-bit already writes *"a boat named Tediaby"*. Four bits is
the floor for post-training quantization here. The caveat matters: ternary works
when a model is *trained* that way. This refutes it as a post-hoc transform, not
as an architecture.

**A shorter attention window.** Going from 64 positions to 8 saves 6% and costs
4.6 points. 16, 32 and 64 sit inside the noise. Window size should be chosen for
memory layout, not speed — which argues for 64, one WRAM bank per layer.

**Running code from HRAM.** On a GBA, copying a hot routine into IWRAM is a real
speedup: 32-bit bus, no wait states. On a Game Boy every region answers in one
M-cycle. Measured rather than assumed — the same loop from ROM and from HRAM
differed by one profiler tick, and the delta flipped sign when the work
quadrupled. HRAM buys shorter instructions, not faster memory.

## Four bugs worth keeping

**The stack was in banked WRAM.** Attention switches `SVBK` per layer, which
yanked the stack out from under every `call`.

**`add a, a` on a 16-bit table index.** Doubling an index in `a` drops bit 8.
`tbl_recip[128]` read `tbl_recip[0]`, so the reciprocal was zero, so attention
output was zero, so the model emitted plausible rubbish. Same mistake in three
lookups.

**The emulator was too kind.** Everything passed under PyBoy and produced
nonsense on SameBoy. PyBoy powers up with RAM zeroed; hardware does not. Now the
ROM clears all eight WRAM banks, the matvec has explicit zero and accumulate
entry points instead of a flag, and a test scribbles over RAM before the CPU
starts.

**The tokenizer silently did nothing.** It looked characters up as byte-fallback
ids, whose pieces are literal strings like `<0x4F>`. Nothing in the merge table
matches that, so BPE ran, found no merges, terminated correctly, and accomplished
nothing. Every test passed. The output was fine — from a worse tokenization.

---

*ChatGBC v0.1 — 21,121,834 M-cycles per token over a 96-token run, measured by
the cartridge itself.*
