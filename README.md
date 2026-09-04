# ChatGBC

A language model that runs on a Game Boy Color written in Assembly.

v0.4 is a model trained *for* this machine, not borrowed: ternary weights,
a recurrent core instead of attention, four small experts per layer, and
an integer twin that decided every rounding before the assembly did.
v0.4.1 adds the teletype - characters arrive one at a time while the next
token computes - and stories that run until you stop them.

**some stats:**
- 1.08 s/token, ~0.31 s per character — measured by DIV/TIMA (v0.3: 6.16 s, 2.94 s per character on the same text)
- 1.15 bits per character on held-out TinyStories — level with v0.3's ROM (1.15), from a checkpoint that loses 2% to quantization where v0.3's lost 31%
- Weights are −1, 0 or +1. Three of them pick one of 27 precomputed sums: no multiplier, no product tables
- No attention, no KV cache, no window. The state is 192 bytes and a story runs until you press SELECT
- Four experts per layer, one runs per token: half the work of a dense layer, twice the weights
- The screen is a teletype: one character every 0.3 s, fed from a queue on the VBlank interrupt
- 374K parameters in a 256 KB ROM

_Trained on TinyStories, compared per character against v0.3_

![ChatGBC generating text](docs/chatgbc.gif)

*One frame per character, about five times the pace of the hardware; 200
tokens, then SELECT - it would go on. The real run is three and a half
minutes on the handheld; v0.3's 160 tokens took seventeen.*

You type a prompt on an on-screen keyboard (`A` types, `B` deletes, `SELECT`
flips case, `START` generates, `SELECT` again stops the story). Tokenizer,
weights and the whole inference stack are on the cartridge.

## Numbers

| | |
|---|---|
| Model | 3 layers, dim 64, minGRU core + ReLU² MLP as 4 experts of 176, vocab 1024 BPE — 374K parameters |
| Trained on | TinyStories V2 (254K stories, 59M tokens), 20,000 steps, on a laptop GPU in 3.5 hours |
| Context | a recurrent state: 3 × 64 bytes, unbounded output, no window |
| Weights | ternary with one power-of-two scale per row; classifier and router ternary at one scale |
| Arithmetic | int8 activations and state, exact 16-bit block sums, no floating point, no division, no multiply |
| **Speed** | **1.08 s/token** (2,259,829 M-cycles; 2,271,104 with the teletype running), **0.31 s per character** at 3.46 characters a token |
| **Quality** | **1.146 bits/char** on 200 held-out stories, teacher-forced. v0.3 as shipped: 1.149; v0.3's fp32 checkpoint: 0.876 |
| Kernel | ~10.5 M-cycles per multiply-accumulate, three MACs per table lookup |

Numbers measured against HW timers; quality measured on the bit-exact twin
of each ROM, on stories no version trained on. [VERSIONS.md](VERSIONS.md)
has every release measured the same way.

## Why this exists

The model behind v0.3 was [karpathy's TinyStories-260K](https://huggingface.co/karpathy/tinyllamas):
a quarter-million parameters trained on the
[TinyStories](https://arxiv.org/abs/2305.07759) corpus, whose point was that a
model this small can write coherent English at all. That result is what makes a
Game Boy LLM possible.

The idea came from a post I saw on X and looking at the repo:
[gbc-transformer](https://github.com/maddiedreese/gbc-transformer)

I wanted a different thing. In assembly every cycle is attributable to a code line.
The AI assist also made an oracle that could pre-verify what a decision costs. 

The real foundation of the project was to make a loop that would be testable fast enough to get into a **loop**. 
That is the foundation this project actually is. 
How could I do a self improving loop on my laptop. 
HW constraints allows me to look at the bits, memory dumps, and eventually train locally.

v0.4 closes that loop: the model is trained here, inside the same integers the
cartridge computes with, and judged by the same twin that judges the assembly.

## What changed since v0.3

v0.3 took a float transformer and squeezed it into 4-bit tables and a
24-token window. Measured on held-out stories, the squeeze cost 31% in bits
per character: the checkpoint scores 0.88, the cartridge 1.15. v0.4 turns it
around: decide what the hardware does well, train a model that lives there
from step one, and ship what was trained.

**The multiply is a table of sums.** A ternary weight is −1, 0 or +1, so three
of them applied to three activations is one of 27 signed sums. The kernel
builds those 27 sums once per block of three inputs and then every weight
triple is a single `ldh a, [c]` and an add. No product tables, no bank
switch per input, and a matrix in ROM is one byte per three weights.

**The core is a minGRU, not attention.** `h = h + z ⊙ (h̃ − h)`, gates from the
input only. Three 64×64 matvecs per layer and a 64-byte state; nothing grows
with the length of the story. v0.3 needed a ring of 24 cached positions and
lost the thread when the ring wrapped. This never wraps, so the story never
has to end.

**Four experts, one runs.** Each layer's MLP is four experts of 176; a
ternary router picks one per token. Half the multiply-accumulates of the dense
layer, twice the parameters, and choosing an expert is one MBC5 bank register
write.

**Trained inside the integers.** Weights are fake-quantized to ternary with
power-of-two row scales during training, activations and the recurrent state
to int8, the classifier and router to ternary at a single scale — and a
full-precision residual (the Arenas trick from
[Sherry](https://arxiv.org/abs/2601.07892)) is annealed to zero so ternary
converges at all. The exported integers score within 2% of the float model.
In float, stories260K is still the better model (0.88 bits per character
against 1.12); what v0.4 buys is that nothing is lost between the training
run and the cartridge, and a sevenfold cycle budget for the next model to
spend.

**The teletype.** A token is three or four characters, and they used to land
in one burst followed by a second of nothing. Now they go into a queue and
the VBlank handler releases one every 18 frames while the forward pass is
busy with the next token. The handler is the only thing that touches VRAM
during a story: a character is one tile write, a scroll moves the shadow
buffer and asks for its DMA on the next frame. The model never waits for the
screen.

_Note_: the GBC is technically 8MHz but those are T-Cycles. A full instruction usually is 4 of those.
This means you really have 2MHz worth of `M` cycles, about 1 instruction each — so consider it a 2MHz HW

## Build it

Windows, PowerShell. Everything is fetched into the project; No PATH required. 
I expressly chose tools that can work this way.

```powershell
.\bootstrap.ps1   # RGBDS, SameBoy, a .venv with PyBoy and torch
.\build.ps1       # -> build\chatgbc.gbc
.\test.ps1        # build, then the headless test suite
.\tools\sameboy\sameboy.exe build\chatgbc.gbc
```

## Train it

```powershell
# TinyStories from HF roneneldan/TinyStories into models\tinystories\, then:
.venv\Scripts\python.exe py\tinystories.py                       # fold to the keyboard's alphabet
.venv\Scripts\python.exe py\tokenizer.py --corpus models\tinystories\ts_train.txt --out models\tok_ts1024.bin --vocab 1024
.venv\Scripts\python.exe py\fit.py --tokenizer models\tok_ts1024.bin --name ts3L_v1024
.venv\Scripts\python.exe py\export5.py                           # checkpoint -> blobs + model.inc
.venv\Scripts\python.exe py\score5.py                            # bits/char of what ships
.\test.ps1
```

## Twin and testing

`py/twin5.py` is a **bit-exact integer twin** of the assembly: same
quantization, rounding, saturation, order and widths. The tests boot the ROM
headlessly and assert it emits an identical token sequence.

Every bug becomes "at which layer do the two stop agreeing", which is a
bisection with a definite answer.

**HUGE KUDOS** to SameBoy and PyBoy for this. That is the work of giants.

## Proof, on the real thing

![ChatGBC running on a real Game Boy Color](docs/chatgbc.jpg)

#gbdev community on Discord was kind enough to flash v0.3 to a cartridge and
capture a pic on original hardware. 

## More

- [Versions](VERSIONS.md) — every release measured the same way, with its capture
- [The model](docs/THE-MODEL.md) — one page: what it runs, why MACs equal
  parameters, and what depth costs that width does not
- [How it works](docs/CONCEPTS.md) — a short tour: tokens, heads, the KV cache,
  and why the multiply is a table lookup. No ML background needed
- [Making of](docs/MAKING-OF.md) — how it was built, what was measured, and
  what was thrown away

## Credits

[TinyStories](https://arxiv.org/abs/2305.07759) (Eldan & Li; dataset
[roneneldan/TinyStories](https://huggingface.co/datasets/roneneldan/TinyStories), CDLA-Sharing-1.0) ·
[karpathy/tinyllamas](https://huggingface.co/karpathy/tinyllamas) (`stories260K`, v0.3) ·
[Were RNNs All We Needed?](https://arxiv.org/abs/2410.01201) (minGRU) ·
[Sherry](https://arxiv.org/abs/2601.07892) (the Arenas residual) ·
[gbc-transformer](https://github.com/maddiedreese/gbc-transformer) ·
[dhepper/font8x8](https://github.com/dhepper/font8x8) ·
[RGBDS](https://rgbds.gbdev.io) ·
[gbdev hardware.inc](https://github.com/gbdev/hardware.inc) ·
[PyBoy](https://github.com/Baekalfen/PyBoy) ·
[SameBoy](https://sameboy.github.io)

MIT licensed.
