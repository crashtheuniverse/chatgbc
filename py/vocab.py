"""Price a tokenizer in cycles per character, which is the only figure that matters.

A token is a forward pass. A character is what the reader waits for. So the
tokenizer's job is to buy as many characters per forward pass as it can, and its
cost is the classifier, which is the one part of the model that grows with the
vocabulary:

    cycles(V) = everything else + 64 * V MACs at 37 cycles each

Everything else - five layers, attention, the norms - does not care how many
tokens there are. So the question "why 512 ids?" is not about memory, it is a
trade: a bigger vocabulary costs classifier cycles per token and buys characters
per token. This measures both sides on a real corpus.

    python py/vocab.py --corpus build/corpus.txt
"""

import argparse
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Measured on the shipped ROM: 13,330,010 cycles a token, of which the
# classifier is 64 * 512 MACs at 37 cycles. The remainder is vocabulary-blind.
TOKEN_CYCLES = 13_330_010
CLS_CYCLES_PER_OUT = 64 * 37          # one vocabulary entry's worth of classifier
FIXED_CYCLES = TOKEN_CYCLES - 512 * CLS_CYCLES_PER_OUT
HZ = 2_097_152


def word_counts(text):
    """Words with their leading space attached, the way llama-style BPE sees them.

    Keeping the space inside the token is what lets " the" be one token rather
    than two, and it is worth roughly a character a token on English.
    """
    return Counter(re.findall(r"\s*\S+", text))


def train_bpe(counts, vocab_size, alphabet):
    """Byte-pair merges over unique words weighted by frequency.

    Running the merges over the *word type* table rather than the corpus is what
    makes this tractable: 191 distinct words here against ten million
    characters, and the answer is identical because a merge inside a word is
    independent of the words around it.
    """
    words = {tuple(w): n for w, n in counts.items()}
    merges = []
    target = vocab_size - len(alphabet)
    while len(merges) < target:
        pairs = Counter()
        for syms, n in words.items():
            for i in range(len(syms) - 1):
                pairs[syms[i], syms[i + 1]] += n
        if not pairs:
            break
        best = max(pairs.items(), key=lambda kv: (kv[1], kv[0]))[0]
        merges.append(best)
        joined = best[0] + best[1]
        nxt = {}
        for syms, n in words.items():
            out, i = [], 0
            while i < len(syms):
                if i < len(syms) - 1 and (syms[i], syms[i + 1]) == best:
                    out.append(joined); i += 2
                else:
                    out.append(syms[i]); i += 1
            nxt[tuple(out)] = nxt.get(tuple(out), 0) + n
        words = nxt
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=ROOT / "build" / "corpus.txt")
    ap.add_argument("--sizes", type=int, nargs="*",
                    default=[96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048])
    args = ap.parse_args()

    text = args.corpus.read_text(encoding="utf-8")
    counts = word_counts(text)
    alphabet = sorted({c for w in counts for c in w})
    chars = sum(len(w) * n for w, n in counts.items())
    print(f"  {args.corpus.name}: {chars:,} characters, {len(counts):,} word types, "
          f"{len(alphabet)} character types\n")

    print(f"  {'vocab':>7}{'chars/token':>13}{'cycles/token':>14}"
          f"{'cycles/char':>13}{'s/char':>9}{'vs 512':>9}")
    ref = None
    for v in args.sizes:
        if v <= len(alphabet):
            words = {tuple(w): n for w, n in counts.items()}   # character level
        else:
            words = train_bpe(counts, v, alphabet)
        toks = sum(len(syms) * n for syms, n in words.items())
        cpt = chars / toks
        cyc = FIXED_CYCLES + v * CLS_CYCLES_PER_OUT
        per_char = cyc / cpt
        if v == 512:
            ref = per_char
        print(f"  {v:>7}{cpt:>13.2f}{cyc:>14,.0f}{per_char:>13,.0f}"
              f"{per_char / HZ:>9.2f}", end="")
        print(f"{'' if ref is None else f'{per_char / ref:>8.2f}x'}")


if __name__ == "__main__":
    main()
