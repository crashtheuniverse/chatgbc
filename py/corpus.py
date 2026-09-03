"""Generate a simple-vocabulary story corpus, offline and unencumbered.

TinyStories works at a quarter of a million parameters because it was
*engineered* to: a deliberately small vocabulary and simple syntax, so that a
model this size can actually learn the distribution. Feed real prose to 260K
parameters and you get mush - the constraint is not the subject matter, it is
sentence complexity.

That property can be manufactured rather than borrowed. This is a grammar: a few
hundred words, a handful of story arcs, and enough combinatorics to produce
millions of tokens that never repeat a whole story. It carries no licence and
needs no download, which means the whole training pipeline can be built and
tested before deciding what to train on for real.

Its ceiling is lower than a corpus written by a large model - the sentences are
formulaic and there is no world knowledge in it. What it is good for is proving
the pipeline end to end, and as a control: a model that cannot learn this cannot
learn anything.

    python py/corpus.py --tokens 2000000 --out build/corpus.txt
    python py/corpus.py --stories 3 --seed 7      # look at a few
"""

import argparse
import random
from pathlib import Path

GIRLS = ["Lily", "Anna", "Sara", "Mia", "Emma", "Rose", "Ruby", "Nora"]
BOYS = ["Tom", "Ben", "Max", "Tim", "Sam", "Jack", "Leo", "Finn"]
KIN = ["mom", "dad", "brother", "sister", "grandma", "teacher"]
ANIMALS = ["cat", "dog", "bird", "frog", "duck", "bunny", "fish", "bear",
           "mouse", "horse", "pig", "owl"]
THINGS = ["ball", "box", "hat", "book", "cup", "kite", "doll", "drum",
          "boat", "rock", "flower", "cake", "key", "sock", "bell"]

# Places carry their own preposition. "in the beach" and "in the hill" are the
# kind of error a grammar produces by accident and a model then learns as fact.
PLACES = [("park", "in"), ("garden", "in"), ("house", "in"), ("beach", "at"),
          ("forest", "in"), ("shop", "at"), ("school", "at"),
          ("kitchen", "in"), ("yard", "in"), ("hill", "on"), ("pond", "at"),
          ("room", "in")]

ADJ = ["big", "small", "red", "blue", "green", "old", "new", "soft", "shiny",
       "funny", "warm", "pretty", "tiny", "yellow"]
# Only these make sense in "too ___ to carry".
HEAVY = ["big", "heavy", "wide"]
FEEL = ["happy", "sad", "scared", "excited", "proud", "tired", "surprised",
        "sorry", "glad"]
MORALS = [
    "It is good to share.",
    "It is good to help your friends.",
    "It is good to be kind.",
    "It is good to try again.",
    "It is good to tell the truth.",
    "It is good to say sorry.",
    "It is good to be careful.",
    "It is good to listen.",
]


class Story:
    """One story, assembled from a random arc. Seeded, so a corpus is
    reproducible from its seed alone.

    Agreement is decided once, up front - gender, prepositions, possessives -
    rather than left to whichever fragment happens to be drawn. A grammar that
    contradicts itself teaches the contradiction.
    """

    def __init__(self, rng):
        self.r = rng
        self.girl = rng.random() < 0.5
        pool = GIRLS if self.girl else BOYS
        self.who = rng.choice(pool)
        self.her = "her" if self.girl else "his"
        self.she = "she" if self.girl else "he"
        self.noun = "girl" if self.girl else "boy"
        self.other = rng.choice([n for n in GIRLS + BOYS if n != self.who])
        self.kin = rng.choice(KIN)
        self.pet = rng.choice(ANIMALS)
        self.thing = rng.choice(THINGS)
        self.place, self.prep = rng.choice(PLACES)
        self.adj = rng.choice(ADJ)
        self.feel = rng.choice(FEEL)

    def at(self):
        return f"{self.prep} the {self.place}"

    def open(self):
        r = self.r
        return r.choice([
            f"Once upon a time, there was a {r.choice(ADJ)} {self.noun} named {self.who}.",
            f"One day, {self.who} went to the {self.place}.",
            f"{self.who} had a {self.adj} {self.thing}.",
            f"{self.who} and {self.other} were playing {self.at()}.",
            f"There was a {self.adj} {self.pet} who lived near the {self.place}.",
        ])

    def problem(self):
        r = self.r
        return r.choice([
            f"But the {self.thing} was too {r.choice(HEAVY)} to carry.",
            f"But then {self.who} could not find the {self.thing}.",
            f"The {self.pet} wanted the {self.thing} too.",
            f"{self.other} was {r.choice(FEEL)} and did not want to play.",
            f"It started to rain, so they could not stay {self.at()}.",
            f"The {self.thing} fell in the {r.choice(['water', 'mud', 'grass'])}.",
        ])

    def attempt(self):
        r = self.r
        return r.choice([
            f"{self.who} tried to fix it, but it did not work.",
            f"{self.who} asked {self.other} for help.",
            f'{self.who} said, "Can you help me, {self.other}?"',
            f"{self.who} went to ask {self.her} {self.kin} what to do.",
            f"They looked and looked, but the {self.thing} was not there.",
            f"{self.who} thought about the {self.thing} for a long time.",
        ])

    def turn(self):
        r = self.r
        return r.choice([
            f'{self.other} said, "I can help you."',
            f'{self.her.capitalize()} {self.kin} said, "Let us try again together."',
            f"Then {self.who} had a good idea.",
            f"The {self.pet} came and showed them the {self.thing}.",
            f"They worked together and it was easy.",
            f"{self.who} tried one more time, very slowly.",
        ])

    def close(self):
        r = self.r
        return r.choice([
            f"Now the {self.thing} was {r.choice(['fixed', 'clean', 'safe'])} again.",
            f"{self.who} and {self.other} were very {r.choice(FEEL)}.",
            f"They played {self.at()} until it was dark.",
            f'{self.who} said, "Thank you for helping me."',
            f"The {self.pet} was happy too.",
        ])

    def text(self):
        r = self.r
        parts = [self.open(), self.problem(), self.attempt(), self.turn(),
                 self.close()]
        if r.random() < 0.5:
            parts.insert(1, r.choice([
                f"{self.who} was very {self.feel}.",
                f"The {self.thing} was {self.adj} and {r.choice(ADJ)}.",
                f"{self.she.capitalize()} liked to play with the {self.pet} every day.",
            ]))
        if r.random() < 0.4:
            parts.append(r.choice(MORALS))
        return " ".join(parts)


def generate(tokens=None, stories=None, seed=0):
    rng = random.Random(seed)
    out, count = [], 0
    while True:
        s = Story(rng).text()
        out.append(s)
        count += len(s.split())
        if stories is not None and len(out) >= stories:
            break
        if tokens is not None and count >= tokens:
            break
        if stories is None and tokens is None:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tokens", type=int, help="stop after roughly this many words")
    ap.add_argument("--stories", type=int, help="stop after this many stories")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.tokens is None and args.stories is None:
        args.stories = 5

    text = "\n\n".join(generate(args.tokens, args.stories, args.seed)) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        words = len(text.split())
        vocab = len({w.strip('.,!?"').lower() for w in text.split()})
        print(f"wrote {args.out}: {words:,} words, {vocab:,} distinct, "
              f"{len(text):,} characters")
    else:
        print(text)


if __name__ == "__main__":
    main()
