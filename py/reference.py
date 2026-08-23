"""Golden float32 reference for TinyStories-260K.

A faithful port of karpathy's llama2.c run.c against the legacy v0 checkpoint
format. This is the oracle: the fixed-point twin in quant.py is checked against
it, and the assembly is in turn checked against the twin.

Checkpoint layout (all float32, after a 7 x int32 header):
    token_embedding (vocab, dim)      rms_att   (L, dim)
    wq (L, dim, dim)                  wk/wv     (L, kv_dim, dim)
    wo (L, dim, dim)                  rms_ffn   (L, dim)
    w1/w3 (L, hidden, dim)            w2        (L, dim, hidden)
    rms_final (dim)                   freq_cis_real/imag  (skipped)
Matrices are stored output-major, matching run.c's matmul(xout, x, w, n, d).
"""

import re
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / "models" / "stories260K.bin"
TOKENIZER = ROOT / "models" / "tok512.bin"

BOS, EOS = 1, 2


@dataclass
class Config:
    dim: int
    hidden_dim: int
    n_layers: int
    n_heads: int
    n_kv_heads: int
    vocab_size: int
    seq_len: int

    @property
    def head_size(self):
        return self.dim // self.n_heads

    @property
    def kv_dim(self):
        return self.head_size * self.n_kv_heads

    @property
    def kv_mul(self):
        return self.n_heads // self.n_kv_heads


class Model:
    def __init__(self, path=CKPT):
        blob = path.read_bytes()
        fields = struct.unpack("<7i", blob[:28])
        shared = fields[5] > 0
        cfg = Config(*fields[:5], abs(fields[5]), fields[6])
        self.cfg = cfg
        c = cfg

        data = np.frombuffer(blob, dtype="<f4", offset=28)
        self._at = 0

        def take(*shape):
            n = int(np.prod(shape))
            out = data[self._at : self._at + n].reshape(shape).astype(np.float32)
            self._at += n
            return out

        self.tok_emb = take(c.vocab_size, c.dim)
        self.rms_att = take(c.n_layers, c.dim)
        self.wq = take(c.n_layers, c.dim, c.dim)
        self.wk = take(c.n_layers, c.kv_dim, c.dim)
        self.wv = take(c.n_layers, c.kv_dim, c.dim)
        self.wo = take(c.n_layers, c.dim, c.dim)
        self.rms_ffn = take(c.n_layers, c.dim)
        self.w1 = take(c.n_layers, c.hidden_dim, c.dim)
        self.w2 = take(c.n_layers, c.dim, c.hidden_dim)
        self.w3 = take(c.n_layers, c.hidden_dim, c.dim)
        self.rms_final = take(c.dim)
        take(c.seq_len, c.head_size // 2)  # freq_cis_real, unused
        take(c.seq_len, c.head_size // 2)  # freq_cis_imag, unused
        self.wcls = self.tok_emb if shared else take(c.vocab_size, c.dim)

        if self._at != data.size:
            raise ValueError(f"checkpoint has {data.size - self._at} trailing floats")


def rmsnorm(x, weight, eps=1e-5):
    ss = np.float32(1.0) / np.sqrt(np.mean(x * x, dtype=np.float32) + np.float32(eps))
    return (weight * (ss * x)).astype(np.float32)


def softmax(x):
    e = np.exp(x - x.max(), dtype=np.float32)
    return (e / e.sum()).astype(np.float32)


def rope(vec, pos, head_size, n_rot):
    """In-place RoPE over the first n_rot entries, computed the way run.c does."""
    for i in range(0, n_rot, 2):
        freq = np.float32(1.0 / (10000.0 ** ((i % head_size) / head_size)))
        val = np.float32(pos) * freq
        fcr, fci = np.cos(val, dtype=np.float32), np.sin(val, dtype=np.float32)
        v0, v1 = vec[i], vec[i + 1]
        vec[i] = v0 * fcr - v1 * fci
        vec[i + 1] = v0 * fci + v1 * fcr


class State:
    """Per-sequence KV cache."""

    def __init__(self, cfg, seq_len=None):
        self.cfg = cfg
        n = seq_len or cfg.seq_len
        self.seq_len = n
        self.k = np.zeros((cfg.n_layers, n, cfg.kv_dim), dtype=np.float32)
        self.v = np.zeros((cfg.n_layers, n, cfg.kv_dim), dtype=np.float32)


def forward(model, state, token, pos):
    """One decode step. Returns logits over the vocabulary."""
    c = model.cfg
    hs, kvm = c.head_size, c.kv_mul
    x = model.tok_emb[token].copy()

    for l in range(c.n_layers):
        xb = rmsnorm(x, model.rms_att[l])
        q = model.wq[l] @ xb
        k = model.wk[l] @ xb
        v = model.wv[l] @ xb

        rope(q, pos, hs, c.dim)
        rope(k, pos, hs, c.kv_dim)
        state.k[l, pos] = k
        state.v[l, pos] = v

        xb2 = np.zeros(c.dim, dtype=np.float32)
        for h in range(c.n_heads):
            qh = q[h * hs : (h + 1) * hs]
            kv = (h // kvm) * hs
            keys = state.k[l, : pos + 1, kv : kv + hs]
            att = softmax((keys @ qh) / np.float32(np.sqrt(hs)))
            vals = state.v[l, : pos + 1, kv : kv + hs]
            xb2[h * hs : (h + 1) * hs] = att @ vals

        x += model.wo[l] @ xb2

        xb = rmsnorm(x, model.rms_ffn[l])
        h1 = model.w1[l] @ xb
        h3 = model.w3[l] @ xb
        hb = (h1 / (np.float32(1.0) + np.exp(-h1, dtype=np.float32)) * h3).astype(np.float32)
        x += model.w2[l] @ hb

    return model.wcls @ rmsnorm(x, model.rms_final)


_BYTE_PIECE = re.compile(rb"<0x([0-9A-Fa-f]{2})>")


class Tokenizer:
    """llama2.c tokenizer.bin: max_len, then (score, len, bytes) per token."""

    def __init__(self, path=TOKENIZER, vocab_size=512):
        blob = path.read_bytes()
        off = 4  # max_token_length
        self.vocab, self.scores = [], []
        for _ in range(vocab_size):
            score, length = struct.unpack_from("<fi", blob, off)
            off += 8
            self.vocab.append(blob[off : off + length])
            self.scores.append(score)
            off += length
        self.lookup = {piece: i for i, piece in enumerate(self.vocab)}

    def encode(self, text, bos=True, eos=False):
        tokens = [BOS] if bos else []
        if text:
            tokens.append(self.lookup[b" "])  # llama2.c's dummy prefix
        for byte in text.encode("utf-8"):
            piece = bytes([byte])
            tokens.append(self.lookup.get(piece, byte + 3))  # byte fallback

        while True:
            best = (-1e10, -1)
            for i in range(len(tokens) - 1):
                merged = self.vocab[tokens[i]] + self.vocab[tokens[i + 1]]
                j = self.lookup.get(merged)
                if j is not None and self.scores[j] > best[0]:
                    best = (self.scores[j], i)
            if best[1] < 0:
                break
            i = best[1]
            tokens[i : i + 2] = [self.lookup[self.vocab[tokens[i]] + self.vocab[tokens[i + 1]]]]

        return tokens + ([EOS] if eos else [])

    def decode(self, token, prev=None):
        if token == BOS and prev is not None:
            return "\n"          # a story separator, not literal "<s>"
        piece = self.vocab[token]
        if prev == BOS and piece.startswith(b" "):
            piece = piece[1:]  # llama2.c strips the space that follows BOS
        m = _BYTE_PIECE.fullmatch(piece)
        if m:  # byte-fallback tokens are spelled "<0x0A>" in the vocab
            piece = bytes([int(m.group(1), 16)])
        return piece.decode("utf-8", errors="replace")


def generate(model, tokenizer, prompt="", steps=64, seq_len=None):
    """Greedy decode. Yields (token, text) pairs."""
    state = State(model.cfg, seq_len)
    prompt_tokens = tokenizer.encode(prompt)
    token, prev = prompt_tokens[0], None

    for pos in range(min(steps, state.seq_len)):
        logits = forward(model, state, token, pos)
        nxt = prompt_tokens[pos + 1] if pos + 1 < len(prompt_tokens) else int(logits.argmax())
        if nxt == EOS:
            break
        yield nxt, tokenizer.decode(nxt, token)
        prev, token = token, nxt


if __name__ == "__main__":
    import sys

    model, tok = Model(), Tokenizer()
    c = model.cfg
    print(
        f"dim={c.dim} hidden={c.hidden_dim} layers={c.n_layers} heads={c.n_heads} "
        f"kv_heads={c.n_kv_heads} vocab={c.vocab_size} seq_len={c.seq_len} "
        f"head_size={c.head_size} kv_dim={c.kv_dim}"
    )
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Once upon a time"
    print(f"\nprompt {prompt!r}\n")

    chars = tokens = 0
    for _, text in generate(model, tok, prompt, steps=96, seq_len=64):
        print(text, end="", flush=True)
        chars += len(text)
        tokens += 1
    print(f"\n\n{tokens} tokens, {chars} chars, {chars / tokens:.2f} chars/token")
