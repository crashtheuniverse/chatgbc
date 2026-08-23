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

Here a question costs **twenty-five seconds**. Assemble, link, boot the ROM
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

## Everything else is a shift

No division in the forward pass. No floating point after export.

Quantization exponents are calibrated offline and rounded to powers of two, so
every rescale is an arithmetic shift. Weight scales are per-output-row, from
4-bit Lloyd–Max codebooks. `rsqrt`, `exp`, `sigmoid` and reciprocal are tables.

That is also what makes the rescale routine worth the attention it gets below:
if every requantization is a shift, the shift routine is on every hot path in
the model.

## Making it fast, in order

Every step bit-exact against the twin. These are first-token figures — see the
caveat further down.

| step | cycles/token | |
|---|---|---|
| the first version that generated text | 20,243,136 | |
| precomputed product tables | 13,835,520 | 1.46x |
| unrolled inner loop, four outputs | 12,993,984 | 1.065x |
| quarter-scaled products, 16-bit accumulators | 11,007,296 | 1.18x |
| byte-stepping the requant shift | 10,266,240 | 6.7% |
| shared scratch into HRAM | 9,831,424 | 4.4% |
| `swap` for the 4-bit step | 9,658,688 | 1.8% |

**2.10x overall.**

Those stop at the first token, which is where the measurement error below
was hiding. Steady state - a full 64-position window, which is what a real
passage costs - went **26,905,280 → 22,781,312** on top of that, by
rewriting attention:

| step | steady state | |
|---|---|---|
| after the shift and HRAM work | 26,905,280 | |
| quarter squares in the dot product | 24,478,592 | 9.0% |
| the weighted sum's loops the right way round | 23,304,384 | 4.8% |
| the softmax maximum staged once | 22,781,312 | 2.2% |
| 8-bit classifier (spent, not saved) | 23,326,656 | −2.4% |

The last row is a purchase rather than a saving: **+6.6 points of top-1
agreement for 2.4% more cycles**, which is what the headroom was for.

**Unrolling.** Four outputs per iteration drops the loop counter from 4 cycles
per MAC to 1. Every output count in the model — 32, 64, 172, 512 — is a multiple
of four, which also let the block chunking go entirely. The kernel got shorter as
well as faster.

**16-bit accumulators, rejected and then taken.** The accumulator started at 24
bits, three bytes touched on every MAC. The obvious fix is to make it
carry-aware and squeeze 65K out of 16. That attempt died on measurement. I checked the true accumulator range across four prompts: five of
eight matrices peak past int16, the worst at 41,534 against a 32,767 limit. A
wrapped accumulator flips sign rather than clamping, which is worse than the
saturation it replaces.

So I got them the other way round: shrink the **products**, not the accumulator.
The exported tables are quarter-scaled, and at that scale the sum provably stays
inside signed 16 bits for every matrix. A byte left the innermost loop and the
bias correction left requantization — from a change in the exporter and none in
the kernel. Estimating cycles is cheap. Estimating *ranges* is where intuition
fails.

**The requant shift stopped being a loop of single-bit shifts.** It rescales the
shared 32-bit scratch, and its counts are calibration data in the 13-16 range. A
shift of eight is a byte move. A shift of four is a `swap` — an SM83 instruction
the Z80 never had, which exchanges a byte's two halves in one go.

So it became a cascade of three step sizes: byte, nibble, bit. Each threshold is
one higher than the step it admits, so at least one bit always leaves the value
singly — the carry it strands is the rounding bit that round-half-up reads
afterwards. Peeling bytes cost ~30 cycles where the bit loop cost ~350.

Worth separating two things that look alike. Where a shift count is known at
assembly time, nothing needed fixing: `REPT 5 / add hl, hl` is an assembler
macro, not a runtime loop, and already emits five straight-line instructions.
`Requant_Shift` is the one place the count genuinely varies.

**HRAM is not faster memory, it is shorter instructions.** `ldh a, [n]` is two
bytes and 3 M-cycles where `ld a, [nn]` is three and 4; `ldh a, [c]` is one byte
and 2, which is what the matvec inner loop rides on. HRAM was holding only the
product table — 32 of its 127 bytes. Moving the shared 32-bit scratch there made
117 accesses a cycle cheaper each.

The ROM clears WRAM at boot and not HRAM, so the cold-boot test had to start
dirtying HRAM as well. Otherwise moving a variable there quietly escapes the test
that exists to catch reading before writing.

## Two more passes, and where they came from

v0.1 shipped at 23,326,656 cycles a token in steady state — 11.1 seconds, which
is a long time to watch a word appear. Two more rounds, both measured the same
way:

| | steady state | 96-token average |
|---|---|---|
| v0.1 | 23,326,656 | 18,951,201 |
| v0.2 | 13,896,256 | 13,724,256 |
| v0.3 | 12,973,824 | 12,794,099 |

**1.80x in steady state**, on top of the 2.10x that got there — and the number
that matters to a reader waiting for text, 2.4 seconds a character.

Most of v0.2 is one idea applied where it had not been: the product table works
for *any* loop with an invariant operand, not only matvec. Attention's score
loop had the dimension innermost, so nothing was invariant; turning it inside
out makes `q[d]` constant across positions and the multiply becomes a lookup
again. The weighted sum got the same treatment in the other direction.

v0.3 is smaller and less glamorous. The generic multiply was costing about 290
cycles for a signed 8-by-16, of which only ~92 was the actual shift-add loop —
the rest was negating operands into memory, writing them back, reading them
straight out again through a second entry point, and then negating the 32-bit
*result* in memory through another call. Operands in registers, sign on the
stack, negate before storing: the arithmetic did not change at all. Then the
window came down from 32 to 24, which is where the section below ends up.

One thing deliberately *not* taken: an inlining pass. Calls were measured at
about ten cycles each, roughly 28,000 a token — 2.0% if every call in the model
were inlined. That is not worth what it would do to the code.

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
exactly one WRAM bank per layer, so the wrap was free in addressing too: the slot
index *is* the low bits of the pointer.

Generation stopped being capped. The window became a knob instead of a wall —
and later, when there was a reason to turn it, the free mask turned out to be
the thing holding it shut. More on that below.

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

**A shorter attention window — thrown away, then taken back.** The first
measurement said 8 positions cost 4.6 points of top-1 while 16, 32 and 64 sat
inside the noise, so the window looked like a memory-layout decision rather than
a speed one. Two things were wrong with that. The evaluation was scoring a
64-position window against 48 generated tokens, so it never truncated anything
and was flattering the largest setting for free. And top-1 is teacher-forced:
fp32's correct history is handed back at every position, so the model never
lives with its own mistakes and cannot be seen to accumulate them.

Cross-entropy on fp32's own continuations does see it, and it is monotonic:
1.869 / 1.793 / 1.706 / 1.672 bits per token at 8 / 16 / 24 / 32. The steps are
0.076, 0.087, **0.034** — a clear knee at 24, which is where the window now
sits. It also prices the window against weight width for the first time: going
24 to 32 buys 0.034 bits for ~7% of a token, while 4-bit to 8-bit buys 0.077 for
~27%. **Context is worth about 1.7x more per cycle than precision here** — 4-bit
at window 32 scores better than 8-bit at window 16.

The awkward part is that 24 is not a power of two, so the ring wrap stops being
one `and`. Repeated subtraction is at most ten iterations, about seventy cycles,
five times a token, against twelve million. The mask was never worth the
constraint it imposed; it just looked free because nothing had asked to move.

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

## How this was made

Worth saying plainly, because the code is unusually clean for a solo project and
someone will ask.

I did not type this assembly. I directed it, and I read it — which is most of
why it is in assembly at all. Assembly is legible in a way I can argue with: I
can look at a loop and know what it costs.

The parts that were mine are the ones that decided the shape of it. Choosing a
small model and an emulator so the loop would be fast. Insisting on the bit-exact
twin as a contract. The ring buffer, and with it unbounded context. Asking
whether a 16-bit accumulator could be made to work, which it could, though not
the way I first suggested. Asking why a shift was a loop, and how HRAM was being
used — both of which turned into real cycles. Deciding to ship before touching
the model.

And several bugs came from sitting down and reading it: a black block from a
stranded palette attribute, a keyboard with no space key, a headline cycle count
that turned out to be the cheapest token in the run. None of those had a failing
test. All of them had a person looking at the thing.

`DECISIONS.md` has the rest.

---

*ChatGBC v0.3 — 12,794,099 M-cycles per token over a 96-token run, measured by
the cartridge itself.*
