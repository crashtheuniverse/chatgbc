# Making ChatGBC

The first draft of this document was eight times longer. Nobody finished it,
me included. Here is the espresso.

## Why a Game Boy

Not nostalgia. **Loop latency.** Train a real model, wait hours. Here a
question costs twenty-five seconds: assemble, boot headless, generate, check
29 assertions. When being wrong costs half a minute, you can afford to be
wrong all day — and that is called research.

The Game Boy is not the point. It is a lab small enough that I can look at
every bit with my own eyes. Like Neo, except the Matrix is 32KB, and I can
actually read it.

## The number that started it

Somebody had already run this model on a GBC, in C: 169 seconds per token,
which is ~676 cycles per multiply-accumulate. A hand-written MAC on this chip
should cost about 20. That factor of 30 was the entire project. No faith
required — just arithmetic.

## The tricks

**There is no multiplier.** The SM83 cannot multiply. But weights are 4-bit:
sixteen possible values, 256 possible activations, so every product the model
will *ever* need fits in 8KB of ROM per matrix. Precompute all of them, and
"multiply" becomes one load instruction: 3,200 cycles become 200. Try
explaining that to a C compiler. There is no spoon.

**Everything else is a shift.** No division, no floats. Scales are powers of
two, so every rescale is a shift; rsqrt, exp and sigmoid are tables. ROM is
abundant (8MB!), cycles are misery (2MHz real). You always trade the fat
thing for the starving one.

**The ring.** My favourite, and mine. The cache slot for position `p` is
`p mod 24`, while RoPE keeps rotating by the *absolute* `p`. Where a token
**is** and where it **fits** had been the same number only by accident.
Separate them and generation never stops: the model attends to the last 24
positions forever, like a nonna who remembers only the last thing you said —
but with total conviction.

**Eight bits only where the error compounds.** `wk` and `wv` write the cache,
so their error is stored and re-read for 24 positions — the only error in the
model that compounds. 8-bit for just those two: three quarters of the whole
quality gain for an eighth of the cost. Top-1 went 75.7% → 78.1%.

**Refusing to repeat.** Greedy argmax is a fixed point, so every story ended
in *"They are very happy. They are very happy."* Sampling ruins the grammar —
a 260K model has no probability to waste. Instead the decoder skips any token
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
layer do the twins disagree", which is a bisection, not a séance.

## Thrown away

- **Sub-4-bit weights.** Post-hoc ternary scores 2.9% top-1 and writes
  *"a boat named Tediaby"*. Four bits is the floor — unless you *train*
  ternary, which is another story, for another version.
- **Code in HRAM.** On a Game Boy every memory region answers in one cycle.
  HRAM buys shorter instructions, not faster memory. Measured, not believed.
- **My first headline number.** Measured on the first token — the cheapest of
  all 96, before the attention window fills. The honest average was more than
  twice as slow. The instrument was fine; it was pointed at the wrong token.

## Two bugs worth a candle

The stack was in banked WRAM, and attention switches banks per layer — it
yanked the stack out from under every `call`. And the emulator powers RAM up
zeroed where real hardware does not: everything passed in the emulator and
spoke rubbish on silicon. Now the ROM scribbles over everything at boot, on
purpose.

## How this was made

I did not type this assembly. I directed it — AI wrote most of the lines, and
I read all of them, which is exactly why it is assembly: I can look at a loop
and know its price. Mine were the decisions that shaped it: the small model
so the loop stays fast, the bit-exact twin as a contract, the ring, the
16-bit accumulators, the observation that argmax needs no softmax. The
machine typed; a guy from Palermo asked *cui prodest?* at every line, and
ate an arancina every time the cycle count went down.

It went down a lot.

---

*ChatGBC v0.3 — 12,918,757 M-cycles per token over a 96-token run, measured
by the cartridge itself.*
