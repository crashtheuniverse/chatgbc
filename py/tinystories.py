"""Fold TinyStories into the cartridge's alphabet.

The font and the keyboard know 26 letters in two cases, space, and
.,!?'-;:" - nothing else. TinyStories (Eldan & Li, 2023; HF
roneneldan/TinyStories, CDLA-Sharing-1.0) is nearly that already: 99% of
its stories are plain ASCII prose once the typographic quotes and dashes are
folded back to their keyboard forms. The rest - a digit, an emoji, a URL -
are dropped whole rather than patched, so every story in the corpus is one
the handheld could display and the player could have typed.

Input is the raw files from the dataset; the training file is read as a
prefix (the first 200 MiB is a quarter million stories, plenty for a model
this size), and the story the byte cut lands in is discarded. Output is one
story per block, blank line between stories, paragraph breaks inside a story
kept as single newlines - the shape py/train.py's loader expects.

    python py/tinystories.py --src models/tinystories --out models/tinystories
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

KEYBOARD = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ .,!?'-;:\"\n")
FOLD = {"‘": "'", "’": "'", "“": '"', "”": '"',
        "—": "-", "–": "-", "‐": "-", "‑": "-",
        "\x92": "'", "\x93": '"', "\x94": '"', " ": " ",
        "…": "...", "´": "'", "`": "'"}
SEP = "<|endoftext|>"

JOBS = [("TinyStoriesV2-GPT4-train.first200MiB.txt", "ts_train.txt", True),
        ("TinyStoriesV2-GPT4-valid.txt", "ts_valid_v2.txt", False),
        ("TinyStories-valid.txt", "ts_valid_v1.txt", False)]


def normalize(text):
    kept, dropped, out = 0, 0, []
    for story in text.split(SEP):
        s = "".join(FOLD.get(ch, ch) for ch in story).strip()
        lines = [ln.rstrip() for ln in s.split("\n")]
        lines = [ln for i, ln in enumerate(lines) if ln or (i and lines[i - 1])]
        s = "\n".join(lines).strip()
        if not s or set(s) - KEYBOARD:
            dropped += 1
            continue
        kept += 1
        out.append(s)
    return "\n\n".join(out) + "\n", kept, dropped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=ROOT / "models" / "tinystories")
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "tinystories")
    args = ap.parse_args()
    for src, dst, is_prefix in JOBS:
        text = (args.src / src).read_bytes().decode("utf-8", errors="replace")
        if is_prefix:
            text = SEP.join(text.split(SEP)[:-1])
        out, kept, dropped = normalize(text)
        (args.out / dst).write_text(out, encoding="ascii")
        print(f"{dst}: kept {kept} stories, dropped {dropped}, "
              f"{len(out) / 1e6:.1f}M chars", flush=True)


if __name__ == "__main__":
    main()
