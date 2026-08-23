"""Operation census: what happens per token, how often, and what drives it.

Counts are structural - derived from the model shape, not measured. Cycle
figures come from docs/LOG.md's stub profile at window 32. The point is the
cycles-per-operation column: it separates "this happens a lot" from "this is
expensive each time", which need completely different fixes.
"""
DIM, HIDDEN, LAYERS = 64, 172, 5
HEADS, KV_HEADS, HEAD = 8, 4, 8
KV_DIM = KV_HEADS * HEAD
VOCAB, WINDOW = 512, 32

# (inputs, outputs) per layer
MATS = [("wq", DIM, DIM), ("wk", DIM, KV_DIM), ("wv", DIM, KV_DIM),
        ("wo", DIM, DIM), ("w1", DIM, HIDDEN), ("w3", DIM, HIDDEN),
        ("w2", HIDDEN, DIM)]

print("\n=== table builds: 2,844 per token, one per input of every matvec ===\n")
print(f"  {'matrix':<8}{'inputs':>8}{'per layer':>11}{'per token':>11}{'cycles':>10}")
tot_b = 0
for name, i, o in MATS:
    tot_b += i * LAYERS
    print(f"  {name:<8}{i:>8}{i:>11}{i*LAYERS:>11}{i*LAYERS*200:>10,}")
print(f"  {'cls':<8}{DIM:>8}{'-':>11}{DIM:>11}{DIM*200:>10,}")
tot_b += DIM
print(f"  {'TOTAL':<8}{'':>8}{'':>11}{tot_b:>11}{tot_b*200:>10,}")
print(f"\n  Depends on the sum of *inputs*, not outputs. w2 alone is "
      f"{HIDDEN*LAYERS/tot_b*100:.0f}% of them, because the FFN is {HIDDEN} wide.")
print("  wq/wk/wv share one input vector; w1/w3 share another. Each group could")
print("  build once instead of three and two times - if they shared a codebook.")
shared = (2*DIM + DIM) * LAYERS
print(f"  That would remove {shared} builds = {shared*200:,} cycles.")

print("\n=== everything that happens per token, by count ===\n")
macs_layer = sum(i*o for _, i, o in MATS) * LAYERS
ops = [
    ("matvec MACs (layers)", macs_layer, "sum(inputs x outputs)", 5_031_616),
    ("matvec MACs (classifier)", VOCAB*DIM, "vocab x dim", 1_236_672),
    ("attention MACs", 2*LAYERS*HEADS*WINDOW*HEAD, "layers x heads x window x head_size",
     828_608 + 2_977_280),
    ("requantizations", sum(o for _, _, o in MATS)*LAYERS + VOCAB, "sum(outputs)", None),
    ("product table builds", tot_b, "sum(inputs)", tot_b*200),
    ("swiglu elements", HIDDEN*LAYERS, "layers x hidden", None),
    ("softmax head-positions", LAYERS*HEADS*WINDOW, "layers x heads x window", 1_790_080),
    ("rmsnorm elements", 2*DIM*LAYERS + DIM, "layers x dim x 2", 1_070_144),
    ("rope pairs", (DIM+KV_DIM)//2*LAYERS, "layers x (dim+kv_dim)/2", 446_208),
    ("residual adds", DIM*2*LAYERS, "layers x dim x 2", 53_952),
]
print(f"  {'operation':<26}{'count':>9}{'cycles':>11}{'cyc/op':>9}  depends on")
for name, n, dep, cyc in sorted(ops, key=lambda r: -r[1]):
    c = f"{cyc:,}" if cyc else "?"
    per = f"{cyc/n:.0f}" if cyc else "?"
    print(f"  {name:<26}{n:>9,}{c:>11}{per:>9}  {dep}")

print("\n  Only two things happen more than 100,000 times: matvec MACs and")
print("  attention MACs. Everything else happens a few thousand times at most -")
print("  and costs hundreds of cycles each. Those are different problems.")
