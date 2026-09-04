"""Make a ternary vehicle out of any PIP5 checkpoint, for kernel work.

The block kernel's correctness is a question about integers, not about a
model's quality, so it should not wait for a trained ternary checkpoint.
This takes pip6 and rewrites every matrix as the trainer's ternary-with-
power-of-two-row-scale quantizer would - each row in {-a, 0, +a} with a a
power of two - and writes it back in PIP5 form. The twin then quantizes it
losslessly, and the ROM has to agree with the twin to the bit.

    python apps/v05/py/ternarize.py models/pip6.bin models/vehicles/pip6t.bin
"""

import struct
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "py"))
from model5 import Model5     # noqa: E402


def ternary_pow2(w):
    """train.FakeQuant's ternary branch with POW2_SCALE on, in numpy."""
    scale = np.abs(w).mean(axis=1, keepdims=True).clip(min=1e-8)
    scale = np.exp2(np.round(np.log2(scale)))
    t = np.clip(np.round(w / scale), -1, 1)
    return (t * scale).astype(np.float32)


def ternary_one_scale(w):
    """The classifier's regime: one power-of-two scale for the whole tensor,
    so argmax over the block sums needs no per-row rescale."""
    scale = np.exp2(np.round(np.log2(np.abs(w).mean().clip(min=1e-8))))
    t = np.clip(np.round(w / scale), -1, 1)
    return (t * scale).astype(np.float32)


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    with_cls = "--cls" in sys.argv[3:]
    m = Model5(src)
    c = m.cfg
    out = bytearray(b"PIP5" + struct.pack("<5H", 1, c.dim, c.hidden, c.layers,
                                         c.vocab))
    emb = np.asarray(m.tok_emb)
    if with_cls:
        emb = ternary_one_scale(emb)              # tied: classifier and embedding
    out += emb.astype("<f4").tobytes()
    for l in range(c.layers):
        out += np.asarray(m.rms_att[l], dtype="<f4").tobytes()
        for mat in (m.wz[l], m.wh[l], m.wo[l]):
            out += ternary_pow2(np.asarray(mat)).astype("<f4").tobytes()
        out += np.asarray(m.rms_ffn[l], dtype="<f4").tobytes()
        out += ternary_pow2(np.asarray(m.w1[l])).astype("<f4").tobytes()
        out += ternary_pow2(np.asarray(m.w2[l])).astype("<f4").tobytes()
    out += np.asarray(m.rms_final, dtype="<f4").tobytes()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(out)
    t = ternary_pow2(np.asarray(m.w1[0]))
    levels = sorted(set(np.unique(t / np.abs(t).max(axis=1, keepdims=True)
                                  .clip(min=1e-9)).round(3)))
    print(f"wrote {dst} ({len(out):,} bytes); w1[0] levels {levels}")


if __name__ == "__main__":
    main()
