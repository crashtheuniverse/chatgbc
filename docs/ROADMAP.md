# v0.5: spend the headroom

v0.4.1 closed the gap the cartridge used to cause: what ships scores within 2%
of what was trained. It did not close the gap between models. stories260K in
float is 0.876 bits per character on the held-out stories; ours is 1.123. The
cartridge is now seven times faster per character than it needs to be for
the reader, so v0.5 is about turning cycles into bits.

**The goal, in the numbers VERSIONS.md is measured in:** as shipped, at most
**1.00 bits/char** (13% under v0.4.1) at no more than **0.6 s/char** on
held-out text. The stretch is v0.3's float ceiling, 0.876, on the cartridge.
Every candidate is priced before it is trained and scored on the twin before
it is believed.

## What the cycles buy

Priced with the census model of the shipped kernel (10.5 cycles a
block-kernel MAC, 8.3 a classifier MAC, ~203K a layer of norms, gate and
requantization) at the tokenizer's characters per token. Pick by bits per
character per cycle, once each has been trained and scored.

| shape | M-cycles/tok | s/tok | s/char | params | ROM |
|---|---|---|---|---|---|
| v0.4.1: 3L 64d, experts of 176, vocab 1024 | 2.26 | 1.08 | 0.31 | 374K | 256 KB |
| binary 3L 96d x256, v1024 (measured kernels) | 2.36 | 1.13 | 0.33 | 773K | 256 KB |
| 4L 64d x176, v1024 | 2.83 | 1.35 | 0.39 | 476K | 256 KB |
| 3L 64d x256, v1024 | 2.58 | 1.23 | 0.36 | 496K | 512 KB |
| 3L 96d x256, v1024 | 3.86 | 1.84 | 0.53 | 772K | 512 KB |
| 3L 96d x256, v2048 | 4.67 | 2.23 | 0.57 | 871K | 512 KB |
| 4L 96d x256, v1024 | 4.87 | 2.32 | 0.67 | 997K | 512 KB |
| v0.3, for scale | 12.92 | 6.16 | 2.94 | 260K | 512 KB |

## The order of work

**0. The BitNet question - the kernels are in; the model is not yet.** One-bit weights
with int8 activations run subset-sum tables (every sum a block of inputs
can produce, built once per block per token, one lookup per block per
output): measured on the lab bench, a block of 5 in HRAM costs 6.97 cycles
a MAC at 64 outputs and a block of 8 in WRAM 3.08 on the classifier,
against ternary's 10.70. Trained at equal seconds per character - binary
at dim 96 with experts of 256 against the shipped ternary - binary scores
1.086 bits per character to ternary's 1.115, with 2.1x the parameters at
one bit each. Activation width stays at 8 bits: narrowing it cost 6% in
bits and buys nothing under table kernels. The port is done and golden strict:
blocks of four in HRAM for the rows, blocks of eight on planes for a
one-bit classifier, and a ternary classifier on 243-entry planes that
takes 120K cycles off v0.4.1 with no retraining. But as shipped - on the
twin, not the trainer - the one-bit dim-96 model scores 1.138 against
1.126 for v0.4.1's weights on the same tree, at 44% more cycles: the
trainer's per-token activation scaling is a normalization the cartridge's
static exponents cannot follow, and the one-bit model leans on it. So the
next lever is a per-token activation exponent on the cartridge (one max
scan a vector, the requant shift adjusted by the difference); until it
closes that gap, v0.5 ships ternary rows, and the one-bit kernels wait.

**1. Make training cheap enough to sweep.** A 20K-step run is 3.5 hours and
the step is launch-bound (0.37 s alone, 3 s if anything shares the GPU). The
fused scan is in. Next: capture the whole training step as a CUDA graph, and
a larger batch with fewer steps. Target: a 3L 64d run in under an hour, so a
shape sweep is an evening rather than a week. Measured by seconds per step at
identical loss.

**2. Squeeze the shape we have.** Before buying capacity, find out what the
current shape leaves on the table, because it is free on the cartridge:
- longer runs - the held-out curve was still falling at 20K steps as the
  Arenas residual finished annealing; 40K and a slower anneal
- longer training windows - the model trains on 96-token windows and runs
  forever; train on 256 and see if the held-out (scored on 256) moves
- the whole corpus - 59M tokens seen three times; the other 2 GB of
  TinyStories is one download away
- the tokenizer trained on all of it, and 2048 pieces priced against the
  classifier it costs

**3. Buy capacity where the price is right.** In the order the table
suggests: wider experts first (parameters at half the MACs), then a fourth
layer, then dim 96. Each is a trained run, a twin score and a census, not an
opinion. The ROM side has to generalize with it: embedding parts of any row
size (today's lookup assumes 256 rows a bank), the classifier in as many
parts as the vocabulary needs, and buffers sized from DIM everywhere - the
exporter asserts what the kernels assume, so a shape that violates one fails
at export rather than on the cartridge.

**4. Diet what is not a matvec.** At v0.4.1 the three norms are 319K cycles
a token (14%), the requantizations 146K, the gate 86K. A norm that costs
what a matvec of its size costs is worth about 8% of the token; nothing else
on the list is worth more than 5%.

**5. Ship it the way v0.4.1 shipped.** Golden strict, suite green, census,
score5, a capture, VERSIONS.md gains a column, the release carries the ROM
and its hash. The three doc pages get rewritten for the model that actually
runs.

## Not in v0.5

Attention, in any form: the recurrent core is the point. Sampling: greedy
with no-repeat is deterministic and testable, and sampling broke the grammar
at this size when it was measured. Anything that cannot be scored in bits
per character on held-out text.
