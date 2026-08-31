# ChatGBC

A language model that runs on a Game Boy Color written in Assembly.

**some stats:**
- 6.16 s/token, ~2.3 s per character — measured by DIV/TIMA (not emu clock)
- No multiplications / divs on the SM83 CPU so lots of requants, pre computation and LUTs
- W4 (4-bit weights) post quantized from original weights
- Fits in 512KB ROM. Still room to spare 
- 24 Tokens Attention window

_Based on TinyStories260K and weights_

![ChatGBC generating text](docs/chatgbc.gif)

*One frame per token, roughly 100x the speed of the hardware — 160 tokens, and
the real run is seventeen minutes on the handheld.*

**Bottom Bar.** `TOK` walks past 24, which is the entire attention
window, but the text just keeps going thanks to a `RING BUFFER`. 
It's a trick. Eventually you lose coherence and allucinate.

You type a prompt on an on-screen keyboard (`A` types, `B` deletes, `SELECT`
flips case, `START` generates). Tokenizer, weights and the whole inference
stack are on the cartridge.

## Numbers

| | |
|---|---|
| Model | TinyStories-260K — 5 layers, dim 64, 8 heads / 4 KV heads, vocab 512 |
| Context | 24-position sliding window, ring buffer, unbounded output |
| Weights | 4-bit, Lloyd–Max codebooks, per-output-row scales; 8-bit used sparingly. |
| Arithmetic | int8 activations, 16-bit accumulators, no floating point, no division |
| **Speed** | **6.16 s/token** averaged over a 96-token run (12,918,757 M-cycles) |
| | **2.26 s per character**, at 2.73 characters a token |
| Quality | 78.1% top-1 agreement with fp32 on held-out prompts (KL 0.34 bits) |
| Kernel | 19 M-cycles per multiply-accumulate |

Numbers measured against HW timers. 

## Why this exists

The model is [karpathy's TinyStories-260K](https://huggingface.co/karpathy/tinyllamas):
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

## Tricks

**The multiply is a table lookup.** The SM83 has no multiplier. With 4-bit
weights there are sixteen possible weight values and 256 possible activations, so
every product the model could ever need fits in 8 KB of ROM per matrix. The
kernel copies 32 bytes into HRAM and from then on "multiply" is `ldh a, [c]` —
3,200 cycles become 200. This machine has 8 MB of ROM which is plenty but we are starving for CPU cycles. 
Also there is no cache and everything is so slow that you always trade memory for computation.

_Note_: the GBC is technically 8MHz but those are T-Cycles. A full instruction usually is 4 of those.
This means you really have 2MHz worth of `M` cycles, about 1 instruction each — so consider it a 2MHz HW

**Generation never stops, because the cache is a ring.** The slot for position
`p` is `p mod 24`, while the embedding keeps rotating by the *absolute*
`p`. You can separate token in the context/output from its source state in memory. 
A bit more bookkeeping to do but you can keep attending to the last 24 positions forever. 

## Build it

Windows, PowerShell. Everything is fetched into the project; No PATH required. 
I expressly chose tools that can work this way.

```powershell
.\bootstrap.ps1   # RGBDS, SameBoy, a .venv with PyBoy
.\build.ps1       # -> build\chatgbc.gbc
.\test.ps1        # build, then the headless test suite
.\tools\sameboy\sameboy.exe build\chatgbc.gbc
```

## Twin and testing

`py/quant.py` is a **bit-exact integer twin** of the assembly: same
quantization, rounding, saturation, order and widths. The tests boot the ROM
headlessly and assert it emits an identical token sequence.

Every bug becomes "at which layer do the two stop agreeing", which is a
bisection with a definite answer.

**HUGE KUDOS** to SameBoy and PyBoy for this. That is the work of giants.

## Proof, on the real thing

![ChatGBC running on a real Game Boy Color](docs/chatgbc.jpg)

#gbdev community on Discord was kind enough to flash it to a cartridge and capture a pic on original
hardware. 

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

MIT licensed.
