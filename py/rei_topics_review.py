"""The topic tree's sense review: every candidate line answered on the twin,
for a reviewer to judge.

    python py/rei_topics_review.py review CHECKPOINT [--corpus FILE_OR_DIR ...]
    python py/rei_topics_review.py pool LEDGER_DIR --banks BANKS_DIR

`review` loads CHECKPOINT on the integer twin (golden5.chat_turn, exactly as
the cartridge runs a turn: the header, the name opcodes, the echo) and asks it
every line of the candidate pool (py/rei_topics_pool.txt) and of the tree
(py/rei_topics.py) in four conversations:

    fresh        the line opens a conversation; the name slot is empty
    fresh+name   the same with "tom" in the slot (a returning friend)
    chat         after "hello" and "how are you"; the slot empty
    chat+name    after "hello" and "my name is tom"; the slot holds "tom"
                 (set by the engine if she did not store it herself - the
                 note says so)

It writes a review sheet - build/review/topics_<checkpoint>.csv and .md - one
row per line: its topic, whether the tree has it, how often her corpus
teaches it (the pool's count; empty for a tree line the pool does not hold),
the four replies, and the WORD check: an unknown piece in the
line, a reply that is empty, runs out of steps, speaks for the player (">")
or shows an opcode ("<"), and with --corpus (her training text: .md
conversation files, or a directory of them) a word she was never taught.
The word check cannot see SENSE: "i like gold" -> "the sky is blue because
the air scatters the light." passes it. The sheet's `sense` column is the
reviewer's - ok / off / wrong / garbled, a line that fails there does not go
in the tree. `--lines` limits the run to the given lines (a quick look).

The tokenizer follows the checkpoint's vocabulary as rei_env.ps1 has it
(models/tok_rei1024.bin for 1,024 pieces, models/tok_rei.bin for 512), or
--tokenizer.

`pool` rebuilds py/rei_topics_pool.txt from a corpus' ledgers (friend5b's
*.ledger.jsonl: every exchange with the events it teaches) and the corpus'
banks (their "== qa NAME | topic=T" sections name each answer's topic): the
player lines her corpus teaches most, grouped into the tree's ten topics,
about --per candidates each. Left out: a line that gives a name (the player
types their own; rei_topics.gives_a_name), a line that only makes sense after
her question (answers, "wow", "more", distractors), invented words, and
anything that does not fit the prompt row. A cap per source keeps the pool
varied (one line per item, two per question, ten name recalls).
"""

import argparse
import collections
import copy
import csv
import glob
import json
import os
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import rei_topics                 # noqa: E402  (TOPICS, LINE_W, gives_a_name)

POOL = HERE / "rei_topics_pool.txt"
OUT = ROOT / "build" / "review"
KEYS = set("abcdefghijklmnopqrstuvwxyz .,!'-;:")      # rei_input.asm's keys, no "?"
NAME = "tom"
WARM = {"chat": ["hello", "how are you"], "chat+name": ["hello", "my name is " + NAME]}
CONDITIONS = ["fresh", "fresh+name", "chat", "chat+name"]
TOPIC_NAMES = [name for name, _ in rei_topics.TOPICS]


# --- the pool ----------------------------------------------------------------

# A bank's qa topic -> the tree's topic. "none" (homework, fun facts, "ask
# me") has no place in the tree.
QA_TOPIC = {"hello": "hello", "rei": "rei", "feeling": "feeling", "sky": "sky",
            "beach": "sky", "garden": "sky", "play": "play", "playroom": "things",
            "kind": "kind"}
# An item's kind -> the tree's topic.
ITEM_TOPIC = {"animal": "animals", "food": "food", "thing": "things", "game": "play",
              "sky": "sky", "colour": "things"}
CAP = {"name": 10, "likes": 4, "greet": 8, "talk": 3, "story": 3, "joke": 2,
       "fact": 2, "qa": 2, "item": 1, "feel": 1}


def normal(line):
    """A corpus player line as the tree writes one: lower case, no "?", no
    closing "!" or ".", single spaces; None if it cannot be typed or does not
    fit the prompt row."""
    s = line.replace("<NK>", "").lower().replace("?", "")
    s = re.sub(r"\s+", " ", s).strip().rstrip("!.").strip()
    if not s or len(s) > rei_topics.LINE_W or not set(s) <= KEYS:
        return None
    return s


def banks_topics(banks):
    """{qa name: tree topic} and {item name: tree topic} from the bank files."""
    qa, items = {}, {}
    for path in sorted(Path(banks).glob("*.txt")):
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"== qa (\S+) \| topic=(\w+)", line)
            if m and m.group(2) in QA_TOPIC:
                qa[m.group(1)] = QA_TOPIC[m.group(2)]
            m = re.match(r"== item (.+?) \| kind=(\w+)", line)
            if m and m.group(2) in ITEM_TOPIC:
                items[m.group(1)] = ITEM_TOPIC[m.group(2)]
    return qa, items


def classify(exchange, qa, items):
    """(tree topic, source) for a player line the tree could offer, or None."""
    events = exchange["events"]
    kinds = {e["type"] for e in events}
    if kinds & {"SET", "DISTRACT", "FOLLOW", "UNKNOWN"}:
        return None                     # a name, or a line that answers her
    for e in events:
        t = e["type"]
        if t == "DLG" and e.get("act") != "ask":
            return None
    line = exchange["player"].lower()
    for e in events:
        t, v = e["type"], e.get("value")
        if t in ("ASK", "NEVER") and e.get("slot") == "name":
            return "me", ("name",)
        if t == "NEVER" and e.get("slot") == "likes":
            return "me", ("likes",)
        if (t == "KNOWN" and e.get("slot") == "name") or (t == "DLG" and e.get("q") == "name"):
            return "hello", ("greet",)
        if t == "DLG":
            return "play", ("talk", e.get("q"))
        if t == "QA":
            return (qa[v], ("qa", v)) if v in qa else None
        if t == "ITEM":
            if e.get("mode") in ("metoo",):
                return "me", ("item", v)
            return (items[v], ("item", v)) if v in items else None
        if t == "FEEL":
            return ("feeling", ("feel", v)) if len(line.split()) >= 2 else None
        if t == "STORY":
            return ("play", ("story",)) if "story" in line else None
        if t == "JOKE":
            return ("play", ("joke",)) if ("joke" in line or "funny" in line) else None
        if t == "FACT":
            return "play", ("fact",)
    return None


def build_pool(ledgers, banks, per):
    qa, items = banks_topics(banks)
    counts = collections.Counter()
    source = {}
    files = sorted(glob.glob(str(Path(ledgers) / "*.ledger.jsonl")))
    if not files:
        raise SystemExit(f"no *.ledger.jsonl in {ledgers}")
    for path in files:
        with open(path, encoding="utf-8") as f:
            for row in f:
                for ex in json.loads(row)["exchanges"]:
                    got = classify(ex, qa, items)
                    s = normal(ex["player"])
                    if got is None or s is None or rei_topics.gives_a_name(s):
                        continue
                    counts[(got[0], s)] += 1
                    source.setdefault((got[0], s), got[1])
    pool = {name: [] for name in TOPIC_NAMES}
    used = collections.Counter()
    taken = set()
    for (topic, s), n in counts.most_common():
        src = source[(topic, s)]
        if len(pool[topic]) >= per or s in taken or used[(topic, src)] >= CAP[src[0]]:
            continue
        used[(topic, src)] += 1
        taken.add(s)
        pool[topic].append((s, n))
    return pool, len(files)


def write_pool(pool, nfiles, ledgers):
    o = ["# Generated by py/rei_topics_review.py pool - the candidate lines for the",
         "# topic tree, the player lines her corpus teaches most, by topic: line, then",
         f"# how often {nfiles} ledger file(s) of {Path(ledgers).name} teach it.",
         "# No line gives a name (the player types their own). py/rei_topics_review.py",
         "# review answers each on the twin for a reviewer to judge its sense.", ""]
    for topic in TOPIC_NAMES:
        o.append(f"== {topic}")
        o += [f"{s}\t{n}" for s, n in pool[topic]]
        o.append("")
    POOL.write_text("\n".join(o), encoding="utf-8", newline="\n")
    print(f"wrote {POOL}: " + ", ".join(f"{t} {len(pool[t])}" for t in TOPIC_NAMES))


def read_pool(path=POOL):
    """[(topic, line, count)] of the pool file."""
    out, topic = [], None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        if raw.startswith("#") or not raw.strip():
            continue
        if raw.startswith("== "):
            topic = raw[3:].strip()
            continue
        line, _, n = raw.partition("\t")
        out.append((topic, line, int(n or 0)))
    return out


# --- the review --------------------------------------------------------------

def vocab_size(ckpt):
    """The PIP5 header's vocabulary (magic, version, dim, hidden, layers,
    vocab: u16 each), as rei_env.ps1 reads it."""
    with open(ckpt, "rb") as f:
        head = f.read(14)
    return struct.unpack_from("<H", head, 12)[0]


def corpus_words(paths):
    """Every word of her lines in the corpus files (not the player's, not the
    markers); None without a corpus. "rei" is her lab name."""
    if not paths:
        return None
    known = {"rei", NAME}
    files = []
    for p in paths:
        p = Path(p)
        files += sorted(p.glob("*.md")) + sorted(p.glob("*.txt")) if p.is_dir() else [p]
    for path in files:
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith((">", "#", "!")):
                    continue
                known.update(re.findall(r"[a-z]+", line.replace("<N>", "").replace("<W>", "")
                                        .replace("<SN>", "")))
    return known


def word_check(reply, known):
    """The word check of one reply: '' if it passes."""
    if not reply.endswith("\n"):
        return "no end (ran out of steps)" if reply.strip() else "empty"
    if not reply.strip():
        return "empty"
    if reply.lstrip().startswith(">"):
        return "speaks for the player"
    if "<" in reply:
        return "an opcode shows"
    if known is not None:
        new = sorted(set(re.findall(r"[a-z]+", reply)) - known)
        if new:
            return "not her words: " + " ".join(new)
    return ""


def review(args):
    ckpt = Path(args.checkpoint).resolve()
    tok_path = args.tokenizer or ROOT / "models" / (
        "tok_rei1024.bin" if vocab_size(ckpt) == 1024 else "tok_rei.bin")
    os.environ["CHATGBC_CHAT"] = "1"
    os.environ["PIP5"] = str(ckpt)
    os.environ["CHATGBC_TOKENIZER"] = str(tok_path)
    import export5                # noqa: F401  (reads the environment above)
    import golden5
    import twin5
    from model5 import Model5, Tokenizer

    m = Model5(ckpt)
    tok = Tokenizer()
    assert len(tok.vocab) == m.cfg.vocab, f"{ckpt.name} vs {tok_path}: sizes differ"
    q = twin5.quantize5(m, twin5.calibrate5(m, tok, export5.cal_prompts()))
    known = corpus_words(args.corpus)

    tree = {s: name for name, lines in rei_topics.TOPICS for s in lines}
    rows = {}
    for topic, s, n in read_pool(args.pool):
        rows.setdefault(s, {"topic": topic, "line": s, "count": n})
    for s, topic in tree.items():            # a tree line the pool does not hold: no count
        rows.setdefault(s, {"topic": topic, "line": s, "count": ""})
    if args.lines:
        rows = {s: r for s, r in rows.items() if s in args.lines}
    order = {t: i for i, t in enumerate(TOPIC_NAMES)}
    rows = sorted(rows.values(), key=lambda r: (order.get(r["topic"], 99), r["line"] not in tree,
                                                -(r["count"] or 0), r["line"]))

    # The conversations the lines are asked in, each built once.
    start = {}
    notes = {}
    st = twin5.QState5(q.cfg)
    start["fresh"] = (st, True)
    st = twin5.QState5(q.cfg)
    st.name = NAME
    start["fresh+name"] = (st, True)
    for cond, warm in WARM.items():
        st = twin5.QState5(q.cfg)
        for i, w in enumerate(warm):
            golden5.chat_turn(q, tok, st, w, first=(i == 0), steps=args.steps)
        if cond == "chat+name" and st.name != NAME:
            notes[cond] = f"she did not store the name ({st.name!r}); the engine's slot set to {NAME!r}"
            st.name = NAME
        start[cond] = (st, False)

    for r in rows:
        fails = []
        r["in_tree"] = "yes" if r["line"] in tree else ""
        if 0 in golden5.staged_ids(tok, r["line"], True, ""):
            fails.append("unknown piece in the line")
        for cond in CONDITIONS:
            st0, first = start[cond]
            st = copy.deepcopy(st0)
            reply = golden5.chat_turn(q, tok, st, r["line"], first=first, steps=args.steps)
            why = word_check(reply, known)
            if why:
                fails.append(f"{cond}: {why}")
            r[cond] = reply.rstrip("\n")
        r["word_check"] = "ok" if not fails else "; ".join(fails)
        r["sense"] = ""
        r["note"] = ""

    OUT.mkdir(parents=True, exist_ok=True)
    stem = args.out or OUT / f"topics_{ckpt.stem}"
    stem = Path(stem)
    cols = ["topic", "line", "in_tree", "count"] + CONDITIONS + ["word_check", "sense", "note"]
    with open(stem.with_suffix(".csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    md = [f"# Topic tree review: {ckpt.name}", "",
          f"Tokenizer {Path(tok_path).name}; {len(rows)} lines, each in four conversations "
          f"({', '.join(CONDITIONS)}; warm-ups: " +
          "; ".join(f"{c} = {' / '.join(w)}" for c, w in WARM.items()) + ").",
          "The word check is mechanical; judge SENSE in the csv's `sense` column "
          "(ok / off / wrong / garbled): a reply on another subject passes the word check.", ""]
    md += [f"- {c}: {n}" for c, n in notes.items()]
    for topic in TOPIC_NAMES + sorted({r["topic"] for r in rows} - set(TOPIC_NAMES)):
        mine = [r for r in rows if r["topic"] == topic]
        if not mine:
            continue
        md += ["", f"## {topic}", ""]
        for r in mine:
            flag = " (tree)" if r["in_tree"] else ""
            count = f"corpus {r['count']}" if r["count"] != "" else "not in the pool"
            md.append(f"**{r['line']}**{flag} - {count} - word check: {r['word_check']}")
            md.append("")
            md += [f"- {c}: {r[c]}" for c in CONDITIONS]
            md.append("")
    stem.with_suffix(".md").write_text("\n".join(md), encoding="utf-8", newline="\n")

    bad = sum(r["word_check"] != "ok" for r in rows)
    print(f"{len(rows)} lines ({sum(bool(r['in_tree']) for r in rows)} in the tree), "
          f"{bad} fail the word check")
    for c, n in notes.items():
        print(f"note, {c}: {n}")
    print(f"wrote {stem.with_suffix('.csv')} and {stem.with_suffix('.md')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("review", help="answer the pool and the tree on the twin")
    r.add_argument("checkpoint")
    r.add_argument("--tokenizer", help="default: by the checkpoint's vocabulary")
    r.add_argument("--pool", default=str(POOL))
    r.add_argument("--corpus", nargs="*", help="her training text, for the word check")
    r.add_argument("--lines", nargs="*", help="only these lines")
    r.add_argument("--steps", type=int, default=48)
    r.add_argument("--out", help="the sheet's path without extension")
    p = sub.add_parser("pool", help="rebuild py/rei_topics_pool.txt from a corpus")
    p.add_argument("ledgers", help="a directory of *.ledger.jsonl (friend5b's)")
    p.add_argument("--banks", required=True, help="the corpus' bank files (py/corpus5/banks)")
    p.add_argument("--per", type=int, default=20, help="candidates per topic")
    args = ap.parse_args()
    if args.cmd == "pool":
        pool, n = build_pool(args.ledgers, args.banks, args.per)
        write_pool(pool, n, args.ledgers)
    else:
        review(args)


if __name__ == "__main__":
    main()
