"""Draw Rei's tiles and write src/rei_art.inc.

Everything the Rei screen shows that is not a font glyph is drawn here, in
code, as 2bpp Game Boy tiles: the window frames, the face (4 x 4 tiles, one
picture per mood plus a blink and two talking mouths), the mood icons, the
arrows, the keyboard's OK key, and the splash logotype.
Pictures are composed as whole images, cut into 8 x 8 tiles and de-duplicated,
so the assembly side only ever sees tile data and small maps of tile indices.

    python py/gen_rei_art.py             write src/rei_art.inc, and the world's
                                         src/rei_world_art.inc (py/gen_rei_world.py)
    python py/gen_rei_art.py --preview   also write build/rei_art_preview.png

Two tile sets share one VRAM range (tiles REI_TILE_BASE and up): the splash
set while the splash is up, the main set afterwards.

Colours inside a tile are 0..3; what they look like is the palette's business
(the tables at the end). 0 is always the paper, 3 always the ink.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DST = ROOT / "src" / "rei_art.inc"
TILE_BASE = 104                      # first tile after the font (FONT_GLYPHS)


# --- small raster helpers ----------------------------------------------------

def canvas(w, h, fill=0):
    return [[fill] * w for _ in range(h)]


def ellipse(img, cx, cy, rx, ry, colour, only=None):
    for y, row in enumerate(img):
        for x in range(len(row)):
            dx, dy = (x + 0.5 - cx) / rx, (y + 0.5 - cy) / ry
            if dx * dx + dy * dy <= 1.0 and (only is None or row[x] in only):
                row[x] = colour


def rect(img, x0, y0, x1, y1, colour):
    for y in range(max(y0, 0), min(y1 + 1, len(img))):
        for x in range(max(x0, 0), min(x1 + 1, len(img[0]))):
            img[y][x] = colour


def dots(img, colour, points):
    for x, y in points:
        if 0 <= y < len(img) and 0 <= x < len(img[0]):
            img[y][x] = colour


def art(img, x0, y0, rows, key):
    """Stamp ASCII art: `key` maps a character to a colour, others skip."""
    for dy, line in enumerate(rows):
        for dx, ch in enumerate(line):
            if ch in key:
                dots(img, key[ch], [(x0 + dx, y0 + dy)])


def outline(img, colour=3, paper=0):
    """Ink every paper pixel that touches a painted one."""
    h, w = len(img), len(img[0])
    edge = []
    for y in range(h):
        for x in range(w):
            if img[y][x] != paper:
                continue
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h and img[ny][nx] not in (paper, colour):
                    edge.append((x, y))
                    break
    dots(img, colour, edge)


def mirror(rows):
    return [r[::-1] for r in rows]


# --- frames ------------------------------------------------------------------
# A four-pixel pipe, two pixels in from the tile edge: ink, light, colour, ink
# from the outside in. Corners are quarter circles about the tile's inner
# corner, so the same radial rule draws edges and corners and they always meet.

def pipe(r):
    band = {5: 3, 4: 1, 3: 2, 2: 3}
    return band.get(int(r), 0)


def frame_tiles():
    t = {}
    edge = [pipe(7.5 - i) for i in range(8)]            # outside at index 0
    t["FR_T"] = [[edge[y]] * 8 for y in range(8)]
    t["FR_B"] = t["FR_T"][::-1]
    t["FR_L"] = [list(edge) for _ in range(8)]
    t["FR_R"] = mirror(t["FR_L"])
    tl = canvas(8, 8)
    for y in range(8):
        for x in range(8):
            r = ((8 - x - 0.5) ** 2 + (8 - y - 0.5) ** 2) ** 0.5
            tl[y][x] = pipe(r)
    t["FR_TL"] = tl
    t["FR_TR"] = mirror(tl)
    t["FR_BL"] = tl[::-1]
    t["FR_BR"] = mirror(tl[::-1])
    return t


# --- small symbols -----------------------------------------------------------

KEY = {"#": 3, "+": 2, "-": 1}

SYMBOLS = {
    "ARROW_R": ["........",
                ".##.....",
                ".####...",
                ".######.",
                ".######.",
                ".####...",
                ".##.....",
                "........"],
    "ARROW_UP": ["........",
                 "...##...",
                 "..####..",
                 ".######.",
                 ".######.",
                 "........",
                 "........",
                 "........"],
    "DOT": ["........",
            "........",
            "........",
            "...++...",
            "...++...",
            "........",
            "........",
            "........"],
}
SYMBOLS["OK"] = ["........",                # the keyboard's send key
                 "......#.",
                 "......#.",
                 "..#...#.",
                 ".##...#.",
                 "#######.",
                 ".##.....",
                 "..#....."]
SYMBOLS["THINK"] = ["..####..",               # the thought box's title: a thought bubble
                    ".#....#.",
                    "#......#",
                    "#......#",
                    ".#....#.",
                    "..####..",
                    ".##.....",
                    "#......."]
SYMBOLS["ARROW_L"] = mirror(SYMBOLS["ARROW_R"])
SYMBOLS["ARROW_DN"] = SYMBOLS["ARROW_UP"][::-1]

# The mood icons, one a mood, each its own shape and its own colour.
ICON_HAPPY = ["..###...###..",
              ".#+++#.#+++#.",
              "#+--++#+++++#",
              "#+-+++++++++#",
              "#+++++++++++#",
              "#+++++++++++#",
              ".#+++++++++#.",
              "..#+++++++#..",
              "...#+++++#...",
              "....#+++#....",
              ".....#+#.....",
              "......#......"]

ICON_CALM = [".........####",
             ".......##++-#",
             ".....##+++-+#",
             "....#++++-++#",
             "...#++++-+++#",
             "..#++++-++++#",
             "..#+++-++++#.",
             ".#+++-+++++#.",
             ".#++-+++++#..",
             ".#+-++++##...",
             ".#-+####.....",
             ".##.#........",
             "#............"]

ICON_CURIOUS = ["..#####.....#..",
                ".#+++++#...#-#.",
                "#++###++#.#---#",
                "#++#..#++#.#-#.",
                ".##..#+++#..#..",
                "....#+++#......",
                "...#+++#.......",
                "...#++#........",
                "...#++#........",
                "....##.........",
                "...#++#........",
                "...#++#........",
                "....##........."]

ICON_SAD = [".....#.....",
            "....#+#....",
            "....#+#....",
            "...#+++#...",
            "...#+-+#...",
            "..#++-++#..",
            "..#+-+++#..",
            ".#++-++++#.",
            ".#+-+++++#.",
            "#++-++++++#",
            "#+++++++++#",
            "#+++++++++#",
            ".#+++++++#.",
            "..#######.."]

# --- the mood band: an icon, centred under the face --------------------------

MOODS = [("calm", ICON_CALM), ("happy", ICON_HAPPY), ("curious", ICON_CURIOUS), ("sad", ICON_SAD)]
BAND_W, BAND_H = 6, 3                 # tiles


def mood_band(icon):
    """The icon over a reminder in tiny capitals: START is the log."""
    img = canvas(BAND_W * 8, BAND_H * 8)
    w = len(icon[0])
    art(img, (BAND_W * 8 - w) // 2, 1, icon, KEY)
    text = "START:LOG"
    tiny(img, (BAND_W * 8 - (len(text) * 4 - 1)) // 2, 17, text, 3)
    return img


# --- the face ----------------------------------------------------------------
# 32 x 32: paper 0, skin 1, hair 2, ink 3. One head, and the expression is
# stamped over it: brows, eyes, mouth.

EYE_OPEN = [".###.",
            "#####",
            "#..##",
            "#.###",
            "#####",
            "#####",
            ".###."]
EYE_UP = [".###.",
          "##..#",
          "##..#",
          "#####",
          "#####",
          ".###.",
          "....."]
EYE_HALF = [".....",
            ".....",
            "#####",
            "#.###",
            "#####",
            ".###.",
            "....."]
EYE_SHUT = [".....",
            ".....",
            ".....",
            ".....",
            "#...#",
            ".###.",
            "....."]
EYE_GLAD = [".....",
            ".....",
            ".###.",
            "#...#",
            "#...#",
            ".....",
            "....."]

MOUTH = {
    "calm":  ["#....#",
              ".####.",
              "......",
              "......"],
    "glad":  ["######",
              "#----#",
              ".#--#.",
              "..##.."],
    "oh":    ["..##..",
              ".#--#.",
              ".#--#.",
              "..##.."],
    "sad":   ["......",
              ".####.",
              "#....#",
              "......"],
    "shut":  ["......",
              ".####.",
              "......",
              "......"],
    "open":  [".####.",
              "#----#",
              "#----#",
              ".####."],
}

BROW = {
    "none": ([], []),
    "up":   (["####.", "....."], [".....", ".####"]),       # one raised
    "sad":  (["...##", "###.."], ["##...", "..###"]),
}
BROW["up"] = (["#####"], [".####", "#...."])


def head():
    img = canvas(32, 32)
    ellipse(img, 16, 15.5, 14, 15, 2)                   # hair, a bob
    rect(img, 0, 29, 31, 31, 0)
    ellipse(img, 16, 19, 10.5, 11.5, 1)                 # face
    rect(img, 6, 6, 25, 11, 2)                          # fringe
    for x0 in (6, 11, 16, 21):                          # cut into points
        art(img, x0, 12, ["+++++", ".+++.", "..+.."], {"+": 2})
    rect(img, 13, 29, 18, 31, 1)                        # neck
    ellipse(img, 16, 36, 13, 6, 2, only=(0,))           # collar
    dots(img, 0, [(9, 4), (10, 3), (11, 3), (12, 2), (13, 2)])   # shine
    dots(img, 0, [(8, 6), (8, 7)])
    outline(img)
    return img


def face(eyes_l, eyes_r, mouth, brow="none", tear=False):
    img = head()
    key = {"#": 3, ".": None, "-": 0}
    key = {k: v for k, v in key.items() if v is not None}
    eye_key = {"#": 3, ".": 0}
    # eyes are stamped with their whites; a shut eye leaves skin
    for rows, x0 in ((eyes_l, 8), (eyes_r, 19)):
        shut = rows in (EYE_SHUT, EYE_GLAD)
        art(img, x0, 15, rows, {"#": 3} if shut else _eye_key(rows))
    art(img, 13, 24, MOUTH[mouth], {"#": 3, "-": 0})
    bl, br = BROW[brow]
    art(img, 8, 12, bl, {"#": 3})
    art(img, 19, 12, br, {"#": 3})
    if tear:
        art(img, 22, 22, [".+.", "+0+", "+++", ".+."], {"+": 2, "0": 0})
    return img


def _eye_key(rows):
    return {"#": 3, ".": 0} if rows is not EYE_HALF else {"#": 3}


def faces():
    """name -> image. The order here is the order of the face maps."""
    return [
        ("CALM", face(EYE_OPEN, EYE_OPEN, "calm")),
        ("HAPPY", face(EYE_GLAD, EYE_GLAD, "glad")),
        ("CURIOUS", face(EYE_UP, EYE_UP, "oh", "up")),
        ("SAD", face(EYE_HALF, EYE_HALF, "sad", "sad", tear=True)),
        ("CALM_BLINK", face(EYE_SHUT, EYE_SHUT, "calm")),
        ("HAPPY_BLINK", face(EYE_GLAD, EYE_GLAD, "glad")),
        ("CURIOUS_BLINK", face(EYE_SHUT, EYE_SHUT, "oh", "up")),
        ("SAD_BLINK", face(EYE_SHUT, EYE_SHUT, "sad", "sad", tear=True)),
        ("TALK_A", face(EYE_OPEN, EYE_OPEN, "shut")),
        ("TALK_B", face(EYE_OPEN, EYE_OPEN, "open")),
    ]


# --- the title ----------------------------------------------------------------
# The maintainer's design, at the screen's own resolution: REI in slab letters
# cut on the diagonal, a red line that runs behind them from corner to corner,
# the character for zero (rei) on the left, four small words on the right.
# Colours: 0 night, 2 red, 3 white (the font's own colour).
LOGO_W, LOGO_H = 20, 9                # tiles; the picture sits on tile row 1
WHITE, RED = 3, 2

KANJI = [".#########.",
         ".....#.....",
         "###########",
         "#.##.#.##.#",
         "..##.#.##..",
         "....#.#....",
         "..##.#.##..",
         "##.......##",
         "..#######..",
         "....#...#..",
         "....#..##..",
         "....#......",
         "....#......"]

TINY = {"A": "####.#####.##.#", "B": "##.#.###.#.###.", "E": "####..##.#..###",
        "I": "###.#..#..#.###", "N": "##.#.##.##.##.#", "G": "####..#.##.####",
        "C": "####..#..#..###", "R": "##.#.###.#.##.#", "T": "###.#..#..#..#.",
        "D": "##.#.##.##.###.", " ": "." * 15,
        "S": "####..###..####", "L": "#..#..#..#..###", "O": "####.##.##.####",
        ":": "....#.....#...."}


def tiny(img, x, y, text, colour=WHITE):
    """Capitals three pixels wide and five tall."""
    for ch in text:
        g = TINY[ch]
        for i, v in enumerate(g):
            if v == "#":
                img[y + i // 3][x + i % 3] = colour
        x += 4


def logo():
    """The title, 160 x 72. Every span below is (row, first x, last x)."""
    W, H, Y0 = LOGO_W * 8, LOGO_H * 8, 8         # Y0: the screen row of the picture's top
    img = canvas(W, H)

    def span(y, x0, x1, colour=WHITE):
        for x in range(x0, x1 + 1):
            img[y - Y0][x] = colour

    X = 24                                       # the R's left corner
    for y in range(21, 30):                      # R: the top bar, leaning
        span(y, X + (y - 21), X + 30 + (y - 21))
    for y in range(30, 43):                      #    the bowl's side
        span(y, X + 31, X + 40)
    for y in range(38, 43):                      #    the bowl's floor, cut at 45 degrees
        span(y, X + 19 + (y - 38), X + 40)
    for y in range(32, 63):                      #    the stem, its top cut the same way
        span(y, X + 8, X + 8 + min(11, y - 32))
    for y in range(43, 63):                      #    the leg
        span(y, X + 24 + (y - 43), X + 31 + (y - 43))
    for y in range(29, 34):                      # E: the top bar
        span(y, X + 45 + (y - 29), X + 75)
    for y in range(35, 55):                      #    the stem
        span(y, X + 47, X + 47 + min(9, y - 35))
    for y in range(43, 48):                      #    the middle bar
        span(y, X + 47, X + 72)
    for y in range(55, 63):                      #    the foot, leaning with the R
        span(y, X + 48 + (y - 55), X + 73 + (y - 55))
    for y in range(21, 63):                      # I, its corner cut away...
        span(y, X + 82, X + 83 + min(11, y - 21))
    for y in range(21, 32):                      # ...and given back in red
        span(y, X + 86 + (y - 21), X + 96, RED)

    # the line: corner to corner, behind the letters, not drawn between R and E
    for x in range(W):
        if X + 30 <= x <= X + 47:
            continue
        yl = 12 + (W - 1 - x) * 65 / (W - 1)
        for y in (int(yl), int(yl) + 1):         # two pixels thick
            if 0 <= y - Y0 < H and img[y - Y0][x] == 0:
                img[y - Y0][x] = RED

    for i, row in enumerate(KANJI):              # zero, and a rule under it
        for j, v in enumerate(row):
            if v == "#":
                img[40 - Y0 + i][12 + j] = RED
    span(56, 12, 22, RED)

    tx = X + 99
    tiny(img, tx, 34 - Y0, "A")
    tiny(img, tx, 41 - Y0, "BEING")
    tiny(img, tx, 48 - Y0, "IN A")
    tiny(img, tx, 55 - Y0, "CARTRIDGE")
    span(62, tx, tx + 7, RED)
    return img


# --- cutting pictures into tiles ---------------------------------------------

class TileSet:
    def __init__(self):
        self.tiles = []              # tuples of 64 colours
        self.index = {}
        self.names = {}

    def add(self, tile, name=None):
        key = tuple(v for row in tile for v in row)
        if key not in self.index:
            self.index[key] = len(self.tiles)
            self.tiles.append(key)
        if name:
            self.names[name] = self.index[key]
        return self.index[key]

    def cut(self, img):
        """The picture as a flat map of tile numbers, row-major."""
        out = []
        for ty in range(len(img) // 8):
            for tx in range(len(img[0]) // 8):
                out.append(self.add([r[tx * 8:tx * 8 + 8] for r in img[ty * 8:ty * 8 + 8]]))
        return out

    def data(self):
        rows = []
        for t in self.tiles:
            b = []
            for y in range(8):
                lo = hi = 0
                for x in range(8):
                    v = t[y * 8 + x]
                    lo = (lo << 1) | (v & 1)
                    hi = (hi << 1) | (v >> 1)
                b += [lo, hi]
            rows.append(b)
        return rows


# --- palettes ----------------------------------------------------------------

def rgb(r, g, b):
    """8-bit RGB to BGR555."""
    return (r >> 3) | ((g >> 3) << 5) | ((b >> 3) << 10)


CREAM = (248, 236, 184)
INK = (40, 28, 40)

MAIN_PALETTES = [
    ("INK",   [CREAM, (176, 168, 152), (96, 88, 96), INK]),          # face frame, plain text
    ("RED",   [CREAM, (248, 168, 160), (208, 56, 64), INK]),         # her words
    ("BLUE",  [CREAM, (152, 200, 248), (48, 96, 208), INK]),         # your words
    ("GREEN", [CREAM, (168, 224, 144), (48, 144, 72), INK]),         # the keys
    ("PICK",  [(48, 144, 72), (168, 224, 144), (248, 236, 184), CREAM]),  # the key under the cursor
    ("FACE",  [CREAM, (248, 208, 176), (152, 96, 200), INK]),        # paper, skin, hair, ink
    ("AMBER", [CREAM, (248, 216, 96), (224, 144, 32), INK]),         # curious
    ("CURSOR", [(176, 224, 152), (120, 192, 112), (48, 144, 72), INK]),  # the row or cell under the cursor
]

# The log screen borrows the cursor's slot while it is open: the player's lines.
YOURS = ("YOURS", [CREAM, (152, 200, 248), (48, 96, 208), (40, 72, 184)])

NIGHT = (20, 30, 64)
SPLASH_PALETTES = [
    ("S_TEXT", [NIGHT, (96, 104, 160), (240, 56, 64), (236, 236, 236)]),   # night, -, red, white
    ("S_DIM", [NIGHT, NIGHT, NIGHT, NIGHT]),                          # PRESS START, blinked off
]


# --- output ------------------------------------------------------------------

def build():
    main = TileSet()
    main.add(canvas(8, 8), "BLANK")
    for name, tile in frame_tiles().items():
        main.add(tile, name)
    for name, rows in SYMBOLS.items():
        t = canvas(8, 8)
        art(t, 0, 0, rows, KEY)
        main.add(t, name)
    face_maps = [(n, main.cut(img)) for n, img in faces()]
    mood_maps = [(w, main.cut(mood_band(icon))) for w, icon in MOODS]

    splash = TileSet()
    splash.add(canvas(8, 8), "S_BLANK")
    t = canvas(8, 8)                             # the menu's cursor, in red
    for y in range(7):
        for x in range(1, 2 + min(y, 6 - y)):
            t[y][x] = RED
    splash.add(t, "S_ARROW")
    limg = logo()
    logo_map = splash.cut(limg)
    return main, face_maps, mood_maps, splash, logo_map, limg


def emit(main, face_maps, mood_maps, splash, logo_map):
    assert TILE_BASE + len(main.tiles) <= 256, len(main.tiles)
    assert TILE_BASE + len(splash.tiles) <= 256, len(splash.tiles)
    o = ["; Generated by py/gen_rei_art.py - do not edit.",
         "; Rei's tiles (2bpp), the maps that arrange them, and the palettes.",
         "; Tile numbers are VRAM indices: the sets load at REI_TILE_BASE.",
         "",
         f"DEF REI_TILE_BASE EQU {TILE_BASE}",
         f"DEF REI_MAIN_TILES EQU {len(main.tiles)}",
         f"DEF REI_SPLASH_TILES EQU {len(splash.tiles)}",
         f"DEF REI_LOGO_W EQU {LOGO_W}",
         f"DEF REI_LOGO_H EQU {LOGO_H}",
         f"DEF REI_BAND_W EQU {BAND_W}",
         f"DEF REI_BAND_H EQU {BAND_H}",
         ""]
    for name, i in list(main.names.items()) + list(splash.names.items()):
        o.append(f"DEF T_{name} EQU {TILE_BASE + i}")
    for i, (name, _) in enumerate(MAIN_PALETTES):
        o.append(f"DEF PAL_{name} EQU {i}")
    o.append("DEF PAL_YOURS EQU PAL_CURSOR")
    for i, (name, _) in enumerate(SPLASH_PALETTES):
        o.append(f"DEF PAL_{name} EQU {i}")
    for i, (name, _) in enumerate(face_maps):
        o.append(f"DEF FACE_{name} EQU {i}")
    o.append("")
    o.append("; The data itself, for the one file that defines REI_ART_DATA first.")
    o.append("IF DEF(REI_ART_DATA)")
    o.append("")

    def tiles(label, ts):
        o.append(f"{label}::")
        for i, row in enumerate(ts.data()):
            o.append("    db " + ",".join(f"${b:02X}" for b in row) + f"  ; {TILE_BASE + i}")
        o.append("")

    def maps(label, items, width):
        o.append(f"{label}::")
        for name, m in items:
            o.append(f"    ; {name}")
            for r in range(0, len(m), width):
                o.append("    db " + ",".join(str(TILE_BASE + v) for v in m[r:r + width]))
        o.append("")

    def pals(label, table):
        o.append(f"{label}::")
        for name, cols in table:
            o.append("    dw " + ",".join(f"${rgb(*c):04X}" for c in cols) + f"  ; {name}")
        o.append("")

    tiles("ReiTilesMain", main)
    tiles("ReiTilesSplash", splash)
    maps("ReiFaceMaps", face_maps, 4)
    maps("ReiMoodMaps", mood_maps, BAND_W)
    maps("ReiLogoMap", [("Rei", logo_map)], LOGO_W)
    pals("ReiPalMain", MAIN_PALETTES)
    pals("ReiPalSplash", SPLASH_PALETTES)
    pals("ReiPalYours", [YOURS])
    o.append("ENDC")
    o.append("")
    DST.write_text("\n".join(o), encoding="utf-8", newline="\n")
    print(f"wrote {DST}: {len(main.tiles)} main tiles, {len(splash.tiles)} splash tiles")


def preview(face_maps_imgs, limg):
    from PIL import Image
    pal_face = MAIN_PALETTES[5][1]
    pal_logo = SPLASH_PALETTES[0][1]
    pal_red = MAIN_PALETTES[1][1]
    fs = faces()
    W = 34 * len(fs)
    im = Image.new("RGB", (max(W, 300), 34 + 74 + 26 + 12), (255, 255, 255))
    for i, (_, img) in enumerate(fs):
        for y in range(32):
            for x in range(32):
                im.putpixel((i * 34 + x, y), pal_face[img[y][x]])
    for y in range(LOGO_H * 8):
        for x in range(LOGO_W * 8):
            im.putpixel((x, 34 + y), pal_logo[limg[y][x]])
    for i, (w, s) in enumerate(MOODS):
        b = mood_band(s)
        for y in range(24):
            for x in range(48):
                im.putpixel((100 + i * 50 + x, 34 + y), pal_red[b[y][x]])
    ft = frame_tiles()
    grid = [["FR_TL", "FR_T", "FR_TR"], ["FR_L", None, "FR_R"], ["FR_BL", "FR_B", "FR_BR"]]
    for gy, row in enumerate(grid):
        for gx, n in enumerate(row):
            if n:
                for y in range(8):
                    for x in range(8):
                        im.putpixel((100 + gx * 8 + x, 60 + gy * 8 + y), pal_red[ft[n][y][x]])
    out = ROOT / "build" / "rei_art_preview.png"
    im.resize((im.width * 4, im.height * 4), 0).save(out)
    print("wrote", out)


if __name__ == "__main__":
    import gen_rei_world                     # the beach has a generator of its own
    gen_rei_world.emit()
    main, face_maps, mood_maps, splash, logo_map, limg = build()
    emit(main, face_maps, mood_maps, splash, logo_map)
    if "--preview" in sys.argv:
        preview(face_maps, limg)
