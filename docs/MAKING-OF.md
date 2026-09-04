# Making ChatGBC

> **v0.4 note.** This page describes the v0.3 model - karpathy's stories260K transformer, 4-bit tables, a 24-token attention window. v0.4 runs a different model trained here: a minGRU core, four ternary experts per layer, a block-sum kernel. The README's *What changed since v0.3* has the short version; this page will follow.

## Why a Game Boy

**Loop latency.** Train a real model, wait hours. Here a
question costs twenty-five seconds: assemble, boot headless, generate, check
29 assertions. When being wrong costs half a minute, you can afford to be
wrong all day and keep researching.

The Game Boy is not the point. It is a lab small enough that I can look at
every bit with my own eyes. I feel like a mini Neo, just my Matrix is 32KB. 

## The number that started it

Somebody had already run this model on a GBC, in C: 169 seconds per token,
which is ~676 cycles per multiply-accumulate. A hand-written MAC on this chip
should cost about 20. 

## The tricks

**There is no multiplier.** The SM83 cannot multiply. But weights are 4-bit:
sixteen possible values, 256 possible activations, so every product the model
will *ever* need fits in 8KB of ROM per matrix. Precompute all of them, and
"multiply" becomes one load instruction: 3,200 cycles become 200. 

**Everything else is a shift.** No division, no floats. Scales are powers of
two, so every rescale is a shift; rsqrt, exp and sigmoid are tables. ROM is
abundant (8MB!), cycles are misery (2MHz real).

**The ring.** My favourite original thinking. The cache slot for position `p` is
`p mod 24`, while RoPE keeps rotating by the *absolute* `p`. Where a token
**is** and where it **fits** had been the same number only by accident.
Separate them and generation never stops: the model attends to the last 24
positions forever. 
This is what reading assembly mentally simplifies for you.

**Eight bits only where the error compounds.** `wk` and `wv` write the cache,
so their error is stored and re-read for 24 positions — the only error in the
model that compounds. 8-bit for just those two: three quarters of the whole
quality gain for an eighth of the cost. Top-1 went 75.7% → 78.1%.

**Refusing to repeat.** Greedy argmax is a fixed point, so every story ended
in *"They are very happy. They are very happy."* Sampling ruins the grammar —
a 260K model has no probability to waste. _trick!!!_ : Instead the decoder skips any token
that would complete a 4-gram it already said: never loops, still
deterministic, 0.13% of a token. And since greedy needs no softmax and no
stored logits, the best token lives in a register pair — deleting the logit
array bought back 3.2% of every token.

## The ladder, measured

| | cycles/token, 96-token average |
|---|---|
| v0.1 | 18,951,201 |
| v0.2 — the lookup trick, applied everywhere it fit | 13,724,256 |
| **v0.3 shipped** | **12,918,757** |

Every step bit-exact against a Python twin of the assembly — same rounding,
same widths, identical tokens or the test fails. Every bug becomes "at which
layer do the twins disagree", which is a bisection.

The **twin IS** the secret weapon.

## Thrown away

- **Sub-4-bit weights.** Post-hoc ternary scores 2.9% top-1 and writes
  *"a boat named Tediaby"*. Four bits is the floor — unless you *train*
  ternary, which is another story, for another version.
- **Code in HRAM.** On a Game Boy every memory region answers in one cycle.
  HRAM buys shorter instructions, not faster memory.

## Notable Bugs

The stack was in banked WRAM, and attention switches banks per layer — it
yanked the stack out from under every `call`. And the emulator powers RAM up
zeroed where **real hardware does not**: everything passed in the emulator and
nonsense on HW. Now the ROM zeroes out at boot.

## How this was made

I did not type probably 98% of the assembly. 
I did just direction. AI wrote most of the lines, and
I read all of them, which is exactly why it is assembly: I can look at a loop
and know its price. 
_funny note:_ a column/row inverted loop. Fix it and code became even cleaner.

I treated it as I had a junior and decided on high level stuff: 
the small model so the loop stays fast, the bit-exact twin as a contract, the ring, the
16-bit accumulators, the observation that argmax needs no softmax. 

Experience gives you patterns. I wanted cycles to go down. 
They went down a lot.

---

*ChatGBC v0.3 — 12,918,757 M-cycles per token over a 96-token run, measured
by the cartridge itself.*