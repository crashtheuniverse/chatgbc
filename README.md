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

You type a prompt on an on-screen keyboard. It generates, and keeps generating —
the text scrolls and it never hits a context limit. Tokenizer, weights and the
whole inference stack are on the cartridge.

## Where this started

[gbc-transformer](https://github.com/maddiedreese/gbc-transformer) got here
first, in GBDK C, and set both the model choice and the target. It runs the same
network at **169 s/token**. I wanted to know what the ceiling was if the kernel
were written by hand, which turned out to be a question about compilers: that
implementation spends ~676 cycles per multiply-accumulate, and the assembly
version spends 19.

## Numbers

| | |
|---|---|
| Model | TinyStories-260K — 5 layers, dim 64, 8 heads / 4 KV heads, vocab 512 |
| Context | 24-position sliding window, ring buffer, unbounded output |
| Weights | 4-bit, Lloyd–Max codebooks, per-output-row scales |
| | 8-bit for the classifier and the two KV projections |
| Arithmetic | int8 activations, 16-bit accumulators, no floating point, no division |
| **Speed** | **6.16 s/token** averaged over a 96-token run (12,918,757 M-cycles) |
| | 4.8 s for the first token, 6.4 s once the 24-token window fills |
| | **2.26 s per character**, at 2.73 characters a token |
| Quality | 1.54 bits/token cross-entropy against fp32's own continuations |
| | 78.1% top-1 agreement with fp32 on held-out prompts (KL 0.34 bits) |
| Kernel | 19 M-cycles per multiply-accumulate |
| ROM | 512 KB, MBC5 |

Attention is O(context), so a token costs more the deeper into a passage you
are — the bar at the bottom of the screen shows the figure climbing as it goes,
then flattening once the window is full. Every number here is measured **by the
cartridge itself** using the hardware timer, not by an emulator's clock.

**Greedy decoding never loops, for 0.13%.** Argmax is a fixed point: once the
state drifts back near one it has already visited, the model re-enters the same
cycle and stays there. It is not a quantization artifact - fp32 at full context
falls into it *sooner* than this cartridge does, at token 36 against 58. So the
decoder refuses to complete a 4-gram it has already emitted and takes the
next-best token. Deterministic, so bit-exactness is untouched, and it costs
about six extra classifier scans across a 160-token run. Sampling was measured
too and is worse: at this model size it breaks the grammar.

**Eight bits where it compounds.** Every matrix is 4-bit except three. The
classifier, because it decides the argmax — and `wk`/`wv`, because they are the
only weights whose error is *stored*: they write the KV cache and get re-read at
each of the next 24 positions, while every other matrix affects only the token
being computed. Those two are also the smallest in the layer, so upgrading them
costs 4.1% of a token and beats putting the **whole model** at 8 bits, which
costs 32%.

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

Windows, PowerShell. Everything is fetched into the project; nothing touches your
PATH.

```powershell
.\bootstrap.ps1   # RGBDS, SameBoy, a .venv with PyBoy
.\build.ps1       # -> build\chatgbc.gbc
.\test.ps1        # build, then the headless test suite
.\tools\sameboy\sameboy.exe build\chatgbc.gbc
```

**Controls:** d-pad moves, `A` types, `B` deletes, `SELECT` flips case, `START`
generates — and `START` again goes back to the keyboard.

## How it is kept honest

`py/quant.py` is not a loose reference — it is a **bit-exact integer twin** of the
assembly: same quantization, rounding, saturation, order and widths. The tests
boot the ROM headlessly and assert it emits an identical token sequence, not a
similar one. Every bug becomes "at which layer do the two stop agreeing", which
is a bisection with a definite answer.

## More

- [The model](docs/THE-MODEL.md) — one page: what it runs, why MACs equal
  parameters, and what depth costs that width does not
- [How it works](docs/CONCEPTS.md) — a short tour of the model: tokens, heads,
  the KV cache, and why the multiply is a table lookup. No ML background needed
- [Making of](docs/MAKING-OF.md) — how it was built, and what was thrown away
- [Experiment log](docs/LOG.md) — every measurement, including the failures
- [Decisions](docs/DECISIONS.md) — design decisions and what drove them

## Credits

[karpathy/tinyllamas](https://huggingface.co/karpathy/tinyllamas) (`stories260K`)
· [gbc-transformer](https://github.com/maddiedreese/gbc-transformer) ·
[dhepper/font8x8](https://github.com/dhepper/font8x8) ·
[RGBDS](https://rgbds.gbdev.io) ·
[gbdev hardware.inc](https://github.com/gbdev/hardware.inc) ·
[PyBoy](https://github.com/Baekalfen/PyBoy) ·
[SameBoy](https://sameboy.github.io)
