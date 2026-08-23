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

; --- Box drawing -----------------------------------------------------------
; Border tiles live just past the ASCII range, so Console_PutChar reaches them
; with ordinary character codes.
DEF CH_TL EQU 128
DEF CH_H  EQU 129
DEF CH_TR EQU 130
DEF CH_V  EQU 131
DEF CH_BL EQU 132
DEF CH_BR EQU 133
DEF CH_LT EQU 134
DEF CH_RT EQU 135

DEF BOX_R     EQU CON_VIS_W - 1           ; rightmost visible column
DEF BOX_B     EQU CON_H - 1               ; bottom row
DEF TITLE_COL EQU 1                       ; against the corner; the title's
                                          ; first letter lands on the box margin

; --- Generation ------------------------------------------------------------
; Tokens the demo ROM generates per run. The lab ROM takes its count from the
; harness instead, so a test can ask for the shortest run that proves its point.
DEF GEN_STEPS EQU 96

; What the demo generates. Deliberately well past SEQ_LEN: the cache is a ring,
; so nothing special happens at the window edge - the token counter walks past
; it, the text keeps scrolling, and the only sign anything wrapped is the cycle
; count going flat once every slot is live. That flattening is the trick, made
; visible. The test suite stays on GEN_STEPS, since a longer golden would cost
; loop latency and prove nothing extra.
DEF APP_GEN_STEPS EQU 160

; The lab ROM's handshake. It parks in an idle loop advertising LAB_IDLE, the
; harness fills in the prompt and step count, then writes LAB_GO.
DEF LAB_IDLE EQU $A5
DEF LAB_GO   EQU $C3

; --- Input -----------------------------------------------------------------
; Joy_Read returns the d-pad in the high nibble and buttons in the low one.
DEF KB_RIGHT EQU %00010000
DEF KB_LEFT  EQU %00100000
DEF KB_UP    EQU %01000000
DEF KB_DOWN  EQU %10000000
DEF KB_A     EQU %00000001
DEF KB_B     EQU %00000010
DEF KB_SELECT EQU %00000100
DEF KB_START  EQU %00001000

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
