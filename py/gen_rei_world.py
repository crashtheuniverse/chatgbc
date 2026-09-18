"""Draw the beach Rei walks along and write src/rei_world_art.inc.

Run through py/gen_rei_art.py (which calls emit() here), or alone:

    python py/gen_rei_world.py --preview     also build/rei_world_preview.png

The scene is one strip, 32 tiles wide and 12 tall - 256 x 96 pixels, exactly
the width the BG map wraps at, so scrolling SCX goes round it for ever:

    rows 0-2   sky: a sun, two clouds, a pale haze over the horizon
    row  3     the far sea; its top edge is the horizon, on a tile boundary
    row  4     waves           two tiles alternating, two frames each
    row  5     the shore       the same: foam, wet sand, sand
    rows 6-11  sand, and what stands on it: a palm, a deck chair, a parasol,
               a sandcastle, two shells and a crab; rows 9-10 are left clear,
               because that is where she walks

Every tile has one palette (CGB attributes), so everything is drawn on a tile
grid: an object claims whole tiles and brings its own palette, whose colour 0
is the sand it stands on. Nothing crosses the seam at x = 255 -> 0.

The world's tiles live in VRAM bank 1 ($8000, attribute bit 3), beside the
chat screen's tiles in bank 0: both screens stay loaded and going from one to
the other loads nothing. The tile numbers at the front of the set are fixed,
because the VBlank handler animates the sea by flipping bit 0 of the tile
number along rows 4 and 5 (frame A is even, frame B is the odd tile after it),
and because an 8 x 16 sprite takes an even tile and the odd one after it.

Rei herself is a 16 x 16 sprite, two 8 x 16 objects: two walking frames and
one looking out to sea, drawn facing right and mirrored by the OAM flip bit.
"""

import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "src" / "rei_world_art.inc"

W, H = 32, 12                         # tiles
SKY, SUN, SEA, SHORE, SAND, PALM, TOY = 1, 2, 3, 4, 5, 6, 7     # BG palettes; 0 is the thought box
ROW_FAR, ROW_WAVE, ROW_SHORE, ROW_SAND = 3, 4, 5, 6

# Fixed tile numbers (see the docstring).
T_BLANK, T_WAVE, T_SHORE, T_SPRITE, T_SCENE = 0, 2, 6, 12, 24
SPRITE_FRAMES = ["WALK_A", "WALK_B", "LOOK"]


def rgb(r, g, b):
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


CREAM, INK = (248, 236, 184), (40, 28, 40)
SKY_C, SEA_C, SAND_C = (120, 200, 248), (40, 120, 216), (248, 224, 152)
PALETTES = [
    ("W_BOX",   [CREAM, (176, 168, 152), (96, 88, 96), INK]),                  # the thought box: the chat's ink
    ("W_SKY",   [SKY_C, (184, 228, 248), (255, 255, 255), (216, 236, 248)]),   # sky, haze, cloud, cloud shade
    ("W_SUN",   [SKY_C, (184, 228, 248), (255, 232, 80), (248, 176, 40)]),    # sky, haze, sun, rim
    ("W_SEA",   [SEA_C, (104, 176, 240), (240, 250, 255), (24, 88, 184)]),     # sea, light, foam, deep
    ("W_SHORE", [SAND_C, (216, 184, 112), (240, 250, 255), SEA_C]),            # sand, wet sand, foam, sea
    ("W_SAND",  [SAND_C, (255, 240, 192), (216, 184, 112), (136, 96, 56)]),    # sand, light, dark, brown
    ("W_PALM",  [SAND_C, (96, 200, 80), (32, 136, 56), (120, 80, 40)]),        # sand, leaf, dark leaf, trunk
    ("W_TOY",   [SAND_C, (255, 255, 255), (224, 56, 56), (72, 48, 40)]),       # sand, white, red, dark
]
OBJ_PALETTE = [(0, 0, 0), (248, 208, 176), (152, 96, 200), INK]               # -, skin, hair, ink

# What is where, for the retrain: the thought trigger records the nearest of
# these (wWorldNear). x is the centre, in pixels along the strip.
OBJECTS = [
    ("palm",   36, "palm tree green tall"),
    ("chair",  80, "chair red sit rest"),
    ("cloud", 108, "cloud white soft slow"),
    ("shell", 134, "shell small pink"),
    ("waves", 152, "waves foam come go"),
    ("sand",  176, "sand warm castle"),
    ("sun",   204, "sun warm bright"),
    ("crab",  220, "crab red small still"),
    ("sea",   248, "sea big blue far"),
]

KEY = {"#": 3, "+": 2, "-": 1, ".": 0}

PALM_ART = ["....++....++++..........",
            "..++--++.+----++..++++..",
            ".+----+++--++--+++----+.",
            "+--++--+--+++++--++++--+",
            "+-+..+---++-++---+..++-+",
            ".+..+--++-###-++--+...+.",
            "...+--+.+-##+.+.+--+....",
            "..+--+..+.##...+.+--+...",
            "..+-+.....##......+-+...",
            "..++......###.....++....",
            "...........##...........",
            "...........###..........",
            "............##..........",
            "............###.........",
            ".............##.........",
            ".............###........",
            ".............###........",
            "..............###.......",
            "..............###.......",
            "..............###.......",
            "..............####......",
            ".............#####......",
            "............--####-.....",
            "........................"]

CHAIR_ART = ["................",
             "................",
             "..#.............",
             "..#+............",
             "..#++...........",
             "...#-+..........",
             "...#++-.........",
             "....#-++........",
             "....#++-+.......",
             ".....#-++-......",
             ".....#++-++####.",
             "......#########.",
             "......#..#...#..",
             ".....#....#..#..",
             "....#......#.#..",
             "...##.......###."]

PARASOL_ART = ["...........##...........",
               "........+++--+++........",
               ".....+++---++---+++.....",
               "...++---+++--+++---++...",
               "..+---++++----++++---+..",
               ".+--+++++------+++++--+.",
               "+--+++++--------+++++--+",
               "+-++++.+--++++--+.++++-+",
               "++....++..+##+..++....++",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "...........##...........",
               "..........-##-..........",
               ".........--##--.........",
               "........................"]

CASTLE_ART = ["................",
              ".......#+.......",
              ".......#++......",
              ".......#........",
              "..-.-.-#-.-.-...",
              "..-----------...",
              "..-+-+-+-+-+-...",
              "..-----------...",
              "-.-.--+###+--.-.",
              "-----+#####+----",
              "-+-+-+#####+-+-+",
              "------#####-----",
              "-+----#####---+-",
              "------#####-----",
              "++++++++++++++++",
              ".+.+.+.+.+.+.+.."]
CASTLE_KEY = {"#": 3, "+": 2, "-": 1}

SHELL_ART = ["........",
             "..####..",
             ".#-+-+#.",
             "#-+-+-+#",
             "#-+-+-+#",
             ".#-+-+#.",
             "..#--#..",
             "...##..."]

CRAB_ART = ["................",
            ".##..........##.",
            "#++#........#++#",
            "#+#..#....#..#+#",
            ".#..#-#..#-#..#.",
            ".#...#++++#...#.",
            "..#.++++++++.#..",
            "...++++++++++...",
            "..#++++++++++#..",
            ".#.#++++++++#.#.",
            "#...#.#..#.#...#",
            "................"]

SPRITES = {
    "WALK_A": ["................",
               "....######......",
               "...#++++++#.....",
               "..#++++++++#....",
               "..#+++++---#....",
               "..#++++--#-#....",
               "..#+++------#...",
               "..#+++-----#....",
               "...#++#####.....",
               "....#++++#......",
               "...#-++++-#.....",
               "...#-++++-#.....",
               "....#++++#......",
               "....#+##+#......",
               "...##...##......",
               "..###...###....."],
    "WALK_B": ["................",
               "....######......",
               "...#++++++#.....",
               "..#++++++++#....",
               "..#+++++---#....",
               "..#++++--#-#....",
               "..#+++------#...",
               "..#+++-----#....",
               "...#++#####.....",
               "....#++++#......",
               "....#-+++#......",
               "....#+-++#......",
               "....#++++#......",
               ".....#++#.......",
               ".....#--#.......",
               ".....####......."],
    "LOOK":   ["................",
               "....######......",
               "...#++++++#.....",
               "..#++++++++#....",
               "..#++++++++#....",
               "..#++++++++#....",
               "..#++++++++#....",
               "..#++++++++#....",
               "...#++++++#.....",
               "....#++++#......",
               "...#-++++-#.....",
               "...#-++++-#.....",
               "....#++++#......",
               "....#+##+#......",
               "....#-##-#......",
               "....##..##......"],
}


def canvas(w, h, fill=0):
    return [[fill] * w for _ in range(h)]


def stamp(img, x0, y0, rows, key=KEY):
    for dy, line in enumerate(rows):
        for dx, ch in enumerate(line):
            if ch in key and key[ch]:
                img[y0 + dy][x0 + dx] = key[ch]


def disc(img, cx, cy, r, colour):
    for y in range(len(img)):
        for x in range(len(img[0])):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                img[y][x] = colour


def wave_tile(phase, frame):
    t = canvas(8, 8)
    for x in range(8):
        a = 2 * math.pi * (x + phase * 8 + frame * 5) / 16
        y = 3 + round(1.6 * math.sin(a))
        t[y][x] = 2
        t[y + 1][x] = 1
        if (x + phase * 8 + frame * 3) % 16 in (3, 4, 5):
            t[7][x] = 1                                  # a glint lower down
    return t


def shore_tile(phase, frame):
    t = canvas(8, 8)
    for x in range(8):
        a = 2 * math.pi * (x + phase * 8) / 16
        edge = 3 + round(1.2 * math.sin(a)) + frame
        for y in range(8):
            t[y][x] = 3 if y < edge - 1 else 2 if y <= edge else 1 if y <= edge + 2 else 0
    return t


def scene():
    """The 256 x 96 picture and each tile's palette. Rows 4 and 5 are laid
    straight from the fixed tiles and stay blank here."""
    img = canvas(W * 8, H * 8)
    pal = [[SKY] * W for _ in range(3)] + [[SEA] * W for _ in range(2)] + \
          [[SHORE] * W] + [[SAND] * W for _ in range(6)]

    for x in range(W * 8):                               # haze over the horizon
        for y in (21, 22, 23):
            img[y][x] = 1
    for cx, cy, scale in ((48, 11, 1.0), (128, 8, 0.8)):  # clouds: lobes on a flat base
        for dx, dy, r in ((-9, 2, 5), (0, -1, 7), (9, 2, 5), (-3, 3, 5), (4, 3, 5)):
            disc(img, cx + dx * scale, cy + dy * scale, r * scale, 2)
        for x in range(W * 8):
            for y in range(int(cy + 5 * scale), 24):
                if img[y][x] == 2:
                    img[y][x] = 1 if y >= 21 else 0
    for ty in range(3):                                  # the sun has its tiles to itself
        for tx in (24, 25, 26):
            pal[ty][tx] = SUN
    disc(img, 204, 10, 9.5, 3)                           # colour 1 stays the haze
    disc(img, 204, 10, 8, 2)

    for x in range(W * 8):                               # the far sea: deep at the horizon, glints
        img[24][x] = 3
        img[25][x] = 3
        if x % 16 in (2, 3, 4, 5):
            img[28][x] = 1
        if x % 32 in (18, 19, 20):
            img[30][x] = 1

    def claim(tx, ty, tw, th, palette):
        for y in range(ty, ty + th):
            for x in range(tx, tx + tw):
                assert pal[y][x] == SAND, (x, y)
                pal[y][x] = palette

    claim(3, 6, 3, 3, PALM)
    stamp(img, 24, 48, PALM_ART)
    claim(9, 7, 2, 2, TOY)
    stamp(img, 72, 56, CHAIR_ART)
    claim(11, 6, 3, 3, TOY)
    stamp(img, 88, 48, PARASOL_ART)
    stamp(img, 168, 56, CASTLE_ART, CASTLE_KEY)          # the castle is sand: no claim
    claimed_by_castle = {(21, 7), (22, 7), (21, 8), (22, 8)}
    claim(16, 7, 1, 1, TOY)                              # her lane, rows 9-10, stays clear
    stamp(img, 128, 56, SHELL_ART)
    claim(18, 11, 1, 1, TOY)
    stamp(img, 144, 88, SHELL_ART)
    claim(27, 6, 2, 2, TOY)                              # the crab, up by the water
    stamp(img, 216, 51, CRAB_ART)

    grains = [[(1, 2, 1), (5, 6, 2)], [(6, 1, 2), (2, 5, 1)], [(3, 3, 1)], []]
    for ty in range(ROW_SAND, H):                        # sand grain, on plain sand only:
        for tx in range(W):                              # four tiles, scattered
            if pal[ty][tx] != SAND or (tx, ty) in claimed_by_castle:
                continue
            for x, y, c in grains[(tx * 7 + ty * 13 + (tx * ty) % 5) % 4]:
                img[ty * 8 + y][tx * 8 + x] = c
    return img, pal


def cut(img, tx, ty, w=8, h=8):
    return [row[tx:tx + w] for row in img[ty:ty + h]]


def build():
    tiles = [canvas(8, 8) for _ in range(T_SCENE)]
    for phase in (0, 1):
        for frame in (0, 1):
            tiles[T_WAVE + phase * 2 + frame] = wave_tile(phase, frame)
            tiles[T_SHORE + phase * 2 + frame] = shore_tile(phase, frame)
    for i, name in enumerate(SPRITE_FRAMES):
        rows = [[KEY[c] for c in line] for line in SPRITES[name]]
        for col in (0, 1):
            for half in (0, 1):
                tiles[T_SPRITE + i * 4 + col * 2 + half] = cut(rows, col * 8, half * 8)

    img, pal = scene()
    index = {tuple(map(tuple, tiles[T_BLANK])): T_BLANK}
    tmap, amap = [], []
    for ty in range(H):
        for tx in range(W):
            if ty == ROW_WAVE:
                n = T_WAVE + (tx & 1) * 2
            elif ty == ROW_SHORE:
                n = T_SHORE + (tx & 1) * 2
            else:
                t = cut(img, tx * 8, ty * 8)
                key = tuple(map(tuple, t))
                if key not in index:
                    index[key] = len(tiles)
                    tiles.append(t)
                n = index[key]
            tmap.append(n)
            amap.append(pal[ty][tx] | 0x08)              # bit 3: the tile is in VRAM bank 1
    assert len(tiles) <= 256, len(tiles)
    return tiles, tmap, amap, img, pal


def tile_bytes(t):
    out = []
    for row in t:
        lo = hi = 0
        for v in row:
            lo = (lo << 1) | (v & 1)
            hi = (hi << 1) | (v >> 1)
        out += [lo, hi]
    return out


def emit():
    tiles, tmap, amap, _, _ = build()
    o = ["; Generated by py/gen_rei_world.py - do not edit.",
         "; The beach: tiles for VRAM bank 1, the 32 x 12 strip and its attributes,",
         "; the palettes, Rei's sprite frames, and where things are.",
         "",
         f"DEF WORLD_TILES EQU {len(tiles)}",
         f"DEF WORLD_W EQU {W}",
         f"DEF WORLD_H EQU {H}",
         f"DEF WORLD_ROW_WAVE EQU {ROW_WAVE}",
         f"DEF WORLD_ROW_SHORE EQU {ROW_SHORE}",
         f"DEF WORLD_OBJECTS EQU {len(OBJECTS)}"]
    for i, name in enumerate(SPRITE_FRAMES):
        o.append(f"DEF SPR_{name} EQU {T_SPRITE + i * 4}")
    for i, (name, _, _) in enumerate(OBJECTS):
        o.append(f"DEF NEAR_{name.upper()} EQU {i}")
    o += ["", "IF DEF(REI_WORLD_DATA)", "", "ReiWorldTiles::"]
    for i, t in enumerate(tiles):
        o.append("    db " + ",".join(f"${b:02X}" for b in tile_bytes(t)) + f"  ; {i}")
    for label, data in (("ReiWorldMap", tmap), ("ReiWorldAttr", amap)):
        o += ["", f"{label}::"]
        for r in range(0, len(data), W):
            o.append("    db " + ",".join(str(v) for v in data[r:r + W]))
    o += ["", "ReiPalWorld::"]
    for name, cols in PALETTES:
        o.append("    dw " + ",".join(f"${rgb(*c):04X}" for c in cols) + f"  ; {name}")
    o += ["", "ReiPalObj::",
          "    dw " + ",".join(f"${rgb(*c):04X}" for c in OBJ_PALETTE),
          "",
          "; What she can see, and where along the strip (x of its centre). Not shown and",
          "; not fed to the model yet: the thought trigger records the nearest in",
          "; wWorldNear, and the words are what the observation corpus will be built on.",
          "ReiWorldObjects::"]
    for name, x, words in OBJECTS:
        o.append(f'    db {x}, "{words}", 0  ; {name}')
    o += ["", "ENDC", ""]
    DST.write_text("\n".join(o), encoding="utf-8", newline="\n")
    print(f"wrote {DST}: {len(tiles)} world tiles")


def preview():
    from PIL import Image
    tiles, tmap, amap, _, _ = build()
    im = Image.new("RGB", (W * 8, H * 8 + 20), (255, 255, 255))
    for frame in (0,):
        for ty in range(H):
            for tx in range(W):
                n, p = tmap[ty * W + tx], PALETTES[amap[ty * W + tx] & 7][1]
                for y in range(8):
                    for x in range(8):
                        im.putpixel((tx * 8 + x, ty * 8 + y), p[tiles[n][y][x]])
    for i, name in enumerate(SPRITE_FRAMES):
        for y, line in enumerate(SPRITES[name]):
            for x, c in enumerate(line):
                if KEY[c]:
                    im.putpixel((60 + i * 40 + x, 64 + y), OBJ_PALETTE[KEY[c]])
    out = ROOT / "build" / "rei_world_preview.png"
    im.resize((im.width * 4, im.height * 4), 0).save(out)
    print("wrote", out)


if __name__ == "__main__":
    emit()
    if "--preview" in sys.argv:
        preview()
