# v0.9: the speed release

v0.4.1 shipped 1.146 bits per character at 1.08 s a token, 0.31 s a
character. v0.5 through v0.8 do not exist as releases: the work that was
planned for them - one-bit kernels, a plane classifier, the stream on the
trainer's grid - landed on the tree as options, and an audit of the whole
token showed that the biggest gain left was not a better model but a
cheaper token for the model we had. So the version number jumped. **v0.9
is the same weights at 2.3x the speed, bit for bit**: 0.46 s a token,
0.133 s a character, 1.126 bits per character, 61 KB of new tables. v1.0
is what is done with the time that buys.

## What the audit found

Every stage of the token was read as a function: what inputs it takes,
how many distinct outputs it can produce. Where the answer is small, the
stage collapses into a lookup, the way three ternary weights times three
activations became a 27-entry table in v0.4. Where the output is mostly
one value - ReLU² is 82% zeros - the work that produces the other value
can be skipped. Every claim was recounted by a second reader against the
instruction timings and checked against the integer twin, and the token
was accounted for line by line, each census stage claimed by exactly one
collapse.

The collapses v0.9 took are all **exact**: the ROM produces the same
integers as the twin for every input, so nothing was retrained and the
golden sequence did not change. Measured on the 8-token census
(`py/census5.py`), on the tree the release started from and on the release,
cycles a token:

| stage | before | after | what changed |
|---|---|---|---|
| classifier | 423,496 | 246,712 | output-major over 16 tables of 81 sums, the best kept in registers, no logits stored, no zero pass, no rescan |
| w1 matvec, with the router | 332,680 | 202,728 | output-major sweep over 22 resident tables; the router rides on the same tables |
| w2 matvec | 344,696 | 67,624 | only the nonzero (activation, weight) pairs, listed by the ReLU² loop |
| wz | 131,264 | 89,248 | output-major sweep (this line carries the table build shared with wh) |
| wh | 131,312 | 63,408 | output-major sweep over wz's build |
| wo | 131,312 | 89,072 | output-major sweep |
| w1 requant | 63,632 | 0 | folded into the sweep's epilogue |
| wz, wh, wo requants | ~72K | 0 | folded into the sweep's epilogue |
| w2 requant | 19,840 | 19,800 | unchanged |
| rms_att | 137,456 | 68,888 | sum of squares in registers, shifts peeled by the byte, x·r through nibble tables |
| rms_ffn | 140,016 | 70,112 | the same |
| rms_final | 48,552 | 23,720 | the same |
| gate | 86,120 | 9,192 | one byte table, indexed by the sigmoid value and ht−h |
| sigmoid | 6,368 | 0 | folded into the gate table's side pages |
| ReLU² | 59,032 | 8,752 | one 256-byte page per layer |
| embed | 13,368 | 448 | rows stored on the stream's grid; the embed is a copy |
| residual adds | 18,632 | 13,272 | page-form loop, overflow from the sign bits |
| debug snapshots | 5,624 | 0 | lab build only |
| **staged total** | **2,164,704** | **973,032** | |

New tables in ROM: 60,416 B for the gate and 768 B for ReLU², about 61 KB
against the audit's rule of at most 100 KB. Everything else is re-encoded
weights or tables rebuilt per token in WRAM. The ROM file is 512 KB, about
370 KB of it content.

**In the numbers VERSIONS.md is measured in:** the app ROM's own counter,
963,792 cycles a token over 100 tokens with the teletype running, **0.46 s
a token** and 0.133 s a character; **1.126 bits per character** as shipped
on the 200 held-out stories, 1.123 for the same checkpoint in fp32. The
release goal had been 0.5 s a token or better at v0.4.1's quality. The
ladder every kernel passed: the twin unchanged, golden strict byte for byte,
then the census.

## What v0.9 leaves out, and why

- **The norm as tables.** Another 280K cycles for 836 KB of planes that
  grow with width and depth, and a 2 MB ROM header. Ruled out by the
  table budget: v0.9 adds at most 100 KB of tables in total. The norm went
  to registers instead and halved.
- **A hierarchical classifier.** The argmax is linear in the vocabulary,
  so a bigger dictionary is paid for there and nowhere else; a two-level
  head (32 groups of 32) would take the classifier from a quarter of the
  token to a few percent. It changes the model and the no-repeat rule, so
  it waits for the decision to grow the vocabulary.
- **Anything that changes the twin.** Every new-semantics option measured
  was worth less than a retrain except the head above.

## v1.0: the model, and where it runs

With the token at half its price, v1.0 spends the time on the model and
on getting it into more hands:

1. **Training and output.** The whole corpus, longer windows, the
   training curve measured instead of assumed (the 20K-step habit was a
   habit), the 2048-piece tokenizer priced against the classifier it
   costs. Measured as bits per character on the same 200 held-out
   stories as every version before it.
2. **Weights as a distribution.** Checkpoints and the corpus recipe
   published where they can be reproduced, with the hashes the release
   carries.
3. **The engine outside the cartridge.** The integer twin is the
   specification; a small C implementation of the same inference, bit
   for bit, runs the model on a PC. An adapter for other targets is
   priced from that.
4. **A first conversational brain** trained and shipped on the same
   engine, as the example of what a cartridge can hold beyond stories.

## Not in v0.9 or v1.0

Attention, in any form: the recurrent core is the point. Sampling:
greedy with no-repeat is deterministic and testable. Anything that cannot
be scored in bits per character on held-out text, or verified bit for
bit against the twin.
