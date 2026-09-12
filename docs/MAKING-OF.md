# Making ChatGBC

> The first chapters describe v0.3 - karpathy's stories260K transformer, 4-bit tables, a 24-token attention window - as they were written. v0.4 replaced the model (the README's *What changed since v0.3* has the short version); v0.9 replaced the kernels under it, and its chapter is further down.

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

### The tricks, v0.9: ask every stage what it can output

v0.4 had made the multiply a table of 27 sums: three ternary weights times
three activations can only come to one of 27 values, so build them once and
look them up. v0.9 asked the same question of everything else on the token.
For each stage: what does it take in, and how many distinct values can it
put out? That number is the stage's codomain, and where it is small the
stage is a table; where the output is mostly one value, the work that makes
the other value is a skip. None of it changes an integer. The twin stayed
fixed and every kernel was rewritten to reproduce it.

**Turn the matvec round.** The 27-sum kernel walked the inputs and kept 64
or 176 accumulators in WRAM, then requantized them in a second pass. Build
all 22 tables of the input vector once instead - by derivation, each entry
one 16-bit add from an earlier one, 381 cycles a table - and then each
output row is a stream of 22 bytes, each byte already the low address of its
table entry. The weight *is* the index. The sum lives in `de` at 12 cycles a
lookup, the shift byte follows the codes, and the requant happens in
registers before the store: 302 + 8s cycles a row, no array, no zero pass,
no second pass. wz and wh read the same vector, so they share one build; the
router's rows ride on w1's tables and the argmax is taken before the chosen
expert's rows are swept. The classifier is the same shape with blocks of
four (81 sums) and nothing stored but the best and the runner-up: 226 cycles
for each of the 1,024 rows.

**Encode the sparsity where it is made.** ReLU² is 82% zeros on held-out
text, and the audit's first answer was to test blocks of three for zero at
w2 time. The better one: the loop that produces the activations knows which
came out nonzero, so it writes the list; w2's weights are stored per input
column as lists of the +1 outputs and the −1 outputs; and the kernel does
one 16-bit add or subtract per nonzero (activation, weight) pair. About
1,100 to 1,650 pairs a layer where the matrix has 11,264
multiply-accumulates. About 68K cycles a token for the three layers on the
8-token census (67,624) where the dense kernel took 344,696, and it is
exact because
integer addition commutes. A guard falls back to the dense kernel above
111 nonzero activations; the measured maximum is 88.

**Prove the saturation dead, then delete it.** The minGRU gate was the last
multiply on the cartridge, 446 cycles an element plus a sigmoid pass. Two
facts about the twin's line were checked over all 16,646,400 inputs: the
result equals `h + ((zg·(ht−h) + 128) >> 8)`, and it never leaves
`[min(h,ht), max(h,ht)]`. So the `sat8` can never fire and one byte of the
gated difference is the whole answer: a table indexed by the sigmoid value
and `ht−h`. Only 118 sigmoid values occur across the three layers, so 118
rows of 512 bytes, 60,416 bytes, and the sigmoid is never computed at all -
two side pages per layer map the raw logit byte to the row. 47 cycles an
element.

**Count the width of the result.** The norm has two rounding shifts and
both produce a value that fits in 16 bits, so a shift only needs the two
bytes above the rounding bit and the bit itself: peel whole bytes first,
then shift. That, the sum of squares in registers, and x·r as two nibble
tables built per norm halved every norm, about 23K from about 46K, with no
table in ROM.

**Store what the exporter already knows.** The embedding rows were
requantized to the stream's grid on every token; the exporter stores them
requantized and the embed is a copy, 13,368 cycles to 448. The layer-0
debug snapshots ran in the shipping ROM for nothing; they assemble only in
the lab build now. The residual add went to a 34-cycle page-form loop with
the overflow taken from the sign bits.

### How v0.9 was built

The audit came first: one analyst per stage reading the assembly and the
twin, then one adversary per stage recounting every cycle against the
instruction timings and running every exactness claim against the twin -
exhaustively where the domain allowed - then a ranking of what held. Then
each collapse was built in its own worktree by a builder, reviewed by an
adversary who re-ran the whole ladder (export, both builds, the golden run
byte for byte, the suite, the census, the linker map) and read the diff,
fixed once, and merged one at a time onto the release branch. The ladder
for every kernel, in order: the twin unchanged, the golden run strict, then
the census. A kernel that passed the first two and not the third was not
faster; a kernel that passed the third and not the first two was not
correct.

The merge order was the dependency order: the sparse w2 with its ReLU² page
and the output-major classifier (independent of everything); the gate
table; the norm; the output-major sweep for the four block matvecs; the
small exact ones last.

Three things from the build notes worth keeping. The census's
arithmetic is the thing to trust over anyone's count: the wh line reads
63,408 for 192 rows, and 302 + 8s at the mean shift the export reports
lands on it to the cycle, which is how you know the counts are honest. A path with no
witness is a path the next change breaks silently: the classifier's retry
path had been correct and untested, so the lab gained a planted-history
entry and the suite checks it at 0 to 9 rejects. And the tree's own
baseline is not the audit's baseline: every before and after was measured
on the same tree with the work stashed, so the untouched stages sit within
tens of cycles of themselves.

## The ladder, measured

| | cycles/token | s/token |
|---|---|---|
| v0.1 | 18,951,201 | 9.0 |
| v0.2 — the lookup trick, applied everywhere it fit | 13,724,256 | 6.5 |
| v0.3 shipped | 12,918,757 | 6.16 |
| v0.4.1 — a model trained for the machine | 2,259,829 | 1.08 |
| **v0.9 shipped** — the same model, the token audited | **963,792** | **0.46** |

v0.1 to v0.3 averaged over 96 tokens, v0.9 over 100 with the teletype
running, v0.4.1 with the teletype off (2,271,104 with it); all on the
cartridge's own DIV/TIMA counter.

Inside v0.9, the 8-token census as the collapses merged, on the tree the
release started from (2,164,704 staged cycles - the v0.4.1 weights with the
two integer-path fixes that also ship):

| after | census cycles/token | s/token |
|---|---|---|
| the sparse w2 and the output-major classifier | 1,660,528 | 0.79 |
| the gate table | 1,576,464 | 0.75 |
| the norm in registers | 1,413,232 | 0.67 |
| the output-major sweep and the small ones | 973,032 | 0.46 |

Every step bit-exact against a Python twin of the assembly — same rounding,
same widths, identical tokens or the test fails. Every bug becomes "at which
layer do the twins disagree", which is a bisection. 31 tests on the lab ROM
now, from the 29 assertions v0.3 had.

The **twin IS** the secret weapon.

## Thrown away

- **Sub-4-bit weights** (v0.3). Post-hoc ternary scores 2.9% top-1 and
  writes *"a boat named Tediaby"*. Four bits was the floor — unless you
  *train* ternary, which is what v0.4 did.
- **Code in HRAM.** On a Game Boy every memory region answers in one cycle.
  HRAM buys shorter instructions, not faster memory.
- **The norm as planes** (v0.9). The audit's largest exact collapse after
  the kernels: another 280K cycles a token, for 836 KB of tables that grow
  with width and depth and a 2 MB ROM header. The release's rule was at
  most 100 KB of new tables; the norm went to registers instead and gave
  up half its cost for none.
- **A hierarchical classifier head** (v0.9). Two levels of 32 would take
  the classifier from a quarter of the token to a few percent, but it is a
  modelling change: bits per character unknown until retrained, and the
  no-repeat rule's stable order over 1,024 tokens stops existing. It waits
  for the decision to grow the vocabulary.
- **A top-9 candidate list for the retry** (v0.9). An insert costs about
  230 cycles and a token makes about 47 of them, 10.8K cycles: a loss
  against simply keeping the top two and rescanning on the third reject,
  once in 440 tokens.
- **8-bit accumulation with a carry plane** (v0.9). Exact, it was argued;
  counted, the carry add *is* the high plane, and 22 blocks of ±381 need
  14 bits with the requant rounding on every low bit. Zero cycles saved.

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

v0.9 was made the same way with the adversary made explicit: nothing
merged on the builder's word, only on a second reader's recount and the
ladder green. The question that started it - what can this stage output -
is the same observation about the argmax, asked of the whole token.

Experience gives you patterns. I wanted cycles to go down. 
They went down a lot.

---

*ChatGBC v0.9 — 963,792 M-cycles per token over a 100-token run, measured
by the cartridge itself. The same weights as v0.4.1, which took 2,259,829.*
