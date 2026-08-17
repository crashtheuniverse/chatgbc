"""What actually fits in the context window, in characters and tokens."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export as E  # noqa: E402
import reference as ref  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main():
    tok = ref.Tokenizer()
    prompt = "Once upon a time"
    ids = tok.encode(prompt)

    print(f"prompt {prompt!r}: {len(prompt)} chars -> {len(ids)} tokens {ids}")
    prev = None
    for t in ids:
        piece = tok.decode(t, prev)
        name = {1: "<BOS>", 2: "<EOS>"}.get(t, repr(piece))
        print(f"    {t:>4}  {name}")
        prev = t
    content = len(ids) - 1                       # BOS carries no text
    print(f"  {content} content tokens = {len(prompt) / content:.2f} chars/token (prompt)")

    g = json.loads((ROOT / "build" / "golden.json").read_text(encoding="utf-8"))
    text, toks = g["text"], g["tokens"]
    print(f"\ngenerated {len(toks)} tokens -> {len(text)} chars "
          f"= {len(text) / len(toks):.2f} chars/token")

    print(f"\nSEQ_LEN = {E.SEQ} positions (one token each)")
    print(f"  window holds ~{E.SEQ * len(text) / len(toks):.0f} characters of text")
    print(f"  prompt uses {len(ids)} of {E.SEQ}, leaving {E.SEQ - len(ids)} to generate")

    cyc = 11_007_296
    hz = 2_097_152
    print(f"\ncost of restarting by re-prompting the last N tokens:")
    for n in (16, 32, 48):
        print(f"    N={n:>3}: {n * cyc:>12,} cycles = {n * cyc / hz:6.1f} s of dead time")
    print(f"  (a ring buffer costs 0 extra: the window never grows past {E.SEQ})")


if __name__ == "__main__":
    main()
