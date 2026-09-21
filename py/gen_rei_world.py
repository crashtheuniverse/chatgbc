"""Turn the world's pictures into Game Boy Color data: src/rei_world_art.inc.

Run through py/gen_rei_art.py (which calls emit() here), or alone:

    python py/gen_rei_world.py --preview     also build/rei_world_preview.png

Needs PIL and numpy, at generation time only: the .inc is committed.

THE SCENE is py/art/world_sunset.png, a riverside at sunset, 256 x 144. The
world shows a strip 96 lines high over a black panel for her thoughts, so the
top 48 lines of sky are cut and the rest - the sun, the skyline, the river, the
railing, the promenade - is the strip: 32 x 12 tiles, the whole width of the
hardware's BG map. The hardware gives a tile four colours from one of eight
palettes and the scene 256 tiles, so the picture is squeezed twice:

  palettes  seven palettes of four 15-bit colours (the eighth is the thought
            box's). Tiles are clustered by their mean colour, each cluster's
            pixels are clustered into four colours, every tile then moves to
            the palette that draws it with the least error, and round again.
  tiles     exact duplicates first, then the nearest pair of tiles that share
            a palette is merged, again and again, until 256 are left. "Nearest"
            is weighted so that flat tiles (pavement, water, sky) merge long
            before busy ones (the sun, the skyline, the railing).

Everything is seeded, so the same picture gives the same bytes.

REI is py/art/rei_sheet_src.png: eight frames at about six times their size,
four from behind (she stands at the railing and looks at the sunset) and four
walking left. Each is reduced to 48 pixels tall in three colours. The sheet's
background is the same navy as her skirt and socks, so what is transparent
cannot be told by colour: the figure's silhouette is built from the light
pixels, closed, and filled row by row, and navy inside it is kept. Small
hand patches per frame (PATCHES) clean what the reduction leaves.
A frame is 8 x 16 objects, three high: two columns for the back views, three
for the walk; walking right is the same objects mirrored, columns reversed.

VRAM: the world runs with LCDC.4 clear, so its BG tiles are bank 1 at
$8800-$97FF (256 of them) and its sprites bank 1 at $8000-$87FF (128), all
resident; bank 0 keeps the chat's tiles, and a copy of its first 128 at $9000
for the thought panel's letters.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "py" / "art"
DST = ROOT / "src" / "rei_world_art.inc"

W, H = 32, 12                         # tiles: the strip
CUT = 6                               # tile rows of sky left out above it
N_PALETTES = 7
N_TILES = 256
SEED = 1

FRAME_H = 48                          # pixels
IDLE_COLS, WALK_COLS = 2, 3           # 8-pixel columns a frame
SPAN_Y, SPAN_X = 10, 3                # navy gaps this long, down and across, are inside her
HAIR_Y, LEGS_Y, SPAN_LEGS = 7, 37, 6  # not above her hair (the stray lock); socks, not the gap between her legs
FRAMES = [("IDLE", IDLE_COLS)] * 4 + [("WALK", WALK_COLS)] * 4
NAVY, BLUE, WHITE = (24, 32, 72), (96, 168, 248), (240, 248, 255)

# What is where, for the retrain: the thought trigger records the nearest of
# these (wWorldNear). x is the centre, in pixels across the picture.
OBJECTS = [
    ("bridge",   24, "bridge far long lights"),
    ("river",    56, "river wide slow dark"),
    ("sun",      90, "sun low red warm"),
    ("water",   100, "water gold light path"),
    ("railing", 128, "railing cold iron lean"),
    ("city",    160, "city far small windows"),
    ("flowers", 200, "flowers weeds small grow"),
    ("tower",   232, "tower tall lights on"),
]

# Hand fixes after the reduction: frame -> [(x, y, colour)], colour 0 = clear,
# 1 navy, 2 blue, 3 white.
PATCHES = {}


def rgb15(c):
    return (int(c[0]) >> 3) | ((int(c[1]) >> 3) << 5) | ((int(c[2]) >> 3) << 10)


# --- the scene -----------------------------------------------------------------

def convert_scene():
    import numpy as np
    from PIL import Image

    rng = np.random.default_rng(SEED)
    im = Image.open(ART / "world_sunset.png").convert("RGB")
    assert im.size == (W * 8, (H + CUT) * 8), im.size
    im = im.crop((0, CUT * 8, W * 8, (H + CUT) * 8))          # the lower twelve rows: the sun stays in
    src = np.array(im).astype(float)
    a = (np.array(im).astype(int) >> 3) << 3                  # 15-bit colour
    T = a.reshape(H, 8, W, 8, 3).transpose(0, 2, 1, 3, 4).reshape(W * H, 64, 3).astype(float)
    n = len(T)

    def kmeans(x, k, rounds=16):
        c = x[rng.choice(len(x), k, replace=False)].copy()
        for _ in range(rounds):
            lab = ((x[:, None] - c[None]) ** 2).sum(2).argmin(1)
            for j in range(k):
                if (lab == j).any():
                    c[j] = x[lab == j].mean(0)
        return c

    def errors(pal):                                          # every tile drawn with `pal`
        return ((T[:, :, None] - pal[None, None]) ** 2).sum(3).min(2).sum(1)

    means = T.mean(1)
    cent = kmeans(means, N_PALETTES)
    lab = ((means[:, None] - cent[None]) ** 2).sum(2).argmin(1)
    pals = None
    for _ in range(10):
        pals = []
        for p in range(N_PALETTES):
            px = T[lab == p].reshape(-1, 3)
            if len(px) < 4:                                   # an empty palette: give it the worst tiles
                worst = np.argsort(-np.min([errors(q) for q in pals], axis=0))[:8] if pals else np.arange(8)
                px = T[worst].reshape(-1, 3)
            take = rng.choice(len(px), min(len(px), 6000), replace=False)
            pals.append(kmeans(px[take], 4))
        lab = np.array([errors(q) for q in pals]).argmin(0)
    pals = [np.clip((q.round().astype(int) >> 3) << 3, 0, 248) for q in pals]
    pals = [q[np.argsort(q.sum(1))] for q in pals]            # dark to light, for tidiness
    lab = np.array([errors(q.astype(float)) for q in pals]).argmin(0)
    idx = np.array([((T[i][:, None] - pals[lab[i]][None]) ** 2).sum(2).argmin(1) for i in range(n)])

    # how busy a tile is: busy tiles resist merging
    g = a.astype(float).sum(2)
    edge = np.zeros_like(g)
    edge[:, 1:] += np.abs(g[:, 1:] - g[:, :-1])
    edge[1:, :] += np.abs(g[1:, :] - g[:-1, :])
    busy = edge.reshape(H, 8, W, 8).transpose(0, 2, 1, 3).reshape(n, 64).mean(1)
    busy = 1.0 + busy / busy.mean()

    groups, seen = {}, {}
    for i in range(n):                                        # exact duplicates
        key = (int(lab[i]), idx[i].tobytes())
        if key in seen:
            groups[seen[key]].append(i)
        else:
            seen[key] = i
            groups[i] = [i]
    unique = len(groups)

    def centre(members):
        pal = pals[lab[members[0]]].astype(float)
        w = busy[members][:, None, None]
        mean = (T[members] * w).sum(0) / w.sum()
        return ((mean[:, None] - pal[None]) ** 2).sum(2).argmin(1)

    while len(groups) > N_TILES:
        keys = list(groups)
        C = np.array([pals[lab[k]][centre(groups[k])].reshape(-1) for k in keys]).astype(float)
        L = np.array([lab[k] for k in keys])
        Wt = np.array([busy[groups[k]].sum() for k in keys])
        D = ((C[:, None] - C[None]) ** 2).sum(2)
        D[L[:, None] != L[None]] = 1e18
        np.fill_diagonal(D, 1e18)
        D = D * (Wt[:, None] * Wt[None] / (Wt[:, None] + Wt[None]))
        batch, done = max(1, (len(groups) - N_TILES) // 6), set()
        for f in np.argsort(D, axis=None, kind="stable")[:batch * 6]:
            i, j = divmod(int(f), len(keys))
            if i in done or j in done or len(groups) <= N_TILES:
                continue
            done |= {i, j}
            groups[keys[i]] += groups.pop(keys[j])

    tiles, tmap, amap = [], [0] * n, [0] * n
    for k in sorted(groups):
        ci = centre(groups[k])
        for t in groups[k]:
            tmap[t] = len(tiles)
            amap[t] = int(lab[t]) + 1                         # palette 0 is the thought box's
        tiles.append(ci.reshape(8, 8).tolist())
    out = np.zeros((n, 64, 3))
    for t in range(n):
        out[t] = pals[lab[t]][np.array(tiles[tmap[t]]).reshape(-1)]
    res = out.reshape(H, W, 8, 8, 3).transpose(0, 2, 1, 3, 4).reshape(H * 8, W * 8, 3)
    mse = float(((res - src) ** 2).mean())
    return tiles, tmap, amap, [q.tolist() for q in pals], res.astype("uint8"), unique, mse


# --- Rei -----------------------------------------------------------------------

def sheet_inks(big):
    """The sheet's own three colours: navy (its background), mid blue, white."""
    import numpy as np
    flat = big.reshape(-1, 3)
    lum = flat.sum(1)
    navy = flat[lum < 200].mean(0)
    white = flat[lum > 640].mean(0)
    mid = flat[(lum > 330) & (lum < 560)].mean(0)
    return np.array([navy, mid, white])


def convert_frames():
    """Eight frames, each FRAME_H rows of cols * 8 colours 0..3 (0 = clear)."""
    import numpy as np
    from PIL import Image

    sheet = Image.open(ART / "rei_sheet_src.png").convert("RGB")
    cell = sheet.width // 8
    whole = np.array(sheet).astype(float)
    inks = sheet_inks(whole)
    frames = []
    for f, (_, cols) in enumerate(FRAMES):
        big = whole[:, f * cell:(f + 1) * cell]
        light = big.sum(2) > 260                              # anything clearly not the navy ground
        ys, xs = np.nonzero(light)
        top, bottom = ys.min(), ys.max() + 1
        left, right = xs.min(), xs.max() + 1
        scale = FRAME_H / (bottom - top)
        w = max(1, round((right - left) * scale))
        small = Image.fromarray(big[top:bottom, left:right].astype("uint8")).resize((w, FRAME_H), Image.BOX)
        px = np.array(small).astype(float)
        near = ((px[:, :, None] - inks[None, None]) ** 2).sum(3).argmin(2) + 1   # 1..3
        fg = near > 1                                         # blue or white: certainly her
        for y in (FRAME_H - 1, FRAME_H - 2):                  # the ground line under her feet:
            for x in range(w):                                # light, but standing on nothing
                if fg[y, x] and not fg[y - 1, max(0, x - 1):x + 2].any():
                    fg[y, x] = False
        mask = fg.copy()
        for x in range(w):                                    # navy in a column between two light
            ys_ = np.nonzero(fg[:, x])[0]                     # pixels is hers: skirt, socks, shadow
            for y0, y1 in zip(ys_[:-1], ys_[1:]):
                limit = SPAN_LEGS if y0 >= LEGS_Y else SPAN_Y
                if 1 < y1 - y0 <= limit and y0 >= HAIR_Y:
                    mask[y0:y1, x] = True
        for y in range(FRAME_H):                              # and in a row, across small gaps: lines
            xs_ = np.nonzero(mask[y])[0]
            for x0, x1 in zip(xs_[:-1], xs_[1:]):
                if 1 < x1 - x0 <= SPAN_X:
                    mask[y, x0:x1] = True
        outside = np.zeros_like(mask)                         # holes: clear pixels the border
        stack = [(y, x) for y in range(FRAME_H) for x in (0, w - 1)]
        stack += [(y, x) for x in range(w) for y in (0, FRAME_H - 1)]
        while stack:                                          # cannot reach are inside her
            y, x = stack.pop()
            if 0 <= y < FRAME_H and 0 <= x < w and not mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
        mask[HAIR_Y:LEGS_Y] |= ~outside[HAIR_Y:LEGS_Y]        # (her legs are apart: that gap is open)
        img = np.where(mask, near, 0)
        if w > cols * 8:                                      # a wisp of hair too wide: trim it
            cut = (w - cols * 8) // 2
            img, w = img[:, cut:cut + cols * 8], cols * 8
        full = np.zeros((FRAME_H, cols * 8), int)
        x0 = (cols * 8 - w) // 2
        full[:, x0:x0 + w] = img
        for x, y, c in PATCHES.get(f, []):
            full[y, x] = c
        frames.append(full.tolist())
    return frames


# --- output --------------------------------------------------------------------

def tile_bytes(t):
    out = []
    for row in t:
        lo = hi = 0
        for v in row:
            lo = (lo << 1) | (v & 1)
            hi = (hi << 1) | (v >> 1)
        out += [lo, hi]
    return out


def sprite_tiles(frames):
    """Each frame's tiles: column by column, top to bottom, 8 x 8 each - so an
    8 x 16 object is tile 2k and 2k + 1."""
    tiles, first = [], []
    for frame, (_, cols) in zip(frames, FRAMES):
        first.append(len(tiles))
        for c in range(cols):
            for y in range(0, FRAME_H, 8):
                tiles.append([row[c * 8:c * 8 + 8] for row in frame[y:y + 8]])
    assert len(tiles) <= 128, len(tiles)
    return tiles, first


def twinkle(pals, amap):
    """The palette the sun's path on the water is drawn in, if the sun itself
    is not: its lightest colour is the one the handler makes shimmer, a little."""
    near_sun = {amap[ty * W + tx] for ty in range(0, 10 - CUT) for tx in range(6, 16)}
    count = {}
    for ty in range(11 - CUT, 15 - CUT):
        for tx in range(9, 14):
            p = amap[ty * W + tx]
            if p not in near_sun:
                count[p] = count.get(p, 0) + 1
    if not count:
        return 1, 3, pals[0][3], pals[0][3]                   # nothing safe to touch: no shimmer
    pal = max(sorted(count), key=count.get)
    bright = pals[pal - 1][3]
    return pal, 3, bright, [int(v * 0.88) for v in bright]


def emit():
    tiles, tmap, amap, pals, res, unique, mse = convert_scene()
    frames = convert_frames()
    stiles, first = sprite_tiles(frames)
    tw_pal, tw_idx, tw_a, tw_b = twinkle(pals, amap)
    box = [(0, 0, 0), (80, 80, 96), (160, 160, 176), (255, 255, 255)]     # her thoughts: white on black
    assert len(tiles) == 256, "the loader copies one 4 KB block"
    o = ["; Generated by py/gen_rei_world.py - do not edit.",
         "; The riverside at sunset (py/art/world_sunset.png) and Rei in it",
         f"; (py/art/rei_sheet_src.png). Scene: {len(tiles)} tiles from {unique} distinct, MSE {mse:.0f}.",
         "",
         f"DEF WORLD_W EQU {W}",
         f"DEF WORLD_H EQU {H}",
         f"DEF WORLD_TILES EQU {len(tiles)}",
         f"DEF WORLD_OBJ_TILES EQU {len(stiles)}",
         f"DEF WORLD_OBJECTS EQU {len(OBJECTS)}",
         f"DEF WORLD_IDLE_COLS EQU {IDLE_COLS}",
         f"DEF WORLD_WALK_COLS EQU {WALK_COLS}",
         f"DEF WORLD_TWINKLE EQU {tw_pal * 8 + tw_idx * 2}     ; BCPS index of the colour that shimmers",
         f"DEF WORLD_TWINKLE_A EQU ${rgb15(tw_a):04X}",
         f"DEF WORLD_TWINKLE_B EQU ${rgb15(tw_b):04X}"]
    for i, (name, _, _) in enumerate(OBJECTS):
        o.append(f"DEF NEAR_{name.upper()} EQU {i}")
    o += ["", "; The first tile of each frame: 0-3 from behind, 4-7 walking left. ROM0's copy.",
          "IF DEF(REI_WORLD_FRAMES)", "ReiWorldFrames::",
          "    db " + ",".join(str(v) for v in first), "ENDC",
          "", "IF DEF(REI_WORLD_DATA)", "",
          "; BG tiles in VRAM order under LCDC.4 = 0: numbers 128-255 are at $8800,",
          "; 0-127 at $9000 - so the table holds 128.. first, then 0..",
          "ReiWorldTiles::"]
    for i in list(range(128, 256)) + list(range(128)):
        o.append("    db " + ",".join(f"${b:02X}" for b in tile_bytes(tiles[i])) + f"  ; {i}")
    o += ["", "ReiWorldObjTiles::"]
    for i, t in enumerate(stiles):
        o.append("    db " + ",".join(f"${b:02X}" for b in tile_bytes(t)) + f"  ; {i}")
    for label, data, flag in (("ReiWorldMap", tmap, 0), ("ReiWorldAttr", amap, 0x08)):
        o += ["", f"{label}::"]
        for r in range(0, len(data), W):
            o.append("    db " + ",".join(str(v | flag) for v in data[r:r + W]))
    o += ["", "ReiPalWorld::",
          "    dw " + ",".join(f"${rgb15(c):04X}" for c in box) + "  ; the thought panel"]
    for i, q in enumerate(pals):
        o.append("    dw " + ",".join(f"${rgb15(c):04X}" for c in q) + f"  ; scene {i + 1}")
    o += ["", "ReiPalObj::",
          "    dw " + ",".join(f"${rgb15(c):04X}" for c in [(0, 0, 0), NAVY, BLUE, WHITE]),
          "",
          "; What she can see, and where across the picture (x of its centre). Not shown",
          "; and not fed to the model yet: the thought trigger records the nearest in",
          "; wWorldNear, and the words are what the observation corpus will be built on.",
          "ReiWorldObjects::"]
    for name, x, words in OBJECTS:
        o.append(f'    db {x}, "{words}", 0  ; {name}')
    o += ["", "ENDC", ""]
    DST.write_text("\n".join(o), encoding="utf-8", newline="\n")
    print(f"wrote {DST}: {len(tiles)} scene tiles ({unique} distinct, MSE {mse:.0f}), "
          f"{len(stiles)} sprite tiles")
    return res, frames


def preview(res, frames):
    from PIL import Image
    im = Image.fromarray(res).convert("RGB")
    ink = {1: NAVY, 2: BLUE, 3: WHITE}
    x = 8
    for frame in frames:
        for y, row in enumerate(frame):
            for dx, v in enumerate(row):
                if v:
                    im.putpixel((x + dx, 43 + y), ink[v])
        x += len(frame[0]) + 6
    strip = Image.new("RGB", (8 * 30, 56), (255, 0, 255))
    x = 2
    for frame in frames:
        for y, row in enumerate(frame):
            for dx, v in enumerate(row):
                if v:
                    strip.putpixel((x + dx, 4 + y), ink[v])
        x += len(frame[0]) + 4
    out = ROOT / "build" / "rei_world_preview.png"
    im.resize((768, 288), 0).save(out)
    strip.resize((strip.width * 6, strip.height * 6), 0).save(ROOT / "build" / "rei_world_frames.png")
    print("wrote", out)


if __name__ == "__main__":
    res, frames = emit()
    if "--preview" in sys.argv:
        preview(res, frames)
