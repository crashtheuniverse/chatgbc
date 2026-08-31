# How the model works

No machine-learning background assumed. If you know what a dot product is, you
have enough.

**The shape of this model.** 512-word vocabulary, 5 layers, working vectors of
64 numbers, 8 attention heads of 8 numbers each, 4 key/value heads, a 24-position
memory. About 260,000 parameters. Everything below is that size.

---

## 1. Text becomes numbers — `encoder.asm`

The model has no idea what letters are. It knows 512 *tokens*, and a token is a
common chunk of text: sometimes a whole word, sometimes a fragment.

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

`"Once upon a time"` comes out as roughly five tokens. That ratio matters more
than it looks: **the model's speed is per token, but you read characters**, so
a tokenizer that packs more characters per token makes the whole thing feel
faster for free.

## 2. A token becomes a vector — `forward.asm`

Each of the 512 tokens has a learned row of 64 numbers. Token 42 means "take
row 42".

That vector is the only thing that travels through the model. Everything after
this is transforming those 64 numbers, five times over, and then asking which
token should come next.

The vector is often called the *residual stream*, because each layer **adds** to
it rather than replacing it. So each layer "enriches" this stream that is nothing but your "temp" vector. 

## 3. Normalise — `rmsnorm.asm`

Before each block, the vector is scaled so its magnitude is roughly constant:
divide by the root-mean-square of its own elements, then multiply by a learned
gain per element.

The point is stability. Without it some layers get numbers ten times bigger than
others and the arithmetic — especially in fixed point — falls apart.

This needs one over a square root, which the SM83 cannot compute. It is a table
lookup. Most of the "hard maths" in this implementation is a table lookup.

## 4. Attention, and what a head actually is — `attention.asm`

**Three projections.** From the 64-number vector, three more are made by matrix
multiplication:

- **Q**, the *query* — what this token is looking for
- **K**, the *key* — what this token offers to anyone looking
- **V**, the *value* — what this token passes on if chosen

**Scoring.** The current token's Q is dotted (you do a dot product) with the K of every token so far.
A big dot product means "these two are relevant to each other". Those scores go
through a softmax, which turns them into weights that sum to one.

**Mixing.** The output is the V of every previous token, weighted by those
scores. So a token literally pulls information out of the tokens it found
relevant.

**Heads.** Doing that once with all 64 numbers would force one notion of
relevance. Instead the vector is split into **8 heads of 8 numbers**, and each
head scores and mixes independently. One head might track the subject of the
sentence, another the token immediately before, another matching punctuation.
Nobody assigns them those jobs — they fall out of training. The eight results
are concatenated back into 64 numbers.

Heads are cheap because splitting is free: 8 heads × 8 numbers is the same 64
numbers, just scored in eight separate groups.

**Grouped queries.** There are 8 query heads but only **4 key/value heads** —
each K/V head is shared by two Q heads. This is grouped-query attention, and it
halves the amount of K and V that has to be stored. 
There are various possible permutations here. But grouping is necessary for 32KB of RAM.

**Position, by rotation** — `rope.asm`. Nothing so far knows word order; a dot
product does not care which token came first. So before scoring, Q and K are
*rotated* by an angle proportional to the token's position. Two tokens close
together end up rotated similarly and still score well against each other; far
apart, less so. That is rotary position embedding, and the useful property is
that it encodes *relative* distance while only ever being applied to one token
at a time.

## 5. The KV cache, and why generation is not quadratic

Here is the problem. To generate token 100, attention needs the K and V of all
99 tokens before it. Recomputing them every step would mean the whole passage is
re-processed for every new word 😭 — quadratic work, and hopeless on this hardware.

So they are computed once and kept. That is the **KV cache**: for every position,
the K and V that position produced. Generating a token is then one new K and V,
plus a scan over the stored ones.

This is the single reason interactive generation is possible at all, on any
machine. **not just the GBC**

**The cost that remains.** The scan still grows with context. In this ROM you can
watch it happen — the cycle counter in the status bar climbs steadily as the
passage gets longer, then flattens. It flattens because of the next part.

**The ring.** The cache has a fixed number of slots — 24 in this ROM. Position
24 has nowhere to go — unless you let it overwrite slot 0. The slot for position
`p` is `p mod 24`, while the positional rotation keeps using the *absolute* `p`.

Those two had been the same number by accident. 
**Separating them is the whole trick**: 
I only needed to notice that storage can be completely independent since we are really 
generating a new KV pair per token! 
The model attends to the last 24 positions, forever, and never notices anything wrapped.
Generation stops having a length limit.

**why 24?** Tests and tests. Ended up being ok paying for a mod instead of a 32 context window. 
It's more expensive than a power of two, but below 24 the loss climbs fast. 
I will try to make it back to 16 at some point, but likely with a freshly trained set of weights.
 

## 6. The feed-forward block — `swiglu.asm`

Attention moves information *between* tokens. The feed-forward block does the
thinking *within* one.

It widens 64 numbers to 172, applies a non-linearity, and projects back down to
64. The widening is where most of the model's parameters live.

The non-linearity here is **SwiGLU**, which is two projections rather than one: a
*value* path and a *gate* path. The gate is squashed through a smooth
S-shaped curve and then multiplied into the value, so the block can learn to
suppress its own outputs. A plain non-linearity cannot do that.

Both the squash and the reciprocal it needs are, again, tables.

## 7. Five layers, then a choice — `forward.asm`, `generate.asm`

A layer is: normalise, attend, add back; normalise, feed-forward, add back. Five
of those.

Then one final matrix turns the 64 numbers into **512 scores**, one per token in
the vocabulary. The highest score wins and becomes the next token. That is greedy
decoding — **no sampling, no temperature, which is also why this ROM produces the
same story from the same prompt every time**. 

The new token is appended and the whole thing runs again.

## 8. Numbers, on a machine with no multiplier — `matvec.asm`, `state.asm`

The model was trained in floating point.

**Activations are int8** — the 64 numbers are single signed bytes.

**Weights are 4-bit.** Not "the value rounded to 4 bits": each matrix has its own
**codebook** of 16 representative values, fitted to that matrix's actual
distribution, and a weight stores which of the 16 it is. Rare large values still
get represented because the codebook can place a level out there.

**Scales are powers of two.** Every quantised tensor has a scale that says what
"1" means. Constraining those to powers of two means converting between tensors
is an arithmetic shift instead of a division — and the SM83 has no divide either.

**And so the multiply disappears.** Sixteen possible weight values, 256 possible
activation bytes: every product the model could ever need is 4,096 numbers, small
enough to precompute into ROM. At runtime the kernel copies the 32 bytes for the
current activation into high RAM, and multiplying becomes a single load
instruction.

That is the whole reason this runs at a usable speed. The model is not doing less
work — it is doing the same work by looking up answers computed years' worth of
cycles in advance, at export time.

---

## Reading order in the source

1. `encoder.asm` — text to tokens
2. `forward.asm` — the layer loop, and where everything else is called from
3. `rmsnorm.asm`, `rope.asm`, `attention.asm`, `swiglu.asm` — one idea each
4. `matvec.asm` — the kernel the whole budget is spent in
5. `state.asm` — requantisation, the glue between every stage
6. `generate.asm` — decode and detokenise

`py/quant.py` is the same model in Python, bit-for-bit identical to the assembly.
If a section above is unclear, that file is the readable version of it.
