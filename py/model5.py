"""PIP5 checkpoint loader and the fp32 reference forward.

The format is fixed-order f32, written by py/train.py's save_pip5 and read
here - the only two places that know the layout, both short enough to diff by
eye. See ../DESIGN.md.

The forward is the plain mathematics the trainer optimized:

    per layer:  xn = rmsnorm(x)         z = sigmoid(wz xn)   ht = wh xn
                h  = (1-z) h + z ht     x = x + wo h
                xf = rmsnorm(x)         x = x + w2 relu(w1 xf)^2
    then        logits = emb . rmsnorm(x)

No positions anywhere: order lives in the recurrence. The state h - 64 floats
per layer here, 64 bytes per layer on the cartridge - is the conversation.
"""

import struct
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]        # the repo, not the app
sys.path.insert(0, str(ROOT / "py"))
import reference as _ref                          # noqa: E402  (Tokenizer)

APP = Path(__file__).resolve().parents[1]
Tokenizer = _ref.Tokenizer
UNK, BOS, EOS = _ref.UNK, _ref.BOS, _ref.EOS


@dataclass
class Cfg:
    dim: int
    hidden: int
    layers: int
    vocab: int


class Model5:
    def __init__(self, path):
        blob = Path(path).read_bytes()
        assert blob[:4] == b"PIP5", "not a PIP5 checkpoint"
        ver = struct.unpack_from("<H", blob, 4)[0]
        assert ver in (1, 2), f"PIP5 version {ver}"
        if ver == 1:
            _, dim, hidden, layers, vocab = struct.unpack_from("<5H", blob, 4)
            experts, off = 0, 14
        else:
            # Version 2: experts. `hidden` is per expert; each layer carries a
            # router (experts, dim) and expert-major w1 / w2.
            _, dim, hidden, layers, vocab, experts = struct.unpack_from("<6H", blob, 4)
            off = 16
        self.cfg = Cfg(dim, hidden, layers, vocab)
        self.experts = experts

        def take(*shape):
            nonlocal off
            n = int(np.prod(shape))
            a = np.frombuffer(blob, "<f4", n, off).reshape(shape).astype(np.float64)
            off += 4 * n
            return a

        self.tok_emb = take(vocab, dim)
        self.rms_att, self.wz, self.wh, self.wo = [], [], [], []
        self.rms_ffn, self.w1, self.w2, self.router = [], [], [], []
        for _ in range(layers):
            self.rms_att.append(take(dim))
            self.wz.append(take(dim, dim))
            self.wh.append(take(dim, dim))
            self.wo.append(take(dim, dim))
            self.rms_ffn.append(take(dim))
            if experts:
                self.router.append(take(experts, dim))
                self.w1.append(take(experts, hidden, dim))
                self.w2.append(take(experts, dim, hidden))
            else:
                self.w1.append(take(hidden, dim))
                self.w2.append(take(dim, hidden))
        self.rms_final = take(dim)
        assert off == len(blob), f"{len(blob) - off} trailing bytes"


def rms(x, g, eps=1e-5):
    return g * x / np.sqrt((x * x).mean() + eps)


class State5:
    def __init__(self, cfg):
        self.h = np.zeros((cfg.layers, cfg.dim))


def forward5(m, st, token):
    """One step. No position argument: the state is the only memory."""
    x = m.tok_emb[token].copy()
    for l in range(m.cfg.layers):
        xn = rms(x, m.rms_att[l])
        z = 1.0 / (1.0 + np.exp(-(m.wz[l] @ xn)))
        ht = m.wh[l] @ xn
        st.h[l] = (1.0 - z) * st.h[l] + z * ht
        x = x + m.wo[l] @ st.h[l]
        xf = rms(x, m.rms_ffn[l])
        if m.experts:
            # hard top-1: the router's argmax picks the one expert that runs
            e = int(np.argmax(m.router[l] @ xf))
            x = x + m.w2[l][e] @ np.maximum(m.w1[l][e] @ xf, 0.0) ** 2
        else:
            x = x + m.w2[l] @ np.maximum(m.w1[l] @ xf, 0.0) ** 2
    return m.tok_emb @ rms(x, m.rms_final)


def generate(m, tok, prompt, steps=48):
    st = State5(m.cfg)
    ids = tok.encode(prompt)
    t, out, prev = ids[0], [], None
    for pos in range(steps):
        logits = forward5(m, st, t)
        nxt = ids[pos + 1] if pos + 1 < len(ids) else int(logits.argmax())
        if nxt == EOS:
            break
        out.append(tok.decode(nxt, prev))
        prev, t = nxt, nxt
    return "".join(out)


if __name__ == "__main__":
    import os
    m = Model5(os.environ.get("PIP5", ROOT / "models" / "pip5.bin"))
    tok = Tokenizer()
    print(generate(m, tok, "> hello\n"))
