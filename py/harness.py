"""Headless PyBoy harness.

Boots build/chatgbc.gbc with no window and reads the ROM's own state back out.
Addresses come from rgblink's symbol file and constants are parsed straight out
of the assembly sources, so tests can never drift from the ROM they test.
"""

import re
from pathlib import Path

from pyboy import PyBoy

ROOT = Path(__file__).resolve().parent.parent
ROM = ROOT / "build" / "chatgbc.gbc"
SYM = ROOT / "build" / "chatgbc.sym"
SRC = ROOT / "src"

_SYM_RE = re.compile(r"^([0-9A-Fa-f]{2}):([0-9A-Fa-f]{4})\s+(\S+)$")
_DEF_RE = re.compile(r"^\s*DEF\s+(\w+)\s+EQU\s+(.+?)\s*(?:;.*)?$", re.IGNORECASE)


def load_symbols(path=SYM):
    """name -> address, from the rgblink .sym file."""
    syms = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _SYM_RE.match(line.strip())
        if m:
            syms.setdefault(m.group(3), int(m.group(2), 16))
    return syms


def load_defs(*paths):
    """Evaluate `DEF NAME EQU expr` from assembly sources into a dict."""
    defs = {}
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            m = _DEF_RE.match(line)
            if not m:
                continue
            expr = re.sub(r"\$([0-9A-Fa-f]+)", r"0x\1", m.group(2))
            expr = re.sub(r"%([01]+)", r"0b\1", expr)
            try:
                defs[m.group(1)] = eval(expr, {"__builtins__": {}}, dict(defs))
            except Exception:
                pass  # symbolic or address-valued DEFs are not needed here
    return defs


class Rom:
    """A booted ROM plus typed accessors for its WRAM."""

    def __init__(self, rom=ROM, sym=SYM):
        if not rom.exists():
            raise FileNotFoundError(f"{rom} missing - run .\\build.ps1")
        self.defs = load_defs(SRC / "chatgbc.inc", SRC / "model.inc",
                              SRC / "main.asm", SRC / "matvec.asm", SRC / "chatgbc.inc")
        self.syms = load_symbols(sym)
        self.pyboy = PyBoy(str(rom), window="null", cgb=True, sound_emulated=False)
        # Without this PyBoy paces itself to real time, which for a ROM that
        # spends seconds per token makes the test loop unusable.
        self.pyboy.set_emulation_speed(0)
        self.frames = 0

    def close(self):
        self.pyboy.stop(save=False)

    # --- memory ---------------------------------------------------------

    def addr(self, name):
        return self.syms[name]

    def read(self, name, count=1):
        a = self.addr(name)
        return bytes(self.pyboy.memory[a : a + count])

    def read_u32(self, name):
        return int.from_bytes(self.read(name, 4), "little")

    # --- execution ------------------------------------------------------

    def run_until_ready(self, max_frames=900):
        """Tick until the ROM sets wReady, or give up. Returns frames elapsed."""
        magic = self.defs["READY_MAGIC"]
        ready = self.addr("wReady")
        for _ in range(max_frames):
            self.pyboy.tick(1, False)
            self.frames += 1
            if self.pyboy.memory[ready] == magic:
                return self.frames
        raise TimeoutError(
            f"wReady never reached {magic:#04x} within {max_frames} frames "
            f"(last value {self.pyboy.memory[ready]:#04x})"
        )

    # --- text -----------------------------------------------------------

    def _decode(self, buf):
        w, vis, h = self.defs["CON_W"], self.defs["CON_VIS_W"], self.defs["CON_H"]
        first = self.defs["FONT_FIRST"]
        return [
            "".join(chr(t + first) for t in buf[r * w : r * w + vis]).rstrip()
            for r in range(h)
        ]

    def console_lines(self):
        """The shadow buffer, as text. This is what the ROM believes it drew."""
        return self._decode(self.read("wConsole", self.defs["CON_SIZE"]))

    def vram_lines(self):
        """The BG tilemap, as text. This is what the PPU will actually show."""
        w, h = self.defs["CON_W"], self.defs["CON_H"]
        buf = bytes(self.pyboy.memory[0x9800 : 0x9800 + w * h])
        return self._decode(buf)

    def text(self):
        return "\n".join(self.console_lines()).rstrip()


    def screenshot(self, path):
        """Save the rendered frame. Pixel-level checks are the only way to catch
        a font that decodes to the right tiles but the wrong shapes."""
        self.pyboy.tick(1, True)
        self.pyboy.screen.image.resize((480, 432), 0).save(path)
        return path


if __name__ == "__main__":
    import sys

    rom = Rom()
    frames = rom.run_until_ready()
    print(f"ready after {frames} frames\n")
    print(rom.text())
    print()
    status = rom.read("wStatus")[0]
    print(f"status      {status:#04x}")
    print(f"prof ticks  {rom.read_u32('wProfTicks')}")
    print(f"prof cycles {rom.read_u32('wProfCycles')}")
    if "--png" in sys.argv:
        print("saved", rom.screenshot(ROOT / "build" / "screen.png"))
    rom.close()
