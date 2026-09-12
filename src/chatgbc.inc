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
; Greedy decoding is a fixed point: argmax is deterministic, so once the state
; drifts back near one it has already visited, the model re-enters the same
; cycle and stays there. It is not a quantization artifact - fp32 at full
; context loops sooner than this cartridge does, at token 36 against 58.
;
; So the decoder refuses to complete a 4-gram it has already emitted, taking the
; next-best token instead. Deterministic, which keeps the golden-token contract
; intact, and it costs about six retries across a 160-token run - each a read
; of the runner-up the classifier already keeps (src/cls4.asm), a rescan only
; past the second reject.
; Sampling was measured too and is worse: it breaks the grammar outright at this
; model size.
; Long enough to cover APP_GEN_STEPS. The decoder searches this for repeated
; 4-grams, so truncating it would quietly let loops back in near the end of a
; run - the exact place they appear.
DEF OUT_MAX EQU 176

DEF NOREPEAT_N EQU 4
DEF NOREPEAT_TRIES EQU 8

; The WRAM bank the classifier's tables live in. v0.5 has no KV cache, so
; every switchable bank is free; 7 is kept for continuity with v0.4, where
; claiming a KV bank by mistake once cost an afternoon.
DEF CLS_TBL_BANK EQU 7

; The WRAM bank of the block tables the output-major sweep reads
; (src/sweep.asm): bank 1, beside the layer-0 probes, which ForwardLayer
; maps at entry anyway - so the forward pass never toggles SVBK mid-layer.
DEF MV_TBL_BANK EQU 1

; The most tokens one reply may run. The newline normally ends a turn well
; before this; the cap is for a reply that never finds one.
DEF CHAT_REPLY_MAX EQU 48
DEF TOK_MAX EQU 64                        ; encoder output, tokens

DEF GEN_STEPS EQU 96

; What the demo generates per exchange. There is no window edge in v0.5 and
; nothing to wrap: cost per token is flat from the first token to the last.
DEF APP_GEN_STEPS EQU 160

; The lab ROM's handshake. It parks in an idle loop advertising LAB_IDLE, the
; harness fills in the prompt and step count, then writes LAB_GO.
DEF LAB_IDLE EQU $A5
DEF LAB_GO   EQU $C3
; Classify wXb as the harness filled it - tables, scan, top two into
; wClsArg / wClsArg2 - and nothing else: the classifier's unit-test entry.
DEF LAB_GO_CLS EQU $C4
; The same, then the no-repeat retry against the history the harness planted
; in wOutTokens / wGenCount, the answer in wBestTok: the retry path's entry,
; which the golden run reaches only once and never past its first reject.
DEF LAB_GO_PICK EQU $C5
; A lab op: RmsNorm alone, on wX as the harness filled it with wRnGain and
; wRnShift as set, into wXb - the kernel by itself for py/tests/test_rmsnorm.py.
DEF LAB_GO_NORM EQU $D2
; Another: ShiftRound24 on the signed 24-bit value at wX+0..2 by the count at
; wX+3, result to wXb+0..2 - the byte peel has no caller on this model's own
; shifts, so py/tests/test_regmath.py exercises every count this way.
DEF LAB_GO_SHIFT EQU $E1

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

; The block kernel in force, chosen by the exporter: one-bit rows run
; Matvec4b (blocks of four), ternary rows Matvec3 (blocks of three). Both
; count wMvIn in blocks; the constants BLOCKS_DIM etc. already match.
MACRO BLOCK_RUN
    IF BINARY
        call Matvec4b_Run
    ELSE
        call Matvec3_Run
    ENDC
ENDM
