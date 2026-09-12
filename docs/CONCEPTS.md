# How the model works

No machine-learning background assumed. If you know what a dot product is, you
have enough.

**The shape of this model.** 1024-piece vocabulary, 3 layers, working vectors
of 64 numbers, a 64-number state per layer that persists from token to
token, four experts of 176 per layer of which one runs. 374K parameters.
Everything below is that size, and everything below is what the v0.9
cartridge executes: a stage is described the way it actually runs, not the
way the textbook draws it.

**What v0.3 was.** The first three versions ran karpathy's stories260K
transformer: five layers, eight attention heads over a 24-position KV cache
kept in a ring, SwiGLU, 4-bit weights multiplied through product tables.
That page is in the v0.3 tag's docs. v0.4 replaced the model - a recurrent
core instead of attention, ternary experts instead of a dense MLP - and v0.9
replaced the kernels under it. What survived from v0.3 is the tokenizer's
shape, the no-repeat rule and the bit-exact twin.

---

## 1. Text becomes numbers — `encoder.asm`

The model has no idea what letters are. It knows 1,024 *tokens*, and a token
is a common chunk of text: sometimes a whole word, sometimes a fragment.

The tokenizer builds them by merging. Start with single characters. Then look
for the adjacent pair the vocabulary most prefers to merge, and merge it. Repeat
until nothing can merge.

```
O n c e   u p o n
On ce   up on
Once   upon
```

The order matters, which is why each merge carries a **rank** and the lowest
rank wins. That is byte-pair encoding, and it is the same on the cartridge as in
Python — it has to be, or the model sees different input than it was trained on.

On held-out text a token is 3.46 characters. That ratio matters more than it
looks: **the model's speed is per token, but you read characters**, so a
tokenizer that packs more characters per token makes the whole thing feel
faster for free. v0.3's 512-piece vocabulary gave 2.10.

## 2. A token becomes a vector, on the stream's grid — `forward.asm`

Each of the 1,024 tokens has a learned row of 64 numbers. Token 42 means
"take row 42".

That vector is the *residual stream*: the one thing that travels through the
model. Each layer **adds** to it rather than replacing it; three layers, six
adds, and then the question of which token comes next.

The stream is int8 on a fixed grid - steps of 1/8, saturating at 15.875,
the same clamp the trainer used. The rows are stored in ROM already on
that grid, so the embed is a copy: 448 cycles. The add that each layer does
into the stream saturates too (`addsat.asm`): 34 cycles an element, with
the overflow read from the sign bits of the operands and the result.

## 3. Normalise — `rmsnorm.asm`

Before each block, the vector is scaled so its magnitude is roughly constant:
divide by the root-mean-square of its own elements, then multiply by a learned
gain per element.

The point is stability. Without it some layers get numbers ten times bigger than
others and the arithmetic — especially in fixed point — falls apart.

This needs one over a square root, which the SM83 cannot compute. It is a table
lookup. Everything around the lookup is registers in v0.9: the sum of
squares accumulates in a register pair and one high byte (33 cycles an
element); the rounding shifts throw away whole bytes before they shift bits;
and x·r, where r is the one reciprocal shared by all 64 elements, is two
reads from a pair of 16-entry tables the norm builds for itself - x is
16·hi + lo, so x·r is TH[hi] + TL[lo]. About 23K cycles a norm, seven norms
a token.

## 4. The recurrent core: a gate, not attention — `sweep.asm`, `gate.asm`

Each layer keeps a **state**: 64 numbers that survive from one token to the
next. That state is the model's memory of the story so far. There is no list
of previous tokens, no positions, no window: 192 bytes across the three
layers is all it has, and it is rewritten every token.

From the normalised stream, two vectors are made by 64×64 matrix
multiplications: `zl`, the gate logits (through `wz`), and `ht`, the
*candidate* state (through `wh`). The gate turns each `zl` into a number
between 0 and 1 (a sigmoid; as a byte, 0 to 255) and interpolates, element
by element:

```
h = h + z · (ht − h)
```

z near 1 means "take the candidate", z near 0 means "keep what you had". Then
a third matrix, `wo`, reads the new state and the result is added into the
stream. That is a minGRU. Nothing grows with the length of the story, so the
story does not have to end.

In v0.9 the gate is one table read per element. The audit proved two things
about the update line, over every one of its 16,646,400 possible inputs:
that it equals `h + ((zg·(ht − h) + 128) >> 8)`, and that the result never
leaves the interval between `h` and `ht`, so the saturation the twin writes
can never fire. A byte sum is the whole answer. The table is indexed by the
sigmoid's value and by `ht − h`; across the three layers only 118 sigmoid
values ever occur, so the rows are shared: 118 rows of 512 bytes, 60,416
bytes in four ROM banks. The sigmoid itself is never computed - two small
side pages per layer turn the raw `zl` byte into the bank and the address
of its row. 47 cycles an element, from 446 plus a 33-cycle sigmoid pass.

## 5. Experts and the router — `sweep.asm`

The other half of a layer is a feed-forward block: widen 64 numbers to 176,
apply a non-linearity, project back to 64. The widening is where most of the
parameters live.

There are four copies of that block per layer, the **experts**, and a
**router** - four rows of weights - scores the normalised stream and the
highest score picks. One expert runs; the other three sit in ROM and cost
nothing. Half the multiplies of one block twice as wide, and twice the
parameters. Choosing an expert is one bank register write, because each
expert lives in its own ROM bank.

The router's four rows read the same vector as the expert's `w1`, so they
use the same tables (section 10) and the argmax is taken in registers before
the chosen expert's 176 rows are swept.

## 6. ReLU² and the sparse w2 — `relu2.asm`, `matvec_sparse.asm`

The non-linearity is ReLU squared: negative numbers become zero, positive
ones are squared. As a function of one int8 input and one per-layer
constant it has 256 possible inputs, so it is a 256-byte page per layer -
the twin's own line evaluated at every input, saturation included - and the
kernel reads the page. 12 cycles an element.

Half of int8 is negative, and on held-out text 82% of the outputs are zero.
The loop that reads the page is the one place that knows which came out
nonzero, so it writes them down as it goes: (index, value), then a
sentinel.

`w2` is then never multiplied as a matrix. Its weights are stored per
*input* column as two lists: the outputs where the weight is +1 and the
outputs where it is −1 (34 to 40% of the weights are zero and are simply
not listed). For each nonzero activation the kernel fetches its column and
adds the activation into the accumulators on the + list and subtracts it on
the − list: 11 cycles a pair when the add does not carry, 16 when it does.
Integer addition commutes, so the 64 sums are the same integers the dense
matvec would have produced. About 1,100 to 1,650 pairs a layer, 76K cycles
a token for the three layers, where the dense kernel took 345K. If a token
ever had more than 111 nonzero activations the dense kernel would run
instead; the most measured is 88.

## 7. Three layers, then a choice — `cls4.asm`, `forward.asm`

A layer is: normalise, gate, add back; normalise, expert, add back. Three of
those, then a final norm.

Then one matrix would turn the 64 numbers into **1,024 scores**, one per
token, and the highest would win. That is greedy decoding — **no sampling, no
temperature, which is also why this ROM produces the same story from the
same prompt every time**.

But greedy decoding needs only the winner, so the 1,024 scores are never
written anywhere. Per token the classifier builds 16 tables of 81 sums in a
WRAM bank (four ternary weights times four activations, 3⁴ = 81 possible
sums). Each token's row of the classifier is 16 bytes, each byte already the
address of its entry in the matching table; the 16 lookups are summed in a
register pair, compared against the best so far, and the best is kept -
ties to the lowest index, exactly the twin's stable argmax. 226 cycles a
row, no zero pass, no rescan.

## 8. Refusing to repeat — `forward.asm`, `generate.asm`

Greedy argmax is a fixed point: once the state drifts back near one it has
visited, the model re-enters the same loop and stays. Sampling would break
it and ruin the grammar. Instead the decoder skips any token that would
complete a 4-gram it already emitted in this run, up to eight rejects,
over a history of the last 176 tokens. Deterministic, never loops, and
the twin implements the same rule (`pick_token` in `py/quant.py`).

Since the classifier stores no scores, a reject needs a plan: the scan
keeps the runner-up as well as the best. The first two rejects are slot
reads; only the third costs a rescan that skips the blocked tokens, and
that happens about once in 440 tokens.

## 9. The teletype — `teletype.asm`

A token is three or four characters, and they used to land on the screen in
one burst followed by a second of nothing. Now they go into a queue, and the
VBlank interrupt handler releases one every 18 frames - 0.3 s a character -
while the forward pass is busy with the next token. The handler is the only
thing that touches video memory during a story: a character is one tile
write, a scroll moves a shadow buffer and asks for its DMA on the next
frame. The model never waits for the screen, and the screen never waits for
the model. Press SELECT and the story stops; nothing else would stop it.

## 10. Numbers, on a machine with no multiplier — `matvec3.asm`, `sweep.asm`, `state.asm`, `addsat.asm`

The SM83 has no multiply and no divide. The v0.9 answer to that is one
question asked of every stage: **how many distinct outputs can it
produce?** A stage whose outputs are few is a table. A stage whose output is
mostly one value is a skip. Everything else is a shift.

**Activations are int8** — the 64 numbers are single signed bytes, and so is
the state.

**Weights are −1, 0 or +1.** Ternary, trained that way, with one power-of-two
scale per row so the scale is a shift.

**Three weights times three activations is one of 27 sums.** A block of
three ternary weights applied to three activations can only produce
`{0, −x0, +x0} + {0, −x1, +x1} + {0, −x2, +x2}`: 27 values. So for each block
of three inputs the kernel builds those 27 sums once - by derivation, each
entry one 16-bit add from an earlier one, 381 cycles a block, 22 blocks for
a 64-wide vector - and a weight triple is stored as one byte that *is* the
address of its sum. v0.4 walked this input-major, adding each block's entry
into an array of accumulators and requantizing the array afterwards. v0.9
turns it round: the tables are built once per input vector and stay
resident, each output row is a stream of 22 bytes, the row's sum lives in a
register pair at 12 cycles a lookup (three multiply-accumulates), and the
requant - shift, round half up, saturate - happens in registers before the
byte is stored. 302 + 8s cycles a row. No accumulator array, no zeroing,
no second pass. The classifier does the same with blocks of four (81 sums)
because it has 1,024 rows to amortise the bigger build over.

**A stage with few outputs is a table.** ReLU² has 256 inputs: a page. The
gate's update, once proved to be a function of the sigmoid value and
`ht − h`: 118 rows of 512 bytes. The requantized embedding rows: 1,024 of
them, so they are stored requantized. The norm's x·r: 16 entries for the
high nibble, 16 for the low, rebuilt per norm because r changes per norm.

**A stage whose output is mostly one value is a skip.** ReLU² is 82% zeros,
and the place that knows which is the loop that made them. `w2` therefore
touches only the pairs where both the activation and the weight are
nonzero.

**Everything is exact.** Every table is the twin's own function evaluated
at every input it can receive, and the proofs are exhaustive where the
domain allows: all 16,646,400 gate inputs, all 255 × 255 pairs of the
saturating add. The golden token sequence is byte-identical to the one the
tree started with, and that is the test.

The model is not doing less arithmetic than the twin. It is doing the same
arithmetic by looking up answers that were computed at export time, or once
per token for the tables that depend on the input, and skipping the terms
that were zero before anyone multiplied them.

---

## Reading order in the source

1. `encoder.asm` — text to tokens
2. `forward.asm` — the layer loop, the no-repeat rule, and where everything else is called from
3. `rmsnorm.asm`, `gate.asm`, `relu2.asm` — one idea each
4. `matvec3.asm` — the 27-sum table build; `sweep.asm` — the output-major row every block matvec runs; `matvec_sparse.asm` — w2 over the nonzero pairs
5. `cls4.asm` — the classifier's running best; `classifier.asm` — the WRAM bank it works in, and the two older kernels that share it
6. `state.asm` — the buffers and the requant w2 still uses; `addsat.asm` — the residual add
7. `generate.asm` — decode and detokenise; `teletype.asm` — the screen

`py/twin5.py` is the same model in Python, bit-for-bit identical to the
assembly; `py/quant.py` holds the integer primitives it shares with v0.4. If
a section above is unclear, those files are the readable version of it.
