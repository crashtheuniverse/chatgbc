"""Train a tokenizer on our own corpus, in the format the ROM already reads.

The shipped tok512 was trained on TinyStories. On the conversation corpus it
manages 1.73 characters a token, against the 3.78 a tokenizer fitted to that
corpus reaches - and characters per token divides straight into the only number
a reader feels, seconds per character. A wrong tokenizer is a 2x speed bug that
shows up nowhere in a profile.

The file layout is llama2.c's: a max-token-length int, then (score, length,
bytes) per token. Two conventions inside it are load-bearing, because
`reference.Tokenizer.encode` and `src/encoder.asm` both depend on them:

* Ids 0, 1, 2 are unknown, BOS and EOS. llama2.c then spends 256 more on a byte
  block whose ids are fixed by byte value, so 259 of 512 are gone before a
  single merge - on a corpus using 34 distinct characters. Neither decoder
  actually needs that block: `Tokenizer.encode` and `Enc_Find` in
  src/encoder.asm both look a character up as its own piece first and only fall
  back on a miss. Giving an id only to characters that can occur buys back 222
  slots and a third more characters per token, for no cycles. `--classic`
  restores the old layout.

* Merge scores must be *decreasing* in merge order. The encoder repeatedly
  applies the highest-scoring available merge, so score = -index reproduces
  exactly the order BPE learned them in.

    python py/tokenizer.py --corpus build/friend.txt --out models/tok_pip.bin
    python py/tokenizer.py --corpus build/friend.txt --compare
"""

import argparse
import re
import struct
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every character src/keyboard.asm can produce, whether or not the corpus uses
# one. A typed capital that has no single-byte piece would fall through to the
# `<unk>` path and lose the letter, so the keyboard's alphabet is part of the
# tokenizer's contract, not of the corpus.
KEYBOARD = (b"abcdefghijklmnopqrstuvwxyz"
            b"ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            b" .,!?'-;:" + b'"')

N_SPECIAL = 3          # unk, BOS, EOS
N_BYTES = 256          # the classic fallback block: id of byte b is b + N_SPECIAL
FIRST_MERGE = N_SPECIAL + N_BYTES


def word_counts(text):
    """Words with their leading spaces attached - and newlines on their own.

    Keeping a space inside the token lets " the" be one piece. A newline is the
    opposite case: it is the turn separator, and the ROM needs to *send* one to
    say "the player's turn is over". If "\nhello" were a single piece, a bare
    newline would be a token the model never saw in training - and it was, and
    the model answered "> hi" by continuing the player's sentence with "there"
    instead of replying. One token per line is the price of an unambiguous
    turn protocol.
    """
    counts = Counter()
    lines = text.split("\n")
    counts["\n"] = len(lines) - 1
    for line in lines:
        counts.update(re.findall(r" *[^ ]+", line))
    return counts


def learn_merges(counts, n_merges):
    """BPE over word types weighted by frequency.

    Running merges over the type table rather than the corpus is what makes this
    a second instead of an hour, and the result is identical: a merge inside a
    word never depends on the words around it.
    """
    words = {tuple(bytes([b]) for b in w.encode("utf-8")): n
             for w, n in counts.items()}
    merges = []
    while len(merges) < n_merges:
        pairs = Counter()
        for syms, n in words.items():
            for i in range(len(syms) - 1):
                pairs[syms[i], syms[i + 1]] += n
        if not pairs:
            break
        best = max(pairs.items(), key=lambda kv: (kv[1], kv[0]))[0]
        merges.append(best)
        joined = best[0] + best[1]
        nxt = Counter()
        for syms, n in words.items():
            out, i = [], 0
            while i < len(syms):
                if i < len(syms) - 1 and (syms[i], syms[i + 1]) == best:
                    out.append(joined); i += 2
                else:
                    out.append(syms[i]); i += 1
            nxt[tuple(out)] += n
        words = nxt
    return merges, words


def build(counts, vocab_size, compact=True):
    """Lay out the vocabulary, then learn as many merges as the space allows.

    Two layouts. The classic one keeps llama2.c's 256-entry byte block, whose
    ids are fixed by byte value, and spends 259 of 512 ids before a single
    merge - on a corpus that uses 34 distinct characters. The compact one gives
    an id only to the bytes that occur, which on this corpus buys back 222 slots
    and roughly a third more characters per token, for no cycles at all.

    Compact is safe because neither decoder needs the block. `Tokenizer.encode`
    and `Enc_Find` in src/encoder.asm both look a character up as its own piece
    first and only fall back on a miss - and a miss is now `<unk>` rather than
    an arbitrary merge, which is the correct answer for a byte the model has
    never seen.
    """
    used = sorted({bytes([b]) for w in counts for b in w.encode("utf-8")}
                  | {bytes([b]) for b in KEYBOARD})
    reserved = N_SPECIAL + (len(used) if compact else N_BYTES)
    merges, final = learn_merges(counts, vocab_size - reserved)

    vocab = [b"<unk>", b"<s>", b"</s>"]
    if compact:
        vocab += used
    else:
        # A byte the corpus uses is stored raw, so `lookup[piece]` and the
        # `byte + 3` fallback agree. One it never uses keeps the "<0xNN>"
        # spelling the detokenizer resolves.
        vocab += [bytes([b]) if bytes([b]) in used else f"<0x{b:02X}>".encode()
                  for b in range(N_BYTES)]
    scores = [0.0] * len(vocab)
    for i, (a, b) in enumerate(merges):
        vocab.append(a + b)
        scores.append(float(-i))
    while len(vocab) < vocab_size:                # pad, if the corpus ran dry
        vocab.append(f"<pad{len(vocab)}>".encode())
        scores.append(-1e9)

    tokens = sum(len(syms) * n for syms, n in final.items())
    chars = sum(len(w) * n for w, n in counts.items())
    return vocab, scores, chars / tokens, len(merges), reserved


def write(path, vocab, scores):
    blob = struct.pack("<i", max(len(v) for v in vocab))
    for piece, score in zip(vocab, scores):
        blob += struct.pack("<fi", score, len(piece)) + piece
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    return len(blob)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", type=Path, default=ROOT / "build" / "friend.txt")
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "tok_pip.bin")
    ap.add_argument("--vocab", type=int, default=512)
    ap.add_argument("--classic", action="store_true",
                    help="keep llama2.c's 256-entry byte block, which costs 222 "
                         "ids this corpus never uses")
    ap.add_argument("--compare", action="store_true",
                    help="also report the shipped tokenizer on this corpus")
    args = ap.parse_args()

    text = args.corpus.read_text(encoding="utf-8")
    counts = word_counts(text)
    vocab, scores, cpt, n_merges, reserved = build(
        counts, args.vocab, compact=not args.classic)
    size = write(args.out, vocab, scores)

    print(f"  {args.corpus.name}: {sum(len(w) * n for w, n in counts.items()):,} "
          f"characters, {len(counts):,} word types")
    print(f"  {n_merges} merges of {args.vocab} ids "
          f"({reserved} reserved for specials and characters)")
    print(f"  wrote {args.out} ({size:,} bytes)")
    print(f"  {cpt:.2f} characters/token")

    if args.compare:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import reference as ref
        old = ref.Tokenizer()
        sample = text[:200_000]
        n = len(old.encode(sample, bos=False))
        print(f"  shipped tok512 on the same text: {len(sample) / n:.2f} "
              f"characters/token  ->  {cpt / (len(sample) / n):.2f}x")


if __name__ == "__main__":
    main()
