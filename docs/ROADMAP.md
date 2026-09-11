# v0.9: the speed release

v0.4.1 ships 1.146 bits per character at 1.03 s a token, 0.30 s a
character. v0.5 through v0.8 do not exist: the work that was planned for
them - one-bit kernels, a plane classifier, the stream on the trainer's
grid - is on this branch already, and an audit of the whole token showed
that the biggest gain left was not a better model but a cheaper token for
the model we have. So the version number jumps. **v0.9 is the same weights
at about twice the speed, bit for bit**, and v1.0 is what is done with the
time that buys.

## What the audit found

Every stage of the token was read as a function: what inputs it takes,
how many distinct outputs it can produce. Where the answer is small, the
stage collapses into a lookup, the way three ternary weights times three
activations became a 27-entry table in v0.4. Where the output is mostly
one value - ReLU² is 82% zeros - the work that produces the other value
can be skipped. Every claim was recounted by a second reader against the
instruction timings and checked against the integer twin, and the token
is accounted for line by line (2,194,784 census cycles, 21 stages,
each claimed exactly once).

The collapses v0.9 takes are all **exact**: the ROM produces the same
integers as today's twin for every input, so nothing is retrained and
the golden sequence does not change. Together they are budgeted at about
1.1M of the 2.17M cycles, with no new table larger than 60 KB:

| collapse | saves / token | table |
|---|---|---|
| w2 walks only the nonzero (activation, weight) pairs, listed where ReLU² makes them | ~290K | weights re-encoded as column lists |
| the block matvecs go output-major: tables resident per input vector, each row summed in registers, requantized in place | ~270K | 1.5 KB WRAM |
| the router rides on w1's tables; wz and wh share one build; the 27-entry table built as a direct sum | ~140K | none |
| the classifier keeps only the running best: no stored logits, no zero pass, no rescan | ~160K | 4 KB WRAM |
| the gate as one byte table with the sigmoid folded in (saturation proved dead over all 16.6M inputs) | ~80K | 60 KB |
| ReLU² as one page per layer; requant epilogues in registers | ~90K | 768 B |
| the norm's shifts peeled by the byte, its sum of squares in registers | ~70K | none |
| embedding rows stored on the stream grid; debug copies out of the app build | ~24K | none |

**The goal, in the numbers VERSIONS.md is measured in:** v0.4.1's
1.146 bits per character, unchanged, at **0.5 s a token or better**
(0.15 s a character) as shipped, on held-out text, verified by the same
ladder every kernel has used: the twin unchanged, golden strict byte for
byte, then the census.

## What v0.9 leaves out, and why

- **The norm as tables.** Another 280K cycles for 836 KB of planes that
  grow with width and depth, and a 2 MB ROM header. Ruled out by the
  table budget: v0.9 adds at most 100 KB of tables in total.
- **A hierarchical classifier.** The argmax is linear in the vocabulary,
  so a bigger dictionary is paid for there and nowhere else; a two-level
  head (32 groups of 32) would take the classifier from 12% of the token
  to 2%. It changes the model and the no-repeat rule, so it waits for
  the decision to grow the vocabulary.
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
