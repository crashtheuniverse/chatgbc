"""Draw Rei's tiles and write src/rei_art.inc.

Everything the Rei screen shows that is not a font glyph is drawn here, in
code, as 2bpp Game Boy tiles: the window frames, the face (4 x 4 tiles, one
picture per mood plus a blink and two talking mouths), the mood band (a symbol
and the word in a compact 5 x 7 face), the arrows, and the splash logotype.
Pictures are composed as whole images, cut into 8 x 8 tiles and de-duplicated,
so the assembly side only ever sees tile data and small maps of tile indices.

    python py/gen_rei_art.py             write src/rei_art.inc
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
SYMBOLS["ARROW_L"] = mirror(SYMBOLS["ARROW_R"])
SYMBOLS["ARROW_DN"] = SYMBOLS["ARROW_UP"][::-1]

HEART = ["..##...##..",
         ".#++#.#++#.",
         "#+--+#++++#",
         "#+-++++++##",
         "#++++++++##",
         ".#++++++##.",
         "..#++++##..",
         "...#++##...",
         "....###....",
         ".....#....."]

QUESTION = ["..####...",
            ".#++++#..",
            "#++##++#.",
            ".##.#++#.",
            "...#++#..",
            "..#++#...",
            "..#++#...",
            "...##....",
            "..#++#...",
            "...##...."]

TEAR = ["....#....",
        "...#+#...",
        "...#+#...",
        "..#++-#..",
        "..#++-#..",
        ".#++++-#.",
        ".#+++++#.",
        ".#+++++#.",
        "..#+++#..",
        "...###..."]

LEAF = ["......###.",
        "....##++#.",
        "...#+++-#.",
        "..#++++-#.",
        ".#+++-++#.",
        ".#++-+++#.",
        ".#+-+++#..",
        ".#-+++#...",
        ".#####....",
        "#........."]

# --- the mood band: a symbol over the word -----------------------------------
# Seven letters have to fit in six tiles, so the word gets its own 5 x 7 face
# at a six-pixel pitch, in the manner of a character LCD.

TINY = {
    "a": [".....", ".....", ".###.", "....#", ".####", "#...#", ".####"],
    "c": [".....", ".....", ".###.", "#....", "#....", "#...#", ".###."],
    "d": ["....#", "....#", ".##.#", "#..##", "#...#", "#...#", ".####"],
    "h": ["#....", "#....", "#.##.", "##..#", "#...#", "#...#", "#...#"],
    "i": ["..#..", ".....", ".##..", "..#..", "..#..", "..#..", ".###."],
    "l": [".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "m": [".....", ".....", "##.#.", "#.#.#", "#.#.#", "#...#", "#...#"],
    "o": [".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."],
    "p": [".....", ".....", "####.", "#...#", "####.", "#....", "#...."],
    "r": [".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."],
    "s": [".....", ".....", ".###.", "#....", ".###.", "....#", "####."],
    "u": [".....", ".....", "#...#", "#...#", "#...#", "#..##", ".##.#"],
    "y": [".....", ".....", "#...#", "#...#", ".####", "....#", ".###."],
}

MOODS = [("calm", LEAF), ("happy", HEART), ("curious", QUESTION), ("sad", TEAR)]
BAND_W, BAND_H = 6, 3                 # tiles


def mood_band(word, symbol):
    img = canvas(BAND_W * 8, BAND_H * 8)
    sw = len(symbol[0])
    art(img, (BAND_W * 8 - sw) // 2, 1, symbol, KEY)
    width = len(word) * 6 - 1
    x = (BAND_W * 8 - width) // 2
    for ch in word:
        art(img, x, 13, TINY[ch], KEY)
        x += 6
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


# --- the logotype ------------------------------------------------------------
LOGO_W, LOGO_H = 12, 5                # tiles


def logo():
    """'Rei', 96 x 40: fat round letters, a highlight along the top of each
    stroke, an ink outline, and a heart for the dot of the i."""
    img = canvas(LOGO_W * 8, LOGO_H * 8)
    c = 2
    # R
    x = 9
    rect(img, x, 3, x + 7, 36, c)
    ellipse(img, x + 15, 12.5, 13, 9.5, c)
    rect(img, x, 3, x + 15, 21, c)
    ellipse(img, x + 15, 12.5, 6, 3.5, 0)
    rect(img, x + 8, 10, x + 15, 15, 0)
    for i in range(16):                                  # the leg
        rect(img, x + 11 + i * 10 // 15, 21 + i, x + 19 + i * 10 // 15, 21 + i, c)
    # e
    x = 42
    ellipse(img, x + 13, 25, 13, 12, c)
    ellipse(img, x + 13, 25, 6.5, 6, 0)
    rect(img, x + 3, 23, x + 25, 27, c)
    rect(img, x + 14, 28, x + 27, 31, 0)
    # i
    x = 75
    rect(img, x, 15, x + 7, 36, c)
    # highlight: the top two pixels of every painted run become light
    for xx in range(len(img[0])):
        for yy in range(len(img)):
            if img[yy][xx] == c and (yy == 0 or img[yy - 1][xx] in (0,)):
                img[yy][xx] = 1
                if yy + 1 < len(img) and img[yy + 1][xx] == c:
                    pass
    outline(img)
    heart = canvas(11, 10)
    art(heart, 0, 0, HEART, KEY)
    art(img, x - 2, 2, HEART, KEY)
    return img, (x - 2, 2, 11, 10)


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
    ("SPARE", [CREAM, CREAM, CREAM, INK]),
]

NIGHT = (32, 28, 64)
SPLASH_PALETTES = [
    ("S_TEXT", [NIGHT, (96, 96, 160), (168, 176, 232), (248, 240, 216)]),
    ("S_LOGO", [NIGHT, (200, 224, 255), (104, 152, 248), (16, 12, 40)]),
    ("S_HEART", [NIGHT, (255, 184, 192), (240, 64, 96), (16, 12, 40)]),
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
    mood_maps = [(w, main.cut(mood_band(w, s))) for w, s in MOODS]

    splash = TileSet()
    splash.add(canvas(8, 8), "S_BLANK")
    limg, heart_box = logo()
    logo_map = splash.cut(limg)
    hx, hy, hw, hh = heart_box
    logo_attr = []
    for ty in range(LOGO_H):
        for tx in range(LOGO_W):
            px = [(x, y) for y in range(ty * 8, ty * 8 + 8) for x in range(tx * 8, tx * 8 + 8)
                  if limg[y][x]]
            inside = [hx <= x < hx + hw and hy <= y < hy + hh for x, y in px]
            if px and all(inside):
                logo_attr.append(2)
            else:
                assert not any(inside) or not px or all(inside) or True
                logo_attr.append(1)
    return main, face_maps, mood_maps, splash, logo_map, logo_attr, limg


def emit(main, face_maps, mood_maps, splash, logo_map, logo_attr):
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
    o.append("ReiLogoAttr::")
    for r in range(0, len(logo_attr), LOGO_W):
        o.append("    db " + ",".join(str(v) for v in logo_attr[r:r + LOGO_W]))
    o.append("")
    pals("ReiPalMain", MAIN_PALETTES)
    pals("ReiPalSplash", SPLASH_PALETTES)
    o.append("ENDC")
    o.append("")
    DST.write_text("\n".join(o), encoding="utf-8", newline="\n")
    print(f"wrote {DST}: {len(main.tiles)} main tiles, {len(splash.tiles)} splash tiles")


def preview(face_maps_imgs, limg):
    from PIL import Image
    pal_face = MAIN_PALETTES[5][1]
    pal_logo = SPLASH_PALETTES[1][1]
    pal_red = MAIN_PALETTES[1][1]
    fs = faces()
    W = 34 * len(fs)
    im = Image.new("RGB", (max(W, 300), 34 + 42 + 26 + 12), (255, 255, 255))
    for i, (_, img) in enumerate(fs):
        for y in range(32):
            for x in range(32):
                im.putpixel((i * 34 + x, y), pal_face[img[y][x]])
    for y in range(40):
        for x in range(96):
            im.putpixel((x, 34 + y), pal_logo[limg[y][x]])
    for i, (w, s) in enumerate(MOODS):
        b = mood_band(w, s)
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
    main, face_maps, mood_maps, splash, logo_map, logo_attr, limg = build()
    emit(main, face_maps, mood_maps, splash, logo_map, logo_attr)
    if "--preview" in sys.argv:
        preview(face_maps, limg)
