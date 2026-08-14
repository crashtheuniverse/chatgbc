; Shared constants and WRAM layout.

IF !DEF(CHATGBC_INC)
DEF CHATGBC_INC EQU 1

; --- Text console -----------------------------------------------------------
; The shadow buffer uses the BG tilemap's 32-byte stride so it can be pushed to
; VRAM with a single GDMA. Only the leftmost 20 columns are visible.
DEF CON_W      EQU 32
DEF CON_H      EQU 18
DEF CON_VIS_W  EQU 20
DEF CON_SIZE   EQU CON_W * CON_H          ; 576 bytes = 36 GDMA blocks
DEF FONT_FIRST EQU 32                     ; VRAM tile N holds ASCII N + 32

; --- Profiler ---------------------------------------------------------------
; TAC_16KHZ makes TIMA tick once per 64 M-cycles. That ratio is fixed to the CPU
; clock, so it holds in double-speed mode too: the unit is cycles, not seconds.
DEF PROF_TICK_CYCLES EQU 64

; --- Status flags (wStatus) -------------------------------------------------
DEF STATUS_CGB    EQU 1 << 0
DEF STATUS_DOUBLE EQU 1 << 1

; Written to wReady once the ROM has finished its work, so the test harness
; knows when to stop ticking the emulator.
DEF READY_MAGIC EQU $5A

ENDC
