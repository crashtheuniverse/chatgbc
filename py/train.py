"""Train a model for the cartridge, quantization-aware, on one laptop GPU.

It writes a checkpoint in llama2.c's legacy v0 format - the same layout
py/reference.py already reads - so nothing downstream changes. The exporter,
the twin, the golden and the ROM all work on the result without modification.
That is the whole reason for matching the format rather than inventing one.

    python py/train.py --corpus build/corpus.txt --steps 3000
    python py/train.py --dim 96 --layers 2 --hidden 256    # a wide candidate

**Quantization-aware from the start**, because the model has to survive 4-bit
weights and the ROM is where it runs. Weights are fake-quantized in the forward
pass - rounded to the grid the exporter will use - with a straight-through
estimator on the backward pass. Training a float model and quantizing afterwards
is what put a floor at 4 bits; this is the way past it.

Shape is chosen with py/arch.py, which costs a candidate in cycles before a GPU
hour is spent on it. Quality is judged with py/eval.py.
"""

import argparse
import math
import re
import struct
import sys
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arch  # noqa: E402
import reference as ref  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
_WORD = re.compile(r" *[^ ]+")      # py/tokenizer.py's word type, spaces in front


# --- quantization-aware weights ---------------------------------------------

class FakeQuant(torch.autograd.Function):
    """Round to the exporter's grid going forward, pass the gradient straight
    through going back.

    Without the straight-through estimator the gradient is zero almost
    everywhere and nothing learns. With it the model sees exactly the weights
    the cartridge will use, and learns around their coarseness instead of being
    damaged by it afterwards.
    """

    @staticmethod
    def forward(ctx, w, levels):
        if levels <= 0:
            return w
        if levels == TERNARY_ONE:
            # Ternary with ONE power-of-two scale for the whole tensor: the
            # classifier's regime, so argmax over block sums needs no per-row
            # rescale on the cartridge. The tied embedding shares it.
            scale = w.abs().mean().clamp(min=1e-8)
            scale = torch.exp2(torch.round(torch.log2(scale)))
            return torch.round(w / scale).clamp(-1, 1) * scale
        if levels == SHERRY:
            # Sherry (Huang et al., arXiv 2601.07892): ternary with exactly one
            # zero per block of four - the smallest-magnitude weight - and the
            # other three at +-1, scaled per output row by the mean magnitude
            # of what was kept. 32 patterns per block is 5 bits a block, and on
            # the cartridge it is a 32-entry table of block sums per four
            # activations: the product-table trick retiring four MACs a lookup,
            # with activations left at int8.
            out, inn = w.shape
            g = w.view(out, inn // 4, 4)
            drop = g.abs().argmin(dim=-1, keepdim=True)
            keep = torch.ones_like(g, dtype=torch.bool).scatter_(-1, drop, False)
            kept = g.abs() * keep
            scale = (kept.sum(dim=(1, 2), keepdim=True)
                     / keep.sum(dim=(1, 2), keepdim=True).clamp(min=1))
            return (torch.sign(g) * keep * scale).view(out, inn)
        if levels <= 3:
            # One and 1.58 bits. The scale is the mean magnitude rather than the
            # max, which is what BitNet uses and what makes it work: with two or
            # three levels a single outlier would otherwise set the scale for
            # the whole row and collapse everything else onto zero.
            scale = w.abs().mean(dim=-1, keepdim=True).clamp(min=1e-8)
            if POW2_SCALE["on"]:
                # The cartridge rescales by shifting, so a per-row scale it
                # can apply for free is a power of two. Constrain it here and
                # the model learns to live on that grid, instead of paying a
                # multiply per output row at inference.
                scale = torch.exp2(torch.round(torch.log2(scale)))
            q = torch.round(w / scale).clamp(-1, 1) if levels == 3 else torch.sign(w)
            return q * scale
        # Per-output-row scale, matching what quant.py does.
        scale = w.abs().amax(dim=-1, keepdim=True).clamp(min=1e-8) / (levels // 2)
        return torch.round(w / scale).clamp(-(levels // 2), levels // 2 - 1) * scale

    @staticmethod
    def backward(ctx, g):
        return g, None


class FakeQuantAct(torch.autograd.Function):
    """The same idea for activations, which the bit kernel cares about as much
    as the weights.

    One-bit weights buy 8.5x only if the activation is narrow too: the kernel
    decomposes an activation into bit planes and runs one pass per plane, so
    k-bit activations cost k times the base. At eight bits that is 17.8
    cycles/MAC and the whole advantage is gone. The question this exists to
    answer is how few bits an activation can carry and still train.
    """

    @staticmethod
    def forward(ctx, x, bits):
        n = (1 << (bits - 1)) - 1
        scale = x.abs().amax(dim=-1, keepdim=True).clamp(min=1e-8) / n
        ctx.save_for_backward(x, scale * n)
        return torch.round(x / scale).clamp(-n - 1, n) * scale

    @staticmethod
    def backward(ctx, g):
        # Straight-through, but clipped: a gradient pushing an activation
        # further outside the representable range is pushing somewhere the
        # forward pass cannot follow.
        x, limit = ctx.saved_tensors
        return g * (x.abs() <= limit), None


class StreamQuant(torch.autograd.Function):
    """The residual stream, as the cartridge stores it: int8 on a FIXED grid.

    The ROM keeps x as int8 with one exponent for the whole run, so every value
    in the stream - the embedding at layer 0 and the sum after layer 5 - shares
    a single 127-step window. The first conversation model trained without this
    constraint grew its stream to |x| = 233 against an embedding of 2.5, and
    quantization then rounded the embedding to one step: the model went from
    100% intent accuracy in float to emitting <unk> forever on the cartridge.

    A per-token scale cannot catch that - the damage is the *ratio between
    layers*, which only a fixed grid sees. Clamping at +-CLIP with a
    straight-through gradient (zeroed outside the clamp, where the forward
    cannot follow) makes the model live inside the window from step one.
    """
    CLIP = 16.0
    STEP = CLIP / 127

    @staticmethod
    def forward(ctx, x):
        ctx.save_for_backward(x)
        return torch.clamp(torch.round(x / StreamQuant.STEP),
                           -127, 127) * StreamQuant.STEP

    @staticmethod
    def backward(ctx, g):
        (x,) = ctx.saved_tensors
        return g * (x.abs() <= StreamQuant.CLIP)


def qs(x, on=True):
    return StreamQuant.apply(x) if on else x


SHERRY = 34               # the `levels` value meaning Sherry's 3:4 ternary
TERNARY_ONE = 35          # ternary, one power-of-two scale for the whole tensor
POW2_SCALE = {"on": False}   # ternary row scales snapped to powers of two

# Arenas (same paper): during training the quantized weight is augmented with
# a decaying full-precision residual, W_eff = Q(W) + lambda_t * W, lambda
# annealed to zero. It exists to break "weight trapping" - with structured
# zeros the gradient reaching the input homogenizes and latent weights stop
# differentiating. Zero cost at inference; the trainer owns the schedule and
# must set lambda to 0 before any grading, so what is graded is what ships.
ARENAS = {"lam": 0.0}


def qw(w, levels):
    q = FakeQuant.apply(w, levels)
    lam = ARENAS["lam"]
    if lam > 0.0 and levels in (2, 3, SHERRY):
        return q + lam * w
    return q


def qa(x, bits):
    # The disabled case skips the autograd Function entirely rather than
    # returning early inside it: an early return saves no tensors, and backward
    # is still called.
    if bits <= 0 or bits >= 16:
        return x
    return FakeQuantAct.apply(x, bits)


# --- the model, matching reference.py exactly -------------------------------

def sliding_mask(T, window, device):
    """The attention pattern the cartridge actually runs.

    The ROM keeps SEQ_LEN key/value slots in a ring, so position i attends to
    positions i-SEQ_LEN+1 through i and to nothing before that. Training with
    full causal attention teaches the model to rely on evidence it will not have
    at inference - it learns to carry information from forty tokens back, and
    then that information is simply gone. Matching the mask is free and removes
    the mismatch entirely.

    RoPE needs no equivalent fix: q_i . k_j depends only on i - j, so rotating
    by absolute position gives the same scores wherever the window sits.
    """
    i = torch.arange(T, device=device)
    delta = i[:, None] - i[None, :]
    return (delta >= 0) & (delta < window)


class Attention(nn.Module):
    def __init__(self, c, levels, act_bits=0):
        super().__init__()
        self.c, self.levels, self.act_bits = c, levels, act_bits
        self.wq = nn.Linear(c.dim, c.dim, bias=False)
        self.wk = nn.Linear(c.dim, c.kv_dim, bias=False)
        self.wv = nn.Linear(c.dim, c.kv_dim, bias=False)
        self.wo = nn.Linear(c.dim, c.dim, bias=False)

    def forward(self, x, cos, sin, mask=None):
        B, T, _ = x.shape
        c = self.c
        x = qa(x, self.act_bits)
        q = F.linear(x, qw(self.wq.weight, self.levels)).view(B, T, c.heads, c.head_size)
        k = F.linear(x, qw(self.wk.weight, self.levels)).view(B, T, c.kv_heads, c.head_size)
        v = F.linear(x, qw(self.wv.weight, self.levels)).view(B, T, c.kv_heads, c.head_size)

        q, k = rope(q, cos, sin), rope(k, cos, sin)
        rep = c.heads // c.kv_heads
        k = k.repeat_interleave(rep, dim=2)
        v = v.repeat_interleave(rep, dim=2)

        y = F.scaled_dot_product_attention(
            q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2),
            attn_mask=mask, is_causal=mask is None)
        y = y.transpose(1, 2).reshape(B, T, c.dim)
        return F.linear(qa(y, self.act_bits), qw(self.wo.weight, self.levels))


def rope(t, cos, sin):
    T = t.shape[1]
    a, b = t[..., 0::2], t[..., 1::2]
    co, si = cos[:T, None, :], sin[:T, None, :]
    return torch.stack([a * co - b * si, a * si + b * co], dim=-1).flatten(-2)


class MinGRU(nn.Module):
    """The O(1) core: h_t = (1 - z_t) * h_t-1 + z_t * htilde_t.

    Gates depend only on the input ("Were RNNs All We Needed?", 2024), so the
    recurrence is linear, and at inference the whole core costs three d x d
    matvecs per layer - no KV cache, no ring, no softmax over positions, flat
    cost at any conversation length. wz + wh + wo is 3 * d^2 = 12,288
    parameters: exact parity with attention's wq..wo at this shape, so the
    comparison is of shape, not of size.
    """

    def __init__(self, c, levels, act_bits=0, state_bits=None,
                 gate_levels=None):
        super().__init__()
        self.levels, self.act_bits = levels, act_bits
        # wz and wh decide what the state holds. Sherry's forced zero in every
        # block of four killed recall there while costing nothing in loss, so
        # the gates may keep a different precision from the bulk.
        self.gate_levels = levels if gate_levels is None else gate_levels
        # The state is not a matvec input. The bit kernel's price depends only
        # on the width of what walks into a matvec; the recurrence updates in
        # whatever width the gate arithmetic keeps - int8 on the cartridge.
        # Quantizing h to act_bits crushed recall to 0/12 at 8,000 steps: 16
        # levels per dim cannot carry a name. The ROM never did that; the lab
        # must not either.
        self.state_bits = act_bits if state_bits is None else state_bits
        self.wz = nn.Linear(c.dim, c.dim, bias=False)
        self.wh = nn.Linear(c.dim, c.dim, bias=False)
        self.wo = nn.Linear(c.dim, c.dim, bias=False)

    def forward(self, x, cos, sin, mask=None):
        x = qa(x, self.act_bits)
        z = torch.sigmoid(F.linear(x, qw(self.wz.weight, self.gate_levels)))
        ht = F.linear(x, qw(self.wh.weight, self.gate_levels))
        if self.act_bits == 0:
            # Hillis-Steele scan over the whole sequence: seven doubling steps
            # for T=96 instead of ninety-six sequential ones. The combine is
            # (a_l, b_l) then (a_r, b_r) = (a_l * a_r, b_l * a_r + b_r) -
            # multiplications of gates that never exceed one, so it cannot
            # overflow. The first chunked version divided by cumulative gate
            # products and went NaN the moment a fresh model saturated its
            # gates; division has no place in a scan whose factors shrink.
            #
            # Float-state only: the int8-state regime quantizes the carried
            # state each step, which is nonlinear, and keeps the sequential
            # path below.
            A = 1 - z
            Bv = z * ht
            step = 1
            while step < ht.shape[1]:
                a_r = A[:, step:]
                new_b = Bv[:, :-step] * a_r + Bv[:, step:]
                new_a = A[:, :-step] * a_r
                A = torch.cat([A[:, :step], new_a], dim=1)
                Bv = torch.cat([Bv[:, :step], new_b], dim=1)
                step *= 2
            return F.linear(Bv, qw(self.wo.weight, self.levels))
        hs, h = [], torch.zeros_like(ht[:, 0])
        for t in range(ht.shape[1]):        # sequential scan under state quant
            h = (1 - z[:, t]) * h + z[:, t] * ht[:, t]
            # The cartridge carries this state in int8 and re-quantizes it
            # every token. A recurrence accumulates that rounding in a way
            # attention - which re-reads clean cache entries - never does, so
            # the training has to live with it too or the ROM inherits a gap
            # no calibration can close. state_bits, not act_bits: the wo
            # matvec reads a narrowed view below, but the carried state keeps
            # the ROM's own width.
            h = qa(h, self.state_bits)
            hs.append(h)
        y = torch.stack(hs, dim=1)
        return F.linear(qa(y, self.act_bits), qw(self.wo.weight, self.levels))


class MoEMLP(nn.Module):
    """Micro mixture of experts, sized for a machine that switches banks for
    free: E experts of half the dense hidden, hard top-1 at inference. Per
    token the MLP costs the router (D x E, negligible) plus ONE expert - half
    the dense MACs - while the parameter count is E/2 times the dense MLP.
    More weights, fewer cycles: the ROM's version selects the expert's weight
    bank, which is one MBC5 register write.

    Training is switch-style: hard top-1 forward, gradient flowing through the
    selected expert scaled by its router probability, and the standard load
    balancing auxiliary so experts share the work.
    """

    def __init__(self, c, levels, act_bits, n_exp=4):
        super().__init__()
        self.levels, self.act_bits, self.n_exp = levels, act_bits, n_exp
        hid = c.hidden // 2
        self.router = nn.Linear(c.dim, n_exp, bias=False)
        self.w1 = nn.Parameter(torch.randn(n_exp, hid, c.dim) * 0.05)
        self.w2 = nn.Parameter(torch.randn(n_exp, c.dim, hid) * 0.05)
        self.last_aux = 0.0

    def forward(self, h):
        # The router is quantized like the classifier - ternary at one scale
        # per tensor - whenever the experts are ternary, so the cartridge's
        # exact block sums reproduce the argmax the model trained with. A
        # fp32 router quantized after the fact would route differently.
        rw = (qw(self.router.weight, TERNARY_ONE) if self.levels <= 3
              else self.router.weight)
        r = torch.softmax(F.linear(h, rw), dim=-1)          # (B,T,E)
        idx = r.argmax(-1)
        w1 = qw(self.w1, self.levels)
        w2 = qw(self.w2, self.levels)
        u = torch.relu(torch.einsum("btd,ehd->bteh", h, w1)) ** 2
        y = torch.einsum("bteh,edh->bted", qa(u, self.act_bits), w2)
        sel = torch.nn.functional.one_hot(idx, self.n_exp).to(y.dtype)
        gate = r.gather(-1, idx.unsqueeze(-1))
        out = (y * sel.unsqueeze(-1)).sum(2) * gate
        self.last_aux = float(self.n_exp) * (
            sel.mean(dim=(0, 1)) * r.mean(dim=(0, 1))).sum()
        return out


class Block(nn.Module):
    def __init__(self, c, levels, act_bits=0, core="attn", mlp="swiglu",
                 state_bits=None, gate_levels=None):
        super().__init__()
        self.levels, self.act_bits, self.mlp = levels, act_bits, mlp
        self.stream_q = True
        self.rms_att = nn.Parameter(torch.ones(c.dim))
        self.attn = (Attention(c, levels, act_bits) if core == "attn"
                     else MinGRU(c, levels, act_bits, state_bits, gate_levels))
        self.rms_ffn = nn.Parameter(torch.ones(c.dim))
        if mlp != "moe4":
            self.w1 = nn.Linear(c.dim, c.hidden, bias=False)
            self.w2 = nn.Linear(c.hidden, c.dim, bias=False)
        if mlp == "swiglu":                 # relu2 has no gate branch at all
            self.w3 = nn.Linear(c.dim, c.hidden, bias=False)
        if mlp == "moe4":
            self.moe = MoEMLP(c, levels, act_bits)

    def forward(self, x, cos, sin, mask=None):
        x = qs(x + self.attn(rmsnorm(x, self.rms_att), cos, sin, mask),
               self.stream_q)
        h = qa(rmsnorm(x, self.rms_ffn), self.act_bits)
        if self.mlp == "moe4":
            return qs(x + self.moe(h), self.stream_q)
        if self.mlp == "relu2":
            # modded-nanoGPT's activation: on an SM83 a square is one
            # quarter-square lookup where silu is a sigmoid LUT and a
            # generic multiply - and the whole w3 gate matrix vanishes.
            up = F.relu(F.linear(h, qw(self.w1.weight, self.levels))) ** 2
            return qs(x + F.linear(qa(up, self.act_bits),
                                   qw(self.w2.weight, self.levels)), self.stream_q)
        gate = F.silu(F.linear(h, qw(self.w1.weight, self.levels)))
        up = F.linear(h, qw(self.w3.weight, self.levels))
        return qs(x + F.linear(qa(gate * up, self.act_bits),
                               qw(self.w2.weight, self.levels)), self.stream_q)


def rmsnorm(x, w, eps=1e-5):
    return w * x * torch.rsqrt(x.pow(2).mean(-1, keepdim=True) + eps)


class Tiny(nn.Module):
    def __init__(self, shape: arch.Shape, levels=16, seq=256, window=None,
                 act_bits=0, core="attn", mlp="swiglu", state_bits=None,
                 gate_levels=None, emb_levels=256):
        super().__init__()
        self.c, self.seq, self.window = shape, seq, window
        self.core_mlp = (core, mlp)
        self.levels, self.act_bits = levels, act_bits
        self.emb_levels = emb_levels          # the tied embedding / classifier
        self.tok_emb = nn.Embedding(shape.vocab, shape.dim)
        self.blocks = nn.ModuleList(Block(shape, levels, act_bits, core, mlp,
                                          state_bits, gate_levels)
                                    for _ in range(shape.layers))
        self.rms_final = nn.Parameter(torch.ones(shape.dim))
        cos, sin = rope_tables(seq, shape.head_size)
        self.register_buffer("cos", cos, persistent=False)
        self.register_buffer("sin", sin, persistent=False)

    def forward(self, idx, targets=None):
        emb = qw(self.tok_emb.weight, self.emb_levels)
        x = qs(F.embedding(idx, emb))
        mask = (sliding_mask(idx.shape[1], self.window, idx.device)
                if self.window else None)
        for b in self.blocks:
            x = b(x, self.cos, self.sin, mask)
        x = rmsnorm(x, self.rms_final)
        # Tied classifier, as the checkpoint format expects: the same
        # quantized image serves the lookup and the logits.
        logits = F.linear(x, emb)
        if targets is None:
            return logits
        loss = F.cross_entropy(
            logits.view(-1, logits.size(-1)), targets.reshape(-1))
        aux = sum(getattr(b, "moe").last_aux for b in self.blocks
                  if hasattr(b, "moe"))
        return logits, loss + 0.01 * aux


def rope_tables(seq, head_size):
    inv = 1.0 / (10000.0 ** (torch.arange(0, head_size, 2).float() / head_size))
    t = torch.arange(seq).float()
    f = torch.outer(t, inv)
    return torch.cos(f), torch.sin(f)


# --- checkpoint, in the format reference.py already reads -------------------

def save_pip5(model: Tiny, path: Path):
    """The PIP5 checkpoint: our own format, because llama2.c's cannot hold a
    minGRU. Fixed tensor order, documented in apps/v05/DESIGN.md - the loader
    and this writer are the only two places that know it, and both are short
    enough to diff by eye.

    header: magic 'PIP5', u16 version, u16 dim, hidden, layers, vocab
    then, f32 little-endian, in this exact order:
      tok_emb (vocab, dim)
      per layer: rms_att(dim), wz(dim,dim), wh(dim,dim), wo(dim,dim),
                 rms_ffn(dim), w1(hidden,dim), w2(dim,hidden)
      rms_final(dim)
    """
    c = model.c
    core, mlp = model.core_mlp
    assert core == "mingru" and mlp in ("relu2", "moe4"), "PIP5 holds minGRU shapes"
    parts = [model.tok_emb.weight]
    if mlp == "relu2":
        blob = b"PIP5" + struct.pack("<5H", 1, c.dim, c.hidden, c.layers, c.vocab)
        for b in model.blocks:
            parts += [b.rms_att, b.attn.wz.weight, b.attn.wh.weight,
                      b.attn.wo.weight, b.rms_ffn, b.w1.weight, b.w2.weight]
    else:
        # Version 2: experts. `hidden` is the per-expert hidden, and each
        # layer carries the router (experts, dim), then w1 (experts, hidden,
        # dim) and w2 (experts, dim, hidden), expert-major.
        moe = model.blocks[0].moe
        blob = b"PIP5" + struct.pack("<6H", 2, c.dim, moe.w1.shape[1], c.layers,
                                     c.vocab, moe.n_exp)
        for b in model.blocks:
            parts += [b.rms_att, b.attn.wz.weight, b.attn.wh.weight,
                      b.attn.wo.weight, b.rms_ffn, b.moe.router.weight,
                      b.moe.w1, b.moe.w2]
    parts.append(model.rms_final)
    blob += b"".join(p.detach().float().cpu().numpy().astype("<f4").tobytes()
                     for p in parts)
    path.write_bytes(blob)
    return len(blob)


def save_checkpoint(model: Tiny, path: Path, seq_len):
    c = model.c
    # A *positive* vocab size is what flags a tied classifier here - llama2.c
    # uses the sign the other way round and reference.py follows this loader.
    hdr = struct.pack("<7i", c.dim, c.hidden, c.layers, c.heads, c.kv_heads,
                      c.vocab, seq_len)

    def stack(name):
        return torch.stack([getattr(b, name) if hasattr(b, name)
                            else getattr(b.attn, name).weight
                            for b in model.blocks])

    parts = [
        model.tok_emb.weight,
        stack("rms_att"),
        stack("wq"), stack("wk"), stack("wv"), stack("wo"),
        stack("rms_ffn"),
        torch.stack([b.w1.weight for b in model.blocks]),
        torch.stack([b.w2.weight for b in model.blocks]),
        torch.stack([b.w3.weight for b in model.blocks]),
        model.rms_final,
        torch.zeros(seq_len, c.head_size // 2),   # freq_cis_real, unused
        torch.zeros(seq_len, c.head_size // 2),   # freq_cis_imag, unused
    ]
    blob = hdr + b"".join(
        p.detach().float().cpu().numpy().astype("<f4").tobytes() for p in parts)
    path.write_bytes(blob)
    return len(blob)


# --- data -------------------------------------------------------------------

def load_tokens(corpus: Path, tok):
    """Tokenize per story, not in one piece.

    The reference tokenizer rescans every pair on every merge, so it is
    quadratic: 4.2k chars/s at 5 KB and 1.1k at 20 KB. On a 9.7 MB corpus that
    is days. One story at a time it runs at 112k chars/s - a minute and a half -
    because n is 200 characters instead of ten million.

    It is also the right unit. Each document gets its own BOS, and merges do not
    reach across a story boundary into the next one.
    """
    # Keyed on the tokenizer as well as the corpus. The same text under a
    # different tokenizer is different training data, and a stale cache would
    # silently train the new model on the old tokenization.
    cache = corpus.with_suffix(f".{ref.TOKENIZER.stem}.tokens.npy")
    newest = max(corpus.stat().st_mtime, ref.TOKENIZER.stat().st_mtime)
    if cache.exists() and cache.stat().st_mtime > newest:
        return np.load(cache)
    text = corpus.read_text(encoding="utf-8")
    stories = [s for s in text.split("\n\n") if s.strip()]
    out, t0 = [], time.time()
    # Word-level memoization, exact by construction: every piece the
    # tokenizer learned carries its spaces in front (py/tokenizer.py learns
    # merges inside " *[^ ]+" word types), so no merge can cross from one
    # word into the next, and a line's encoding is its words' encodings in
    # order. The dummy prefix llama2.c puts before a text is one space, so a
    # first word is encoded as if it had one. The newline is its own token,
    # so a story is BOS + its lines joined by it. Checked against whole-line
    # encoding on the first 300 stories every run, because "exact by
    # construction" is a claim about the tokenizer's training, not a law.
    # On 200 MB of TinyStories this is minutes instead of hours.
    nl_id = tok.lookup["\n".encode()]
    memo = {}

    def encode_line(line, first):
        ws = _WORD.findall(line)
        if first and ws:
            ws[0] = " " + ws[0]
        ids = []
        for w in ws:
            got = memo.get(w)
            if got is None:
                got = memo[w] = tok.encode(w, bos=False, prefix=False)
            ids.extend(got)
        return ids

    for n, s in enumerate(stories, 1):
        out.append(ref.BOS)
        for i, line in enumerate(s.split("\n")):
            ids = encode_line(line, i == 0)
            if n <= 300:
                assert ids == tok.encode(line, bos=False, prefix=(i == 0)), \
                    "a merge crossed a word boundary; this tokenizer needs the slow path"
            if i:
                out.append(nl_id)
            out.extend(ids)
        if n % 25000 == 0:
            print(f"    tokenizing {n:,}/{len(stories):,} "
                  f"({time.time() - t0:.0f}s, {len(memo):,} distinct words)",
                  flush=True)
    ids = np.array(out, dtype=np.int32)
    np.save(cache, ids)
    print(f"    {len(stories):,} stories -> {len(ids):,} tokens "
          f"in {time.time() - t0:.0f}s")
    return ids


def batches(ids, batch, seq, device, seed=0):
    """One gather on the device, not `batch` slices on the host.

    The corpus is 29M tokens - 116 MB as int32 - so it lives on the GPU and a
    batch is a single fancy-index into it. The previous version built every
    batch from `batch` separate numpy slices, a `from_numpy` each, and a stack,
    all on the CPU; at batch 96 that starved the GPU badly enough to leave it
    at a third utilization and turn a six-minute run into hours.
    """
    g = torch.Generator(device=device).manual_seed(seed)
    flat = torch.from_numpy(ids.astype(np.int32)).to(device)
    span = torch.arange(seq + 1, device=device)
    hi = len(ids) - seq - 1
    while True:
        i = torch.randint(hi, (batch,), generator=g, device=device)
        chunk = flat[i[:, None] + span].long()
        yield chunk[:, :-1], chunk[:, 1:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=ROOT / "build" / "corpus.txt")
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "trained.bin")
    ap.add_argument("--dim", type=int, default=64)
    ap.add_argument("--hidden", type=int, default=172)
    ap.add_argument("--layers", type=int, default=5)
    ap.add_argument("--heads", type=int, default=8)
    ap.add_argument("--kv-heads", type=int, default=4)
    ap.add_argument("--core", default="attn", choices=["attn", "mingru"])
    ap.add_argument("--mlp", default="swiglu", choices=["swiglu", "relu2"])
    ap.add_argument("--act-bits", type=int, default=0,
                    help="activation width; 0 leaves them float. The bit kernel "
                         "costs one pass per activation bit, so this is the "
                         "other half of what one-bit weights are worth.")
    ap.add_argument("--levels", type=int, default=16,
                    help="weight levels seen in the forward pass; 0 disables")
    ap.add_argument("--seq", type=int, default=128)
    ap.add_argument("--window", type=int, default=0,
                    help="attention window; 0 trains full causal. Set it to the "
                         "ROM's SEQ_LEN so training sees what inference sees.")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--steps", type=int, default=2000)
    ap.add_argument("--lr", type=float, default=3e-3)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    # A run has to be repeatable, or a measurement of it means nothing.
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    tok = ref.Tokenizer()
    ids = load_tokens(args.corpus, tok)
    shape = arch.Shape(dim=args.dim, hidden=args.hidden, layers=args.layers,
                       heads=args.heads, kv_heads=args.kv_heads, vocab=512)

    print(f"  corpus {len(ids):,} tokens   device {device}")
    print(f"  shape dim {shape.dim}, hidden {shape.hidden}, {shape.layers} layers, "
          f"{shape.params():,} parameters")
    print(f"  predicted {sum(arch.cost(shape).values()):,} cycles/token "
          f"({sum(arch.cost(shape).values()) / arch.CYCLES_PER_SECOND:.2f} s/token)")

    if args.window:
        print(f"  attention window {args.window}, as the ROM runs it")
    model = Tiny(shape, levels=args.levels, seq=args.seq,
                 window=args.window or None, act_bits=args.act_bits,
                 core=args.core, mlp=args.mlp).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01,
                            betas=(0.9, 0.95))
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=args.lr, total_steps=args.steps, pct_start=0.1)

    t0 = time.time()
    stream = batches(ids, args.batch, args.seq, device, seed=args.seed)
    for step in range(1, args.steps + 1):
        x, y = next(stream)
        _, loss = model(x, y)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        sched.step()
        if step % 100 == 0 or step == 1:
            print(f"  step {step:>5}/{args.steps}  loss {loss.item():.4f}  "
                  f"({loss.item() / math.log(2):.3f} bits)  "
                  f"{time.time() - t0:6.1f}s", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if getattr(model, "core_mlp", ("attn", "swiglu")) == ("mingru", "relu2"):
        n = save_pip5(model, args.out)
        print(f"\n  wrote {args.out} ({n:,} bytes) in PIP5 format")
        return
    n = save_checkpoint(model, args.out, args.seq)
    print(f"\n  wrote {args.out} ({n:,} bytes) in llama2.c v0 format")
    print("  next: point reference.CKPT at it, then py/export.py and py/eval.py")


if __name__ == "__main__":
    main()
