# The model

> **v0.4 note.** This page describes the v0.3 model - karpathy's stories260K transformer, 4-bit tables, a 24-token attention window. v0.4 runs a different model trained here: a minGRU core, four ternary experts per layer, a block-sum kernel. The README's *What changed since v0.3* has the short version; this page will follow.

What ChatGBC actually runs. 
If you want the implementation instead, that is [CONCEPTS.md](CONCEPTS.md).

```
Config(dim=64, hidden_dim=172, n_layers=5, n_heads=8, n_kv_heads=4, vocab=512)
```

This is exactly from `stories260K` as it was trained with those numbers.

## The shape

| | | |
|---|---|---|
| **dim** | 64 | the *residual stream* — one vector, the width of the whole model |
| **hidden** | 172 | the feed-forward block's inner width, ~2.7× dim |
| **layers** | 5 | how many times the block runs, one after another |
| **heads** | 8 | attention heads, 8 numbers each (8 × 8 = dim) |
| **kv_heads** | 4 | each key/value head is shared by two query heads |
| **vocab** | 512 | tokens, BPE, ~2.6 characters each |

## One vector, updated ten times

There is a single 64-number vector. It is the whole state of the model for the
token being generated, and it is never replaced — each block **adds** to it:

```
after embedding   |x| = 2.348
after layer 0     |x| = 5.672     changed by 4.069
after layer 1     |x| = 6.926     changed by 2.536
after layer 2     |x| = 7.311     changed by 2.337
after layer 3     |x| = 9.059     changed by 4.232
after layer 4     |x| = 9.644     changed by 4.905
```

Same 64 slots throughout. That is why it is called a *stream*: information is
written into it and later layers read what earlier ones left. Layer 2 cannot
start before layer 1 finishes, because it reads layer 1's output.

Each layer does this, twice adding into the stream:

1. normalise the stream, run attention over it, **add the result back**
2. normalise again, run the feed-forward block, **add that back**

## Two things move, in different directions

This is the distinction worth getting straight.

**Down, within one token:** the residual stream, through 5 layers. 64 numbers,
updated 10 times, then discarded. It exists for one token only.

**Sideways, across tokens:** the **KV cache**. Each layer stores the key and
value it computed for this position so the *next* token can attend to it. That
is what persists, and that is what the ring buffer manages — 24 slots per layer,
overwritten in place once full.

The residual stream is vertical and temporary. The KV cache is horizontal and
persistent. Only the KV cache has a length limit and wraps.

## What one layer costs

| | shape | MACs | |
|---|---|---|---|
| wq | 64 → 64 | 4,096 | query projection |
| wk | 64 → 32 | 2,048 | key — 4 KV heads, not 8 |
| wv | 64 → 32 | 2,048 | value |
| wo | 64 → 64 | 4,096 | merge the heads back |
| **w1** | 64 → 172 | **11,008** | feed-forward up, value path |
| **w3** | 64 → 172 | **11,008** | feed-forward up, gate path |
| **w2** | 172 → 64 | **11,008** | feed-forward down |
| | | **45,312** | per layer |

Multiply that by five layers and add the classifier:

```
layer weights   226,560
embedding        32,768   (reused as the classifier)
                ────────
                259,328   parameters

MACs per token: 259,328
```

One token is one pass over the model weights — every parameter is multiplied once. So
`MACs = parameters`. 
This means in a basic transformer you are mostly bound by the amount of weights you have.

After trickeries it got down to 19 cycles per multiply-accumulate: that is 4.93M cycles.
Means that **2.35 seconds per token** are just this part. 

**loophole** 
At lower bit precisions, some weights quantize to 0.
However the codebook chosen thanks to the AI assisting here (didn't even remotely think of it), 
is the Lloyd-Max where 0 is still meaningful. Means we can't skip them. 

(The attention *weights* are a different story — those come from a
softmax, and 46% of them are exactly zero. The ROM skips those.)

## Depth vs Width

Sharing weights between layers — some architectures do — would cut the ROM by
five. **It would not save a single cycle**, because you still run five passes.

But depth does cost, just not in multiplies. Every layer pays again for
normalisation, RoPE, softmax and requantisation: about 3.09M cycles a token
across 5,316 such operations. A model with the same parameter count but two
layers instead of five pays that overhead **twice, not five times**.

> **Depth costs time. Width costs parameters.**

Which is why the measured rule for anything trained later is *wide beats deep*:
at a constant parameter count, dim 96 with 2 layers is 1.44× the parameters per
cycle of dim 64 with 5.

## Where the numbers come from
Look at `py/census.py`, `py/profile_all.py` and `py/arch.py`.
This last one is particularly interesting to predict what a different shape would cost before even attempting it.
