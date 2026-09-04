"""A synthetic MoE checkpoint for the kernel path, cut from a dense one.

The MoE inference path - router matvec, expert select, an expert's w1 and w2
- is a question about integers before it is a question about quality. This
makes a version-2 PIP5 out of pip7: four experts of half the hidden, each a
slice of the dense FFN, and a ternary router at one power-of-two scale. It
routes arbitrarily and speaks nonsense; the twin and the ROM must agree on
every bit of it.

    python apps/v05/py/moevehicle.py models/pip7.bin models/vehicles/pip7moe.bin
"""

import struct
import sys
from pathlib import Path

import numpy as np

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "py"))
from model5 import Model5     # noqa: E402

EXPERTS = 4


def main():
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    m = Model5(src)
    c = m.cfg
    hid = c.hidden // 2
    rng = np.random.default_rng(7)
    out = bytearray(b"PIP5" + struct.pack("<6H", 2, c.dim, hid, c.layers,
                                         c.vocab, EXPERTS))
    out += np.asarray(m.tok_emb, dtype="<f4").tobytes()
    for l in range(c.layers):
        out += np.asarray(m.rms_att[l], dtype="<f4").tobytes()
        for mat in (m.wz[l], m.wh[l], m.wo[l]):
            out += np.asarray(mat, dtype="<f4").tobytes()
        out += np.asarray(m.rms_ffn[l], dtype="<f4").tobytes()
        # a ternary router, one scale: values in {-0.5, 0, 0.5}
        router = rng.integers(-1, 2, size=(EXPERTS, c.dim)).astype(np.float32) * 0.5
        out += router.astype("<f4").tobytes()
        w1 = np.stack([np.asarray(m.w1[l])[(e % 2) * hid:(e % 2 + 1) * hid]
                       for e in range(EXPERTS)])
        w2 = np.stack([np.asarray(m.w2[l])[:, (e % 2) * hid:(e % 2 + 1) * hid]
                       for e in range(EXPERTS)])
        out += w1.astype("<f4").tobytes()
        out += w2.astype("<f4").tobytes()
    out += np.asarray(m.rms_final, dtype="<f4").tobytes()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(out)
    print(f"wrote {dst} ({len(out):,} bytes): {EXPERTS} experts of {hid}")


if __name__ == "__main__":
    main()
