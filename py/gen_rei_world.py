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


def rect(img, x0, y0, x1, y1, colour):
    for y in range(max(y0, 0), min(y1 + 1, len(img))):
        for x in range(max(x0, 0), min(x1 + 1, len(img[0]))):
            img[y][x] = colour


def copy(img):
    return [row[:] for row in img]


class Scene:
    """One world: its picture in two frames (they differ only where it moves),
    each tile's palette, the two rows that move and the eight palettes."""

    def __init__(self, name, img_a, img_b, pal, anim_rows, palettes, objects):
        self.name, self.img_a, self.img_b, self.pal = name, img_a, img_b, pal
        self.anim_rows, self.palettes, self.objects = anim_rows, palettes, objects


# --- the beach -----------------------------------------------------------------

def beach():
    img, pal = scene()
    img_b = copy(img)
    for tx in range(W):                                  # rows 4 and 5: the sea's two frames
        for frame, target in ((0, img), (1, img_b)):
            for row, draw in ((ROW_WAVE, wave_tile), (ROW_SHORE, shore_tile)):
                t = draw(tx & 1, frame)
                for y in range(8):
                    target[row * 8 + y][tx * 8:tx * 8 + 8] = t[y]
    return Scene("beach", img, img_b, pal, (ROW_WAVE, ROW_SHORE), PALETTES, OBJECTS)


# --- the garden ----------------------------------------------------------------
# rows 0-2 sky, 3-4 a white picket fence with a hedge behind its rail, 5 a bed
# of flowers along it (they sway: frame A / B), 6-8 lawn with a tree, a bench,
# a watering can and a pond, 9-10 the gravel path she walks, 11 more flowers
# (they sway too, a beat later).

G_SKY, G_FENCE, G_GRASS, G_FLOWER, G_TREE, G_WOOD, G_POND = 1, 2, 3, 4, 5, 6, 7
GRASS_C, SKY2_C = (120, 192, 80), (136, 200, 248)
GARDEN_PALETTES = [
    ("W_BOX",    PALETTES[0][1]),
    ("G_SKY",    [SKY2_C, (248, 248, 248), (200, 232, 248), (176, 212, 240)]),   # sky, cloud, haze, cloud shade
    ("G_FENCE",  [SKY2_C, (248, 248, 240), (168, 176, 192), (64, 144, 72)]),     # sky, white, grey, hedge
    ("G_GRASS",  [GRASS_C, (224, 200, 144), (176, 144, 96), (72, 144, 56)]),    # lawn, path, pebble, dark grass
    ("G_FLOWER", [GRASS_C, (248, 112, 160), (248, 224, 80), (48, 120, 56)]),    # lawn, pink, yellow, stem
    ("G_TREE",   [SKY2_C, (96, 176, 72), (48, 120, 56), (120, 80, 48)]),        # sky, leaf, dark leaf, trunk
    ("G_WOOD",   [GRASS_C, (208, 152, 96), (136, 88, 48), (56, 40, 40)]),       # lawn, wood, dark wood, ink
    ("G_POND",   [GRASS_C, (88, 152, 232), (176, 216, 248), (120, 128, 144)]),  # lawn, water, light, stone/tin
]
GARDEN_OBJECTS = [
    ("tree",     28, "tree green leaves shade"),
    ("fence",    64, "fence white wood garden"),
    ("bench",    92, "bench wood sit rest"),
    ("flowers", 124, "flowers pink yellow bloom"),
    ("can",     140, "watering can water flowers"),
    ("path",    160, "path stones walk"),
    ("pond",    188, "pond water still fish"),
    ("sky",     236, "sky blue cloud soft"),
]

BENCH_ART = ["........................",
             "........................",
             "..######################",
             "..#++++++++++++++++++++#",
             "..#--------------------#",
             "..######################",
             "..#++++++++++++++++++++#",
             "..######################",
             "........................",
             "#######################.",
             "#++++++++++++++++++++++#",
             "#----------------------#",
             "########################",
             ".##.................##..",
             ".##.................##..",
             ".##.................##.."]

CAN_ART = ["........",
           "..###...",
           ".#...#..",
           "#######.",
           "#++--+###",
           "#+++-+#.#",
           "#+++-+#..",
           "#######.."]

TREE_TOP = ["...........####...........",
            "........####--####........",
            "......##----++----##......",
            ".....#---++----++---#.....",
            "....#--++--------++--#....",
            "...#--+----++++----+--#...",
            "..#--++--+-------+--++-#..",
            "..#-++--------++-----+-#..",
            ".#--+----++-------++--+-#.",
            ".#-+--++-------++----+--#.",
            "#--+-------++--------++--#",
            "#-++--++--------++-----+-#",
            "#-+------++--++------+++-#",
            "#--++-------------++-----#",
            ".#-+---++---++--------+-#.",
            ".#--+-------------++-+--#.",
            "..#--++--+++---++----+-#..",
            "...#-----------------##...",
            "....##--+++-----++--#.....",
            "......###---#--#####......",
            ".........####.###.........",
            "............####..........",
            "............####..........",
            "............####.........."]
TREE_KEY = {"#": 2, "-": 1, "+": 2}


def flower(img, x, y, frame, petal):
    """A small flower, 5 wide, 7 tall, its head leaning with the frame."""
    lean = (1 if frame else 0)
    for dy in range(3):                                  # the stem
        img[y + 4 + dy][x + 2 + (lean if dy == 0 else 0)] = 3
    img[y + 5][x + 1] = 3                                # a leaf
    hx = x + 1 + lean
    for dx, dy in ((1, 0), (0, 1), (2, 1), (1, 2)):
        img[y + dy][hx + dx] = petal
    img[y + 1][hx + 1] = 2 if petal == 1 else 1           # the middle


def garden():
    a = canvas(W * 8, H * 8)
    pal = [[G_SKY] * W for _ in range(3)] + [[G_FENCE] * W for _ in range(2)] + \
          [[G_FLOWER] * W] + [[G_GRASS] * W for _ in range(6)]
    for cx, cy, s in ((56, 9, 0.9), (168, 13, 0.7), (228, 7, 0.6)):     # clouds
        for dx, dy, r in ((-9, 2, 5), (0, -1, 7), (9, 2, 5), (-3, 3, 5), (4, 3, 5)):
            disc(a, cx + dx * s, cy + dy * s, r * s, 1)
        for x in range(W * 8):
            for y in range(int(cy + 5 * s), 24):
                if a[y][x] == 1:
                    a[y][x] = 0                  # a flat base
    for x in range(W * 8):                               # haze low in the sky
        for y in (22, 23):
            a[y][x] = 2

    for x in range(W * 8):                               # the fence: pickets and rails,
        p = x % 8                                        # the hedge behind them
        for y in range(24, 40):
            a[y][x] = 3 if y >= 30 else 0
        if 1 <= p <= 5:
            top = 25 if p in (2, 3, 4) else 26
            for y in range(top, 40):
                a[y][x] = 1
            if p == 5:
                for y in range(top, 40):
                    a[y][x] = 2
        for y in (29, 36):                               # the rails
            a[y][x] = 1 if p not in (6, 7, 0) or y == 29 else a[y][x]
            if p in (6, 7, 0):
                a[y][x] = 2
    b = copy(a)

    for x in range(W * 8):                               # row 5: lawn under the flower bed
        for y in range(40, 48):
            a[y][x] = b[y][x] = 0
    for i in range(W * 2):                               # the bed: two flowers a tile
        x = i * 4 - 2 + (i % 3)
        if not 0 <= x <= W * 8 - 7:
            continue
        petal = 1 if i % 3 else 2
        flower(a, x, 40, 0, petal)
        flower(b, x, 40, 1, petal)

    def claim(tx, ty, tw, th, palette):
        for y in range(ty, ty + th):
            for x in range(tx, tx + tw):
                pal[y][x] = palette

    grass = [[(1, 2), (5, 5)], [(6, 1), (2, 6)], [(3, 3)], []]
    for ty in range(6, H):                               # lawn tufts
        for tx in range(W):
            for x, y in grass[(tx * 7 + ty * 11) % 4]:
                a[ty * 8 + y][tx * 8 + x] = b[ty * 8 + y][tx * 8 + x] = 3
    for x in range(W * 8):                               # the path, rows 9-10
        for y in range(72, 88):
            edge = (y == 72 or y == 87)
            v = 1
            if edge and (x // 2) % 3 == 0:
                v = 0
            if not edge and ((x * 7 + y * 13) % 23) == 0:
                v = 2
            a[y][x] = b[y][x] = v
        a[72][x] = b[72][x] = 3 if (x // 3) % 2 == 0 else 1

    # the tree: its crown over the sky, the hedge behind its trunk, then the
    # trunk goes on down the lawn in wood colours
    claim(2, 0, 3, 5, G_TREE)
    for img in (a, b):
        for y in range(0, 40):
            for x in range(16, 40):
                img[y][x] = 2 if y >= 30 else 0          # sky, and the hedge low down
        for x in range(25, 31):                           # the trunk
            for y in range(20, 40):
                img[y][x] = 3
        for cx, cy, r in ((28, 13, 9.5), (21.5, 19, 5), (34.5, 19, 5), (24, 8, 5.5), (32, 8, 5.5), (28, 21, 6.5)):
            disc(img, cx, cy, r, 2)                       # the crown, inside its three tiles
        for cx, cy, r in ((27, 11, 8), (21.5, 17, 3.5), (34, 17, 3.5), (24, 7, 4), (31, 7, 4), (28, 20, 4.5)):
            disc(img, cx, cy, r, 1)
        for x, y in ((22, 10), (30, 6), (33, 14), (25, 15), (31, 20), (19, 16), (27, 11)):
            img[y][x] = img[y][x + 1] = 2                 # a few darker leaves
    claim(3, 5, 1, 2, G_WOOD)
    for img in (a, b):
        for y in range(40, 56):
            for x in range(24, 32):
                img[y][x] = 0
            for x in range(25, 31):
                img[y][x] = 2 if x in (25, 30) else 1
        for x in (24, 31):                                # the roots
            img[54][x] = img[55][x] = 2

    claim(10, 6, 3, 2, G_WOOD)                           # the bench
    stamp(a, 80, 48, BENCH_ART, KEY)
    stamp(b, 80, 48, BENCH_ART, KEY)
    claim(17, 7, 2, 1, G_POND)                           # the watering can
    stamp(a, 136, 56, CAN_ART, {"#": 3, "+": 1, "-": 2})
    stamp(b, 136, 56, CAN_ART, {"#": 3, "+": 1, "-": 2})
    claim(21, 6, 5, 3, G_POND)                           # the pond
    for img in (a, b):
        for y in range(48, 72):
            for x in range(168, 208):
                if ((x - 188) / 19) ** 2 + ((y - 60) / 10) ** 2 <= 1:
                    img[y][x] = 3
                if ((x - 188) / 17) ** 2 + ((y - 60) / 8.5) ** 2 <= 1:
                    img[y][x] = 1
                elif img[y][x] == 3 and (x + y) % 3 == 0:
                    img[y][x] = 2
        for x0, y0 in ((178, 56), (194, 62)):            # glints
            for dx in range(4):
                img[y0][x0 + dx] = 2

    for i in range(W * 2):                               # row 11: flowers at the front
        x = i * 4 + (i * 5) % 3
        if not 0 <= x <= W * 8 - 7 or i % 5 == 3:
            continue
        petal = 2 if i % 2 else 1
        flower(a, x, 89, 0, petal)
        flower(b, x, 89, 1, petal)
    for tx in range(W):
        pal[11][tx] = G_FLOWER
        for y in range(88, 96):
            for x in range(tx * 8, tx * 8 + 8):
                for img in (a, b):
                    if img[y][x] == 3 and pal[11][tx] == G_FLOWER and y < 89:
                        img[y][x] = 0
    return Scene("garden", a, b, pal, (5, 11), GARDEN_PALETTES, GARDEN_OBJECTS)


# --- the playroom --------------------------------------------------------------
# rows 0-5 a papered wall with a window (curtains that stir), a shelf of books
# and a clock, row 6 the skirting board, 7-11 a wooden floor with a rug; on it a
# teddy bear, a stack of blocks, a ball, a spinning top and a toy train (the top
# spins and the train's wheels turn: frame A / B).

P_WALL, P_WINDOW, P_WOOD, P_FLOOR, P_RUG, P_TOYS, P_BEAR = 1, 2, 3, 4, 5, 6, 7
WALL_C, PLANK_C = (248, 216, 168), (208, 152, 96)
PLAYROOM_PALETTES = [
    ("W_BOX",    PALETTES[0][1]),
    ("P_WALL",   [WALL_C, (240, 196, 150), (224, 168, 128), (88, 56, 48)]),        # paper, stripe, dot, ink
    ("P_WINDOW", [WALL_C, (136, 200, 248), (248, 248, 240), (224, 80, 88)]),       # paper, sky, white, red
    ("P_WOOD",   [WALL_C, (200, 136, 80), (136, 80, 48), (72, 48, 40)]),           # paper, wood, dark wood, ink
    ("P_FLOOR",  [PLANK_C, (232, 184, 120), (168, 112, 64), (120, 72, 40)]),       # plank, light, dark, gap
    ("P_RUG",    [(96, 144, 216), (144, 192, 240), (248, 232, 184), (56, 88, 160)]),   # rug, light, cream, dark
    ("P_TOYS",   [PLANK_C, (224, 64, 64), (248, 216, 72), (96, 56, 40)]),         # plank, red, yellow, gap/ink
    ("P_BEAR",   [PLANK_C, (160, 96, 48), (232, 184, 128), (96, 56, 40)]),         # plank, fur, light fur, gap/ink
]
PLAYROOM_OBJECTS = [
    ("clock",    36, "clock round tick time"),
    ("bear",     52, "teddy bear soft brown"),
    ("window",  116, "window sky outside light"),
    ("rug",     124, "rug blue soft floor"),
    ("top",     188, "top spin round toy"),
    ("ball",    172, "ball red round bounce"),
    ("shelf",   200, "shelf books stories"),
    ("blocks",  212, "blocks build tower"),
    ("train",   236, "train toy wheels track"),
]

BEAR_ART = [".##........##...",
            "#-+#......#+-#..",
            "#++########++#..",
            ".#++++++++++#...",
            "#+++#++++#+++#..",
            "#++++++++++++#..",
            "#+++++##+++++#..",
            ".#+++-##-+++#...",
            "..##+----+##....",
            ".#++#----#++#...",
            "#++#------#++#..",
            "#++#------#++#..",
            ".##++----++##...",
            ".##+######+##...",
            "#+++#....#+++#..",
            ".###......###..."]

BLOCKS_ART = ["....########....",
              "....#------#....",
              "....#-++++-#....",
              "....#-+--+-#....",
              "....#-++++-#....",
              "....#------#....",
              "....########....",
              "################",
              "#++++++##------#",
              "#+----+##-++++-#",
              "#+-++-+##-+--+-#",
              "#+----+##-++++-#",
              "#++++++##------#",
              "################"]

BALL_ART = ["..####..",
            ".#++-+#.",
            "#++--++#",
            "#+-++-+#",
            "#-++++-#",
            "#++--++#",
            ".#+++-#.",
            "..####.."]


def top_art(frame):
    rows = ["...##...",
            "..####..",
            ".#+-+-#.",
            "#+-+-+-#",
            "#-+-+-+#",
            ".#-+-+#.",
            "..#++#..",
            "...##..."]
    if frame:
        rows = [r.replace("+", "x").replace("-", "+").replace("x", "-") for r in rows]
    return rows


def train(img, x0, y0, frame):
    """A toy engine and a wagon, 24 x 8: red and yellow, wheels that turn."""
    rect(img, x0 + 2, y0 + 1, x0 + 7, y0 + 4, 1)          # the cab
    rect(img, x0 + 3, y0 + 2, x0 + 6, y0 + 3, 2)          # its window
    rect(img, x0 + 8, y0 + 3, x0 + 13, y0 + 5, 1)         # the boiler
    rect(img, x0 + 10, y0, x0 + 11, y0 + 2, 3)            # the chimney
    rect(img, x0 + 2, y0 + 5, x0 + 13, y0 + 5, 1)
    rect(img, x0 + 16, y0 + 2, x0 + 22, y0 + 5, 2)        # the wagon
    rect(img, x0 + 16, y0 + 2, x0 + 22, y0 + 2, 3)
    img[y0 + 4][x0 + 14] = img[y0 + 4][x0 + 15] = 3       # the coupling
    for x in (x0 + 2, x0 + 7, x0 + 11, x0 + 16, x0 + 20):  # wheels: three by three
        for dy in range(3):
            for dx in range(3):
                img[y0 + 5 + dy][x + dx] = 3
        img[y0 + 6][x + 1] = 2
        if frame:
            img[y0 + 5][x + 1] = img[y0 + 7][x + 1] = 2
        else:
            img[y0 + 6][x] = img[y0 + 6][x + 2] = 2


def playroom():
    a = canvas(W * 8, H * 8)
    pal = [[P_WALL] * W for _ in range(6)] + [[P_WOOD] * W] + [[P_FLOOR] * W for _ in range(5)]
    for x in range(W * 8):                               # wallpaper: soft stripes and dots
        for y in range(48):
            a[y][x] = 1 if x % 16 in (0, 1, 8) else 0
            if x % 16 == 12 and y % 16 == 6:
                a[y][x] = 2
    for x in range(W * 8):                               # skirting board
        for y in range(48, 56):
            a[y][x] = 3 if y in (48, 55) else 1 if y < 51 else 2
    for x in range(W * 8):                               # planks
        for y in range(56, 96):
            a[y][x] = 0
            if (y - 56) % 8 == 7:
                a[y][x] = 3
            elif (x + ((y - 56) // 8) * 20) % 40 == 0:
                a[y][x] = 3
            elif (x * 3 + y * 7) % 29 == 0:
                a[y][x] = 2
            elif (y - 56) % 8 == 0:
                a[y][x] = 1

    imgs = [a]

    def claim(tx, ty, tw, th, palette):
        """A tile takes another palette: its wallpaper or its planks go plain
        first, since their colours mean something else there."""
        for ty_ in range(ty, ty + th):
            for tx_ in range(tx, tx + tw):
                pal[ty_][tx_] = palette
                for img in imgs:
                    for y in range(ty_ * 8, ty_ * 8 + 8):
                        for x in range(tx_ * 8, tx_ * 8 + 8):
                            if ty_ < 6 or img[y][x] != 3:
                                img[y][x] = 0

    # the window: tiles 12-16, rows 1-4, curtains in tiles 11 and 17
    claim(11, 0, 7, 5, P_WINDOW)
    for y in range(0, 40):
        for x in range(88, 144):
            a[y][x] = 0
    for y in range(8, 36):
        for x in range(96, 136):
            a[y][x] = 2 if (y in (8, 9, 34, 35) or x in (96, 97, 134, 135, 115, 116) or y == 21) else 1
    for cx, cy in ((106, 15), (124, 27)):                # a cloud in each pane
        for dx, dy, r in ((-3, 0, 3), (0, -1, 3.5), (3, 0, 3)):
            disc_on(a, cx + dx, cy + dy, r, 2, 96, 134, 10, 33)
    for x in range(88, 144):                             # the rod
        a[5][x] = a[6][x] = 3 if x in (88, 143) else 2
    b = copy(a)
    imgs.append(b)

    def curtain(img, x0, lean):
        for y in range(4, 40):
            w = 7 if y < 30 else 7 + (lean if y > 33 else 0)
            for dx in range(8):
                x = x0 + dx if x0 < 110 else x0 + 7 - dx
                if dx < w:
                    img[y][x] = 3
                if dx in (2, 5) and y < 36:
                    img[y][x] = 0 if dx == 5 and x0 < 110 else img[y][x]
        for y in range(36, 40):                          # the hem stirs
            for dx in range(8):
                x = x0 + dx if x0 < 110 else x0 + 7 - dx
                img[y][x] = 3 if (dx + y + lean) % 4 else 0
    curtain(a, 88, 0)
    curtain(b, 88, 1)
    curtain(a, 136, 0)
    curtain(b, 136, 1)
    for y in range(40, 48):                              # the window sill
        for x in range(88, 144):
            for img in (a, b):
                img[y][x] = 3 if y == 47 else 1
    claim(11, 5, 7, 1, P_WOOD)

    claim(3, 1, 3, 3, P_WOOD)                            # the clock
    for img in (a, b):
        for y in range(8, 32):
            for x in range(24, 48):
                d = ((x - 36) ** 2 + (y - 20) ** 2) ** 0.5
                if d <= 10.5:
                    img[y][x] = 3 if d > 9 else 1
        for y in range(13, 21):
            img[y][36] = 3
        for x in range(36, 42):
            img[20][x] = 3
        for dx, dy in ((0, -8), (8, 0), (0, 8), (-8, 0)):
            img[20 + dy][36 + dx] = 2

    claim(24, 1, 5, 3, P_WINDOW)                         # the shelf and its books
    claim(24, 4, 5, 1, P_WOOD)
    for img in (a, b):
        x = 194
        for i, (w, h, c) in enumerate(((5, 18, 1), (4, 14, 3), (6, 20, 2), (4, 16, 1),
                                       (5, 12, 3), (3, 17, 2), (4, 19, 1))):
            for y in range(32 - h, 32):
                for dx in range(w):
                    img[y][x + dx] = c
                img[y][x] = 3 if c != 3 else 1
            for dx in range(w):
                img[32 - h][x + dx] = 3 if c != 3 else 2
            x += w + 1
        for x in range(192, 232):
            for y in range(32, 36):
                img[y][x] = 3 if y == 35 else 1
    for img in (a, b):
        for x in range(192, 232):
            for y in range(32, 40):
                if y >= 36:
                    img[y][x] = 1 if x in (196, 227) and y < 39 else 0

    claim(10, 8, 11, 4, P_RUG)                           # the rug
    for img in (a, b):
        for y in range(64, 96):
            for x in range(80, 168):
                edge = y in (64, 95) or x in (80, 167)
                img[y][x] = 3 if edge else 2 if (y in (67, 92) or x in (83, 164)) else 0
                if not edge and 70 <= y <= 89 and 88 <= x <= 159 and (x - y) % 12 == 0:
                    img[y][x] = 1
                if (x in (80, 167)) and y % 2:
                    img[y][x] = 2

    claim(5, 7, 2, 2, P_BEAR)                            # the teddy bear, sitting
    stamp(a, 42, 56, BEAR_ART, {"#": 3, "+": 1, "-": 2})
    claim(25, 7, 2, 2, P_TOYS)                           # the blocks
    stamp(a, 200, 56, BLOCKS_ART, {"#": 3, "+": 1, "-": 2})
    claim(21, 8, 1, 1, P_TOYS)                           # the ball
    stamp(a, 168, 64, BALL_ART, {"#": 3, "+": 1, "-": 2})
    for img in (b,):
        stamp(img, 42, 56, BEAR_ART, {"#": 3, "+": 1, "-": 2})
        stamp(img, 200, 56, BLOCKS_ART, {"#": 3, "+": 1, "-": 2})
        stamp(img, 168, 64, BALL_ART, {"#": 3, "+": 1, "-": 2})

    claim(23, 11, 1, 1, P_TOYS)                          # the spinning top, front row
    stamp(a, 184, 88, top_art(0), {"#": 3, "+": 1, "-": 2})
    stamp(b, 184, 88, top_art(1), {"#": 3, "+": 1, "-": 2})
    claim(27, 11, 3, 1, P_TOYS)                          # the train, front row
    train(a, 216, 88, 0)
    train(b, 216, 88, 1)
    return Scene("playroom", a, b, pal, (11, 4), PLAYROOM_PALETTES, PLAYROOM_OBJECTS)


def disc_on(img, cx, cy, r, colour, x0, x1, y0, y1):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= r * r:
                img[y][x] = colour


SCENES = [beach, garden, playroom]


# --- tiles ---------------------------------------------------------------------

def build(scene):
    """Tile numbers: 12-23 are her sprite's in every scene; a cell that moves is
    an even tile (frame A) and the odd one after it (frame B), paired from 0 up,
    past the sprite; every other cell takes the next free number."""
    tiles = [None] * 256
    for i, name in enumerate(SPRITE_FRAMES):
        rows = [[KEY[c] for c in line] for line in SPRITES[name]]
        for col in (0, 1):
            for half in (0, 1):
                tiles[T_SPRITE + i * 4 + col * 2 + half] = cut(rows, col * 8, half * 8)
    pair_slots = [i for i in range(0, 256, 2) if not T_SPRITE <= i < T_SCENE]
    index, pairs = {}, {}
    tmap, amap, masks = [0] * (W * H), [0] * (W * H), []
    moving = set()
    for row in scene.anim_rows:
        mask = 0
        for tx in range(W):
            ta = cut(scene.img_a, tx * 8, row * 8)
            tb = cut(scene.img_b, tx * 8, row * 8)
            if ta != tb:
                mask |= 1 << tx
                moving.add((row, tx))
                key = (tuple(map(tuple, ta)), tuple(map(tuple, tb)))
                if key not in pairs:
                    n = pair_slots.pop(0)
                    tiles[n], tiles[n + 1] = ta, tb
                    pairs[key] = n
                    index.setdefault(key[0], n)
                tmap[row * W + tx] = pairs[key]
        masks.append((row, mask))
    free = (i for i in range(256) if tiles[i] is None)
    for ty in range(H):
        for tx in range(W):
            if (ty, tx) not in moving:
                assert cut(scene.img_a, tx * 8, ty * 8) == cut(scene.img_b, tx * 8, ty * 8), \
                    (scene.name, tx, ty, "moves outside the two rows")
                t = cut(scene.img_a, tx * 8, ty * 8)
                key = tuple(map(tuple, t))
                if key not in index:
                    n = next(free)
                    tiles[n] = t
                    index[key] = n
                tmap[ty * W + tx] = index[key]
            amap[ty * W + tx] = scene.pal[ty][tx] | 0x08    # bit 3: VRAM bank 1
    count = max(i for i in range(256) if tiles[i] is not None) + 1
    tiles = [t if t is not None else canvas(8, 8) for t in tiles[:count]]
    return tiles, tmap, amap, masks


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
    o = ["; Generated by py/gen_rei_world.py - do not edit.",
         "; The worlds: per scene its tiles for VRAM bank 1, its 32 x 12 strip and",
         "; attributes (GDMA sources: 16-byte aligned), its palettes, the two rows that",
         "; move and which cells in them, and where things are. Rei's sprite is the",
         "; same in every scene (tiles 12-23).",
         "",
         f"DEF WORLD_SCENES EQU {len(SCENES)}",
         f"DEF WORLD_W EQU {W}",
         f"DEF WORLD_H EQU {H}"]
    for i, name in enumerate(SPRITE_FRAMES):
        o.append(f"DEF SPR_{name} EQU {T_SPRITE + i * 4}")
    built = []
    for s, make in enumerate(SCENES):
        scene = make()
        tiles, tmap, amap, masks = build(scene)
        built.append((scene, tiles, tmap, amap, masks))
        o.append(f"DEF SCENE_{scene.name.upper()} EQU {s}")
        for i, (name, _, _) in enumerate(scene.objects):
            o.append(f"DEF NEAR_{scene.name.upper()}_{name.upper()} EQU {i}")
    o += ["", "IF DEF(REI_WORLD_DATA)", "",
          "; A scene: tiles, tile count, map (the attributes follow it), palettes,",
          "; objects, and the two moving rows: row, then a 32-bit mask of its cells.",
          "ReiScenes::"]
    for scene, tiles, _, _, masks in built:
        n = scene.name.capitalize()
        o.append(f"    dw ReiTiles{n}, {len(tiles)}, ReiMap{n}, ReiPal{n}, ReiObjects{n}")
        for row, mask in masks:
            o.append(f"    db {row}, " + ", ".join(f"${(mask >> (8 * k)) & 0xFF:02X}" for k in range(4)))
    for scene, tiles, tmap, amap, _ in built:
        n = scene.name.capitalize()
        o += ["", "PUSHS", f'SECTION "Rei world {scene.name}", ROMX, BANK[REI_WORLD_BANK], ALIGN[4]',
              f"ReiTiles{n}:"]
        for i, t in enumerate(tiles):
            o.append("    db " + ",".join(f"${b:02X}" for b in tile_bytes(t)) + f"  ; {i}")
        o.append(f"ReiMap{n}:")
        for r in range(0, len(tmap), W):
            o.append("    db " + ",".join(str(v) for v in tmap[r:r + W]))
        o.append(f"ReiAttr{n}:")
        for r in range(0, len(amap), W):
            o.append("    db " + ",".join(str(v) for v in amap[r:r + W]))
        o += ["POPS", "", f"ReiPal{n}:"]
        for name, cols in scene.palettes:
            o.append("    dw " + ",".join(f"${rgb(*c):04X}" for c in cols) + f"  ; {name}")
        o += ["", "; What she can see there, and where along the strip (x of its centre). Not",
              "; shown and not fed to the model yet: the thought trigger records the nearest",
              "; in wWorldNear (and the scene in wWorldScene); the words are for the corpus.",
              f"ReiObjects{n}:", f"    db {len(scene.objects)}"]
        for name, x, words in scene.objects:
            o.append(f'    db {x}, "{words}", 0  ; {name}')
    o += ["", "ReiPalObj::",
          "    dw " + ",".join(f"${rgb(*c):04X}" for c in OBJ_PALETTE),
          "", "ENDC", ""]
    DST.write_text("\n".join(o), encoding="utf-8", newline="\n")
    for scene, tiles, _, _, masks in built:
        print(f"  {scene.name}: {len(tiles)} tiles, moving cells "
              f"{[bin(m).count('1') for _, m in masks]}")
    print(f"wrote {DST}")
    return built


def preview(built):
    from PIL import Image
    im = Image.new("RGB", (W * 8 * 2 + 8, (H * 8 + 8) * len(built)), (255, 255, 255))
    for s, (scene, tiles, tmap, amap, masks) in enumerate(built):
        for frame in (0, 1):
            flip = {(row, tx) for row, m in masks for tx in range(W) if m >> tx & 1} if frame else set()
            for ty in range(H):
                for tx in range(W):
                    n = tmap[ty * W + tx] ^ (1 if (ty, tx) in flip else 0)
                    p = scene.palettes[amap[ty * W + tx] & 7][1]
                    for y in range(8):
                        for x in range(8):
                            im.putpixel((frame * (W * 8 + 8) + tx * 8 + x, s * (H * 8 + 8) + ty * 8 + y),
                                        p[tiles[n][y][x]])
        for i, name in enumerate(SPRITE_FRAMES):             # her, standing where she walks
            for y, line in enumerate(SPRITES[name]):
                for x, c in enumerate(line):
                    if KEY[c]:
                        im.putpixel((60 + i * 40 + x, s * (H * 8 + 8) + 72 + y), OBJ_PALETTE[KEY[c]])
    out = ROOT / "build" / "rei_world_preview.png"
    im.resize((im.width * 3, im.height * 3), 0).save(out)
    print("wrote", out)


if __name__ == "__main__":
    built = emit()
    if "--preview" in sys.argv:
        preview(built)
