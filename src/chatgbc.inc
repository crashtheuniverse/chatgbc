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
DEF PROMPT_MAX EQU 48                     ; characters the user can type                     ; VRAM tile N holds ASCII N + 32

; --- Model arithmetic -------------------------------------------------------
; Products are halved in the exported tables, which keeps the running sum inside
; signed 16-bit. That drops the third accumulator byte from the inner loop and
; removes the bias correction from requantization.
DEF ACC_BYTES EQU 2

; Attention scores are a separate width and must not be tied to ACC_BYTES: a
; score is q.k over HEAD_SIZE terms, up to 8 * 127 * 127 = 129,032, so it needs
; 24 bits regardless of how wide the matvec accumulator happens to be.
DEF SCORE_BYTES EQU 3

; --- Input -----------------------------------------------------------------
; Joy_Read returns the d-pad in the high nibble and buttons in the low one.
DEF KB_RIGHT EQU %00010000
DEF KB_LEFT  EQU %00100000
DEF KB_UP    EQU %01000000
DEF KB_DOWN  EQU %10000000
DEF KB_A     EQU %00000001
DEF KB_B     EQU %00000010
DEF KB_START EQU %00001000

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
