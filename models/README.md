# models

What `build.ps1` exports into the cartridges. Everything here is small
enough to live in the repository, so a fresh clone builds the same ROMs.

| File | What it is |
|---|---|
| `ts3L_v1024.bin` | The story model: 3 layers, dim 64, 4 experts of 176, 1,024-piece vocabulary, ternary weights. `build.ps1` builds `chatgbc.gbc` from it. |
| `tok_ts1024.bin` | Its tokenizer. |
| `rei.bin` | Rei v1: the same shape with a 512-piece vocabulary, trained on short conversations. `build.ps1 -Rei` builds `rei.gbc` from it. |
| `tok_rei.bin` | Her tokenizer. |
| `calibration.txt` | The first six stories of the TinyStories V1 validation file. The export calibrates the ROM's fixed-point exponents on them, so it is part of what makes a build byte-identical. |

The checkpoints hold the integers the cartridge uses; the float values in
them are only what the exporter needs to get those integers back.

SHA-256:

```
99ce91571d98fc9f14838599f539364fd34ca638176b157bca867866d6bfc6b3  ts3L_v1024.bin
53b2899fa9a95513d79aece3ae39c8ff9ed63059561a6e573a44c89105fef1fa  tok_ts1024.bin
b50026470ac21e3c8e7cdb368602ae9ad286e9fe13317c86bb2c4d1740407e72  rei.bin
aee23d5c5c82c7190c89d2756a744956a8bdffa80c942809624d7f7e27e01163  tok_rei.bin
da352e61a2f45505b4691f940241c4f5c6fefad44e47d77b20d96a82a20dbebe  calibration.txt
```

TinyStories (Eldan and Li, 2023) is published under CDLA-Sharing-1.0; the
six stories in `calibration.txt` are an excerpt of its validation split.
