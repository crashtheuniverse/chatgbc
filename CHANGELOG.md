# Changelog

What changed between releases, newest first. Measurements for every
version, taken the same way, are in [VERSIONS.md](VERSIONS.md).

## What changed since v0.9

Nothing in the story model and nothing in its tokens: the golden sequence is
byte-identical. What moved is the wait before the first token, and Rei.

- **The encoder is exact, and fast.** The old one looked at pieces up to 7 bytes; both vocabularies have pieces up to 11, so some lines drifted from the Python tokenizer. It also scanned the whole vocabulary on every merge: 8.3 million cycles for "Once upon a time". Now a hash table and a merge loop that only rechecks what changed: 55,552 cycles, and Python's tokens
- **A prompt token only feeds the state.** Its prediction is thrown away anyway, so its pass stops at the last layer's state update. A test runs the prompt both ways and compares the state byte for byte
- **Rei**, above

## What changed since v0.4.1

Nothing in the model. Every change below produces the same integers as the
twin for every input, which is why the golden token sequence is byte-identical
before and after, and why the tests could say so.

The method was an audit by codomain. Each stage of the token was read as a
function: what it takes in, how many distinct values it can put out. Where
the answer is small the stage becomes a table. Where the output is mostly one
value - ReLU² is 82% zeros - the work that produces the other value is
skipped. One reader per stage proposed, a second recounted every cycle against
the instruction timings and checked every exactness claim against the twin,
and the survivors were built one at a time, each in its own worktree with its
own adversarial review. The rule was at most 100 KB of new tables; the release
uses 61.

**The block matvecs go output-major.** v0.4 built a 27-sum table per block
of three inputs and walked every output row against it, into an accumulator
array in WRAM, then requantized the array in a second pass. Now the 22
tables of the input vector are built once into WRAM - by derivation, each
entry one 16-bit add from an earlier one, 381 cycles a table - and each
output row is a stream of 22 bytes, each byte already the low address of its
table entry. The row's sum lives in register pair `de` at 12 cycles per
lookup (three MACs), the shift byte follows the codes, and the requant
(round-half-up, saturate to int8) happens in registers. No accumulator
array, no zero pass, no requant pass: 302 + 8s cycles a row. wz and wh read
the same vector, so they share one build; the router's four rows ride on
w1's tables and the argmax is taken in registers before the chosen expert's
176 rows are swept.

**w2 walks only the nonzero pairs.** ReLU² is a function of one byte and one
per-layer constant, so it is a 256-byte page per layer: the twin's line
evaluated at all 256 inputs, saturation included. The loop that reads the
page is the one place that knows which activations came out nonzero, so it
writes the list. w2's weights are stored per input column as lists of output
offsets, the +1 set and the −1 set, and the kernel does one 16-bit add or
subtract per nonzero (activation, weight) pair - about 1,100 to 1,650 pairs
a layer, since 82% of the activations and 34-40% of the weights are zero.
About 68K cycles a token for the three layers on the 8-token census
(67,624) where the dense block kernel took 344,696. A guard falls back to the dense kernel above 111 nonzero activations;
the measured maximum is 88.

**The classifier keeps only the running best.** Greedy decode needs the
argmax and nothing else, and the kernel v0.9 started from stored 1,024
int16 logits to find it: zero them, add thirteen planes into every one,
rescan.
Now 16 tables of 81 sums (blocks of four ternary weights) are built per
token in a WRAM bank, each row is 16 lookups summed in `de` and compared
against the best so far, ties to the lowest index - exactly the twin's
stable argmax. No logits stored, no zero pass, no rescan. The no-repeat
rule may turn the winner down; the scan keeps a runner-up for that, and only
a third reject costs a rescan, once in about 440 tokens. 226 cycles an
output.

**The gate is one byte table.** The minGRU update `h = h + z ⊙ (h̃ − h)`
was the last place the ROM multiplied: two quarter-square products and a
shift-and-saturate, 446 cycles an element, after a 33-cycle sigmoid pass.
Two facts about the twin's line were proved over all 16,646,400 inputs:
the result equals `h + ((zg·(ht−h) + 128) >> 8)`, and it never leaves
`[min(h,ht), max(h,ht)]`, so the saturation is dead and a byte sum is the
whole answer. The table is indexed by the sigmoid value and by `ht−h`;
only 118 sigmoid values occur across the three layers, so the rows are
shared: 60,416 bytes in four banks. The sigmoid itself is never computed -
two side pages per layer turn the raw gate logit into the row's address.
47 cycles an element.

**The norm in registers.** No tables. The sum of squares accumulates in
registers without the stack, the rounding shifts peel whole bytes before
they shift bits, and x·r goes through two 16-entry nibble tables rebuilt
per norm in the matvec's idle HRAM. Each of the seven norms costs about
23K cycles, from about 46K.

**The small ones.** Embedding rows are stored already requantized to the
stream's grid, so the embed is a copy (13,368 cycles to 448). The layer-0
debug snapshots that the shipping ROM used to take for nothing assemble
only in the lab build. The residual add is a 34-cycle page-form loop with
the overflow read from the sign bits.

Two fixes to the integer path that landed between the tags ship with it,
and they are why the quality line moved although the weights did not: the
residual stream is pinned to the grid the trainer used (v0.4.1 had
calibrated it four times coarser), and the norm's width factor is folded
into its gains. The first moves the score at dim 64 from 1.146 to 1.126;
the second is exact at this width. Both are in the twin, so the tree v0.9
started from already had them, at 2,164,704 cycles a token on the 8-token
census (the v0.4.1 release measured 2,259,829 with the teletype off,
2,271,104 with it).

On that census the token went from 2,164,704 cycles to 973,032:
classifier 423,496 → 246,712; w1 with the router 332,680 → 202,728; w2
344,696 → 67,624; the three norms 326,024 → 162,720; gate and sigmoid
92,488 → 9,192; ReLU² 59,032 → 8,752; the five requant passes 155K → 19,800.
The ROM file grew from 256 KB to 512 KB: the w2 column lists and the gate
table take the content to about 370 KB, and the MBC5 header rounds to the
next power of two.

## What changed since v0.3

v0.3 took a float transformer and squeezed it into 4-bit tables and a
24-token window. Measured on held-out stories, the squeeze cost 31% in bits
per character: the checkpoint scored 0.88, the cartridge 1.15. v0.4 turned
it around: decide what the hardware does well, train a model that lives
there from step one, and ship what was trained.

**The multiply became a table of sums.** A ternary weight is −1, 0 or +1,
so three of them applied to three activations is one of 27 signed sums.
v0.4 built those sums once per block of three inputs and retired three
multiply-accumulates per lookup. No product tables, no bank switch per
input, and a matrix in ROM is one byte per three weights. v0.9 keeps the
27 sums and changes who walks whom.

**The core became a minGRU, not attention.** `h = h + z ⊙ (h̃ − h)`, gates
from the input only. Three 64×64 matvecs per layer and a 64-byte state;
nothing grows with the length of the story. v0.3 needed a ring of 24
cached positions and lost the thread when the ring wrapped. This never
wraps, so the story never has to end.

**Four experts, one runs.** Each layer's MLP is four experts of 176; a
ternary router picks one per token. Half the multiply-accumulates of the
dense layer, twice the parameters, and choosing an expert is one MBC5 bank
register write.

**Trained inside the integers.** Weights fake-quantized to ternary with
power-of-two row scales during training, activations and the recurrent
state to int8, the classifier and router to ternary at a single scale, and
a full-precision residual (the Arenas trick from
[Sherry](https://arxiv.org/abs/2601.07892)) annealed to zero so ternary
converges at all. In float, stories260K is still the better model (0.88
bits per character against 1.12); what v0.4 bought is that nothing is lost
between the training run and the cartridge.

**The teletype.** A token is three or four characters, and they used to
land in one burst followed by a second of nothing. v0.4.1 put them in a
queue; the VBlank handler releases one every 18 frames while the forward
pass is busy with the next token, and is the only thing that touches VRAM
during a story. The model never waits for the screen.

_Note_: the GBC is technically 8MHz but those are T-Cycles. A full instruction usually is 4 of those.
This means you really have 2MHz worth of `M` cycles, about 1 instruction each — so consider it a 2MHz HW
