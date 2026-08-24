# ChatGBC

A language model that runs on a Game Boy Color. Not an emulator on a phone — a
512 KB cartridge, an 8 MHz SM83, 32 KB of RAM, and a transformer doing a full
forward pass per token in hand-written assembly. No C anywhere.

![ChatGBC generating text](docs/chatgbc.gif)

*One frame per token, roughly 100x the speed of the hardware — 160 tokens, and
the real run is seventeen minutes on the handheld.*

**Watch the bottom bar.** `TOK` walks past 24, which is the entire attention
window, and nothing happens: the text just keeps going. And `CYC/TOK` climbs
while the window is filling — attention is O(context) — then **goes flat** the
moment every slot is live and old ones start being overwritten. That flattening
is the ring buffer, made visible.

You type a prompt on an on-screen keyboard (`A` types, `B` deletes, `SELECT`
flips case, `START` generates). Tokenizer, weights and the whole inference
stack are on the cartridge.

## Numbers

| | |
|---|---|
| Model | TinyStories-260K — 5 layers, dim 64, 8 heads / 4 KV heads, vocab 512 |
| Context | 24-position sliding window, ring buffer, unbounded output |
| Weights | 4-bit, Lloyd–Max codebooks, per-output-row scales; 8-bit where it compounds |
| Arithmetic | int8 activations, 16-bit accumulators, no floating point, no division |
| **Speed** | **6.16 s/token** averaged over a 96-token run (12,918,757 M-cycles) |
| | **2.26 s per character**, at 2.73 characters a token |
| Quality | 78.1% top-1 agreement with fp32 on held-out prompts (KL 0.34 bits) |
| Kernel | 19 M-cycles per multiply-accumulate |

Every number is measured **by the cartridge itself** using the hardware timer,
not by an emulator's clock.

## Why this exists

The model is [karpathy's TinyStories-260K](https://huggingface.co/karpathy/tinyllamas):
a quarter-million parameters trained on the
[TinyStories](https://arxiv.org/abs/2305.07759) corpus, whose point was that a
model this small can write coherent English at all. That result is what makes a
Game Boy LLM possible — the hardware was never going to meet the model halfway.

The idea turned out not to be mine alone: for completeness,
[gbc-transformer](https://github.com/maddiedreese/gbc-transformer) had already
run this model on a GBC, in C. I wanted a different thing. In assembly every
cycle is attributable to a line you can point at, and with a bit-exact integer
oracle behind every kernel, what a design decision costs — in cycles and in
quality — is a measurement, not a guess. That is the foundation this project
actually is: a loop where each release is measured against the last, and the
improvement never has to stop.

## Two tricks worth the click

**The multiply is a table lookup.** The SM83 has no multiplier. With 4-bit
weights there are sixteen possible weight values and 256 possible activations, so
every product the model could ever need fits in 8 KB of ROM per matrix. The
kernel copies 32 bytes into HRAM and from then on "multiply" is `ldh a, [c]` —
3,200 cycles become 200. This machine has 8 MB of ROM and almost no cycles; the
whole design is trading the abundant thing for the scarce one.

**Generation never stops, because the cache is a ring.** The slot for position
`p` is `p mod 24`, while the rotary embedding keeps rotating by the *absolute*
`p`. Rotation is where a token is; storage is where it fits. Separating them
costs a handful of subtractions, and the model simply attends to the last 24
positions forever.

## Build it

Windows, PowerShell. Everything is fetched into the project; nothing touches
your PATH.

```powershell
.\bootstrap.ps1   # RGBDS, SameBoy, a .venv with PyBoy
.\build.ps1       # -> build\chatgbc.gbc
.\test.ps1        # build, then the headless test suite
.\tools\sameboy\sameboy.exe build\chatgbc.gbc
```

## How it is kept honest

`py/quant.py` is a **bit-exact integer twin** of the assembly: same
quantization, rounding, saturation, order and widths. The tests boot the ROM
headlessly and assert it emits an identical token sequence, not a similar one.
Every bug becomes "at which layer do the two stop agreeing", which is a
bisection with a definite answer.

## More

- [The model](docs/THE-MODEL.md) — one page: what it runs, why MACs equal
  parameters, and what depth costs that width does not
- [How it works](docs/CONCEPTS.md) — a short tour: tokens, heads, the KV cache,
  and why the multiply is a table lookup. No ML background needed
- [Making of](docs/MAKING-OF.md) — how it was built, what was measured, and
  what was thrown away

## Credits

[karpathy/tinyllamas](https://huggingface.co/karpathy/tinyllamas) (`stories260K`)
· [TinyStories](https://arxiv.org/abs/2305.07759) ·
[gbc-transformer](https://github.com/maddiedreese/gbc-transformer) ·
[dhepper/font8x8](https://github.com/dhepper/font8x8) ·
[RGBDS](https://rgbds.gbdev.io) ·
[gbdev hardware.inc](https://github.com/gbdev/hardware.inc) ·
[PyBoy](https://github.com/Baekalfen/PyBoy) ·
[SameBoy](https://sameboy.github.io)
