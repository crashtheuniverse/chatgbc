# The model

What ChatGBC actually runs, as of v0.9. If you want the implementation
instead, that is [CONCEPTS.md](CONCEPTS.md).

```
DIM 64   HIDDEN 176   EXPERTS 4   N_LAYERS 3   VOCAB 1024      (src/model.inc)
```

Those constants are written by `py/export5.py` from the checkpoint,
`models/ts3L_v1024.bin`: the model v0.4 trained, and the one v0.4.1 and v0.9
both ship. v0.9 changed the kernels, not the model, so every number on this
page about the shape is v0.4's and every number about cycles is v0.9's.

## The shape

| | | |
|---|---|---|
| **dim** | 64 | the *residual stream* — one vector, the width of the whole model |
| **state** | 64 per layer | the minGRU's `h`: what persists from one token to the next |
| **experts** | 4 × 176 | the MLP's inner width; one expert of the four runs per token |
| **layers** | 3 | how many times the block runs, one after another |
| **vocab** | 1024 | tokens, BPE, 3.46 characters each on held-out text |

## One vector, updated six times

There is a single 64-number vector. It is the whole working state of the
model for the token being generated, and it is never replaced — each block
**adds** to it. Three layers, two adds each: six updates, then a final norm
and the classifier.

Each layer does this:

1. normalise the stream; read it through `wz` and `wh`; let the gate mix the
   candidate into the state `h`; read `h` through `wo`; **add the result back**
2. normalise again; let the router pick an expert; `w1`, ReLU², `w2`; **add
   that back**

## Two things move, in different directions

**Down, within one token:** the residual stream, through 3 layers. 64 bytes,
updated six times, then discarded. It exists for one token only.

**Sideways, across tokens:** the state `h`, 64 bytes per layer, 192 in all.
The gate rewrites it in place every token. It has no length, no slots and
no ring; nothing wraps, so nothing is forgotten by falling off an edge.
v0.3's sideways object was a KV cache of 24 positions per layer, and the
story lost the thread when the ring came round. The trade is that `h` is
all the model has of the past: whatever it did not write into 192 bytes is
gone.

## The minGRU update

From the normalised stream `xb`, two 64×64 matvecs:

```
zl = wz · xb          gate logits
ht = wh · xb          the candidate state
zg = sigmoid(zl)      as a byte, 0..255 for 0..1
h  = sat8((zg·ht + (256 − zg)·h + 128) >> 8)
out = wo · h          added into the stream
```

The gate reads the input, not the previous state, which is what lets `wz`
and `wh` run on the same vector and share one table build. On the cartridge the update line is
computed as `h + ((zg·(ht − h) + 128) >> 8)`, which was proved equal to the
twin's line for every one of the 16,646,400 inputs and never leaves
`[min(h, ht), max(h, ht)]`, so the `sat8` is dead and the whole line is one
table read (see [CONCEPTS.md](CONCEPTS.md), section 4).

## The MoE ReLU² MLP

From the second norm's output `xf`:

```
e  = argmax(router · xf)      four ternary rows, ties to the lowest index
a  = w1[e] · xf               176 outputs
u  = sat8(relu(a)² >> r)      r one constant per layer
x += w2[e] · u                back to 64
```

Four experts, one runs: half the multiply-accumulates of a dense 352-wide
MLP for twice the parameters. Choosing an expert is one MBC5 bank register
write, because each expert's matrices live in their own ROM bank.

## MACs and parameters

| | shape | MACs run | parameters | |
|---|---|---|---|---|
| wz | 64 → 64 | 4,096 | 4,096 | gate logits |
| wh | 64 → 64 | 4,096 | 4,096 | candidate |
| wo | 64 → 64 | 4,096 | 4,096 | state back to the stream |
| router | 64 → 4 | 256 | 256 | which expert |
| **w1** | 64 → 176 | **11,264** | 45,056 | one expert runs, four are stored |
| **w2** | 176 → 64 | **11,264** | 45,056 | one expert runs, four are stored |
| | | **35,072** | **102,656** | per layer |

Three layers and the classifier:

```
layers          105,216 MACs     307,968 parameters
classifier       65,536 MACs      65,536 parameters   (the embedding, tied)
norm gains                            448
                ─────────────    ───────────────────
                170,752 MACs     373,952 parameters
```

v0.3's rule was `MACs = parameters`: one token multiplied every weight once.
Here a token multiplies 46% of them, because three experts of four sit in
ROM and cost nothing. And v0.9's `w2` does not even do that: it adds only
where both the activation and the weight are nonzero, about 1,100 to 1,650
adds a layer where the matrix has 11,264 multiply-accumulates. The
multiply-accumulate stopped being the unit of cost. The row is.

## What one layer costs, in v0.9 cycles

The 8-token census (`py/census5.py`) times each stage over the three layers;
below is that line divided by three, rounded to the ten.

| stage | cycles | what it is |
|---|---|---|
| norm, before the core | 22,960 | sum of squares, rsqrt lookup, x·r, gain, all in registers |
| wz and wh | 50,890 | one build of 22 tables (8.4K), then 128 rows swept |
| gate | 3,060 | 64 table reads, 47 cycles each |
| wo | 29,690 | one build, 64 rows |
| residual add | 2,210 | 64 saturating adds, 34 cycles each |
| norm, before the MLP | 23,370 | |
| router and w1 | 67,580 | one build, 4 router rows, an argmax, 176 expert rows |
| ReLU² | 2,920 | 176 page reads, and the list of the nonzero ones |
| w2, sparse, with its requant | 29,140 | one add per nonzero (activation, weight) pair |
| residual add | 2,210 | |
| **one layer** | **~234,000** | |

Then the token: three layers 702,100, the final norm 23,720, the classifier
246,712, the embed 448 — 973,032 with the census's own timers. A quarter of
the token is the classifier, and the classifier is linear in the vocabulary:
1,024 rows at 226 cycles each, plus 18K to build its 16 tables. A bigger
dictionary is paid for there and nowhere else.

What a row costs is the number to hold on to. A row of 64 ternary inputs
through the sweep is `302 + 8s` cycles, `s` its shift (1 to 5): 22 lookups
at 12 cycles, the shift, the saturation. The classifier's row, blocks of
four and no requant, is 226. A table build is 381 cycles a block, 22 blocks
per input vector.

## Depth vs width

The v0.3 page said *depth costs time, width costs parameters*: every layer
paid again for normalisation, RoPE, softmax and requantisation, about 620K
cycles a layer over and above its multiplies, so a two-layer model of the
same size would have paid that overhead twice instead of five times.

v0.9 shrank the overhead. The part of a layer that does not scale with rows -
two norms, the gate, ReLU², two adds - is about 57K cycles, a quarter of the
layer. The other three quarters are rows: 372 of them a layer at roughly
330 cycles, and `w2`'s pairs. So the accounting changed shape:

- **Depth** costs the whole layer again, 234K, three quarters of it rows.
- **Width** costs rows too. A wider stream adds 12 cycles per three inputs
  to every row and 381 cycles per block to every build; more state or more
  hidden units add whole rows at 302 + 8s each.
- **What is free** is what does not run: the three experts the router did
  not pick, the 82% of ReLU² that is zero, and the logits the classifier
  never stores.

> Rows cost time. Experts cost ROM.

At this kernel, wide against deep is not a rule of thumb any more; it is a
question of bits per character per cycle, and the answer has to be measured
per shape on the twin and the census. `py/fit.py` still prices a shape with
v0.4's costs (10.5 cycles a multiply-accumulate, 203K a layer of overhead);
it has not been refitted to v0.9, which is why the numbers on this page are
the census's and not the price model's.

## Where the numbers come from

- `py/census5.py` — the staged census: the census ROM, one timer per stage,
  8 tokens. The source of every cycle figure above.
- the app ROM's own `CYC/TOK` counter (DIV/TIMA) — the authority for
  seconds per token; 963,792 over 100 tokens with the teletype running.
- `py/score5.py` on `py/twin5.py` — bits per character of what ships.
- `src/sweep.asm`, `src/cls4.asm`, `src/gate.asm`, `src/relu2.asm`,
  `src/rmsnorm.asm`, `src/addsat.asm`, `src/matvec3.asm`,
  `src/matvec_sparse.asm` — each header counts its own loop in M-cycles and
  says how the count squares with the census.
