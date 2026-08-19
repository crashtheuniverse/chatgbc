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
LAB_ROM = ROOT / "build" / "chatgbc-lab.gbc"
LAB_SYM = ROOT / "build" / "chatgbc-lab.sym"
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

    def __init__(self, rom=None, sym=None, dirty_ram=False, lab=False):
        """lab boots build/chatgbc-lab.gbc, the ROM with no keyboard or frame.

        The demo boots into an entry screen and waits for START, which costs the
        suite wall-clock for presentation no test is checking. The lab ROM parks
        in an idle loop instead and takes its prompt and token count from here,
        so a test can ask for the shortest run that proves its point.

        dirty_ram fills WRAM with a non-zero pattern before the CPU runs.

        PyBoy powers up with RAM at zero; real hardware and SameBoy do not. Any
        variable the ROM reads before writing therefore behaves differently on
        hardware, which is exactly how a stale accumulator flag passed every
        headless test and produced nonsense on a real emulator.
        """
        self.lab = lab
        rom = rom or (LAB_ROM if lab else ROM)
        sym = sym or (LAB_SYM if lab else SYM)
        if not rom.exists():
            flag = " -Lab" if lab else ""
            raise FileNotFoundError(f"{rom} missing - run .\\build.ps1{flag}")
        self.defs = load_defs(SRC / "chatgbc.inc", SRC / "model.inc",
                              SRC / "boot.asm", SRC / "matvec.asm", SRC / "generate.asm")
        self.syms = load_symbols(sym)
        self.pyboy = PyBoy(str(rom), window="null", cgb=True, sound_emulated=False)
        # Without this PyBoy paces itself to real time, which for a ROM that
        # spends seconds per token makes the test loop unusable.
        self.pyboy.set_emulation_speed(0)
        self.frames = 0
        if dirty_ram:
            self._dirty_ram()

    def _dirty_ram(self):
        """Scribble over WRAM before the first tick, simulating a cold boot."""
        junk = bytes(range(256)) * 16                     # 4 KB, no long zero runs
        self.pyboy.memory[0xC000:0xD000] = junk
        for bank in range(1, 8):
            self.pyboy.memory[bank, 0xD000:0xE000] = junk
        # HRAM holds the shared 32-bit scratch and the matvec product table,
        # and unlike WRAM the ROM does not clear it at boot - so it needs the
        # same treatment, or moving a variable there quietly escapes this test.
        self.pyboy.memory[0xFF80:0xFFFF] = junk[:0x7F]
        # wReady is the harness handshake, not model state. The pattern above can
        # land READY_MAGIC there by coincidence, which makes run_until_ready
        # return before the ROM has executed a single instruction.
        self.pyboy.memory[self.addr("wReady")] = 0x00

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

    def run_until_ready(self, max_frames=900, press_start=True):
        """Tick until the ROM sets wReady, or give up. Returns frames elapsed.

        The ROM opens on the keyboard screen with a default prompt, so the
        harness taps START once to begin generation - the same thing a player
        does, which means the entry screen is on the tested path too.
        """
        magic = self.defs["READY_MAGIC"]
        ready = self.addr("wReady")
        # Tap START repeatedly during startup rather than once: the entry screen
        # only appears after the VRAM clear, font load and calibration, and a
        # single early press would land before anything is listening.
        for _ in range(max_frames):
            if press_start and self.frames < 400 and self.frames % 20 == 0:
                self.pyboy.button_press("start")
            elif press_start and self.frames % 20 == 8:
                self.pyboy.button_release("start")
            self.pyboy.tick(1, False)
            self.frames += 1
            if self.pyboy.memory[ready] == magic:
                return self.frames
        raise TimeoutError(
            f"wReady never reached {magic:#04x} within {max_frames} frames "
            f"(last value {self.pyboy.memory[ready]:#04x})"
        )

    def lab_run(self, steps=None, prompt=None, max_frames=400000):
        """Drive one generation on the lab ROM. Returns frames elapsed.

        Safe to call repeatedly on the same instance: the ROM returns to its
        idle loop afterwards, so a booted emulator can serve several runs.
        """
        if not self.lab:
            raise RuntimeError("lab_run needs Rom(lab=True)")
        idle, go = self.defs["LAB_IDLE"], self.defs["LAB_GO"]
        state, goflag = self.addr("wLabState"), self.addr("wLabGo")
        self.pyboy.memory[goflag] = 0
        self._tick_until(lambda: self.pyboy.memory[state] == idle, 2000,
                         "lab ROM never reached its idle loop")

        if prompt is not None:
            raw = prompt.encode("ascii")
            if len(raw) > self.defs["PROMPT_MAX"]:
                raise ValueError(f"prompt longer than {self.defs['PROMPT_MAX']}")
            base = self.addr("wPromptText")
            self.pyboy.memory[base : base + len(raw)] = list(raw)
            self.pyboy.memory[self.addr("wPromptLen")] = len(raw)
        if steps is not None:
            self.pyboy.memory[self.addr("wGenSteps")] = steps

        ready, magic = self.addr("wReady"), self.defs["READY_MAGIC"]
        self.pyboy.memory[ready] = 0
        self.pyboy.memory[goflag] = go
        start = self.frames
        self._tick_until(lambda: self.pyboy.memory[ready] == magic, max_frames,
                         "lab run never finished")
        self.pyboy.memory[goflag] = 0        # release the ROM back to idle
        return self.frames - start

    def _tick_until(self, done, max_frames, what):
        for _ in range(max_frames):
            if done():
                return self.frames
            self.pyboy.tick(1, False)
            self.frames += 1
        raise TimeoutError(f"{what} within {max_frames} frames")

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
    frames = rom.run_until_ready(max_frames=400000)
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
