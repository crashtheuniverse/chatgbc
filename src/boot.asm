; Bringing the machine up, and the pieces both ROMs share.
;
; Two entry points build against this. src/app/main.asm is the demo - keyboard,
; frame, status bar. src/lab/main.asm is the bare one the test suite drives,
; which exists because the demo path costs wall-clock the loop cannot spare.
; Whichever is linked provides `Run`, which this jumps to when the machine is
; up. It has to be a jump, not a call: bring-up moves the stack pointer, so a
; return address pushed beforehand is popped off a different stack afterwards.
;
; Measure still times a block whose exact M-cycle cost is known by inspection,
; and py/tests/test_phase0.py checks the ROM's answer against that arithmetic.
; Nothing depends on it any more, but it is the calibration every other timing
; number in the project rests on, so it stays.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; The calibration block below costs exactly 9 M-cycles per iteration
; (nop 1 + nop 1 + dec bc 2 + ld a,b 1 + or c 1 + jr taken 3), less 1 for the
; final untaken jr, plus 3 for the `ld bc` setup. py/test_phase0.py repeats this
; arithmetic and asserts the ROM agrees.
DEF CAL_ITERS EQU 10000

SECTION "VBlank IRQ", ROM0[$40]
    jp Type_ISR                 ; the teletype; a few cycles when it is off

SECTION "Entry", ROM0[$100]
    nop
    jp Boot
    ds $150 - @, 0              ; rgbfix fills in the cartridge header

; The stack must live in WRAM0. The KV cache switches SVBK per layer, and a
; stack in a banked region would vanish out from under every call.
SECTION "Stack", WRAM0
wStack: ds 192

SECTION "Main state", WRAM0
wStatus::    db                 ; STATUS_* flags
wReady::     db                 ; READY_MAGIC once the ROM is finished
wCalCycles:: ds 4               ; hand-countable block, proves the profiler
wMvCycles::  ds 4               ; the matvec kernel
wRowCycles:: ds 4               ; the same sweep without the table build

SECTION "Boot", ROM0

Boot::
    di

    ; The CGB boot ROM leaves $11 in A. The header is CGB-only, so this should
    ; be unreachable on real hardware, but a lenient emulator would sail past it.
    cp $11
    jr z, .isCgb
.hang
    jr .hang
.isCgb
    call ClearWram              ; before sp is set, since the stack lives in WRAM0
    ld sp, wStack + 192

    call LcdOff                 ; disabling the LCD outside VBlank is not safe
    call EnterDoubleSpeed

    ld a, 1
    ldh [rSVBK], a              ; any nonzero bank; layers reselect per KV cache

    ; VRAM bank 1 holds BG attributes and comes up dirty; zeroing it selects
    ; palette 0, tile bank 0, no flip for every cell.
    ld a, 1
    ldh [rVBK], a
    call ClearVram
    xor a
    ldh [rVBK], a
    call ClearVram

    call LoadFont
    call SetPalette
    call Console_Clear
    call Console_FlushNow

    xor a
    ldh [rSCX], a
    ldh [rSCY], a
    ld a, LCDC_ON | LCDC_BG_ON | LCDC_BLOCK01 | LCDC_BG_9800
    ldh [rLCDC], a

    call RecordStatus
    call Measure
    call Prof_Start             ; time the gate row while checking it: one
    call GateSelftest           ; Gate_Update over 64 dims, plus the copies
    call Prof_Stop
    ld hl, wProfCycles
    ld de, wGateCycles
    ld b, 4
    call CopyN
    jp Run                      ; whichever entry point was linked



; --- Boot helpers -----------------------------------------------------------

LcdOff:
    ldh a, [rLCDC]
    bit B_LCDC_ENABLE, a
    ret z
.wait
    ldh a, [rLY]
    cp 144
    jr nz, .wait                ; stop at the first line of VBlank
    xor a
    ldh [rLCDC], a
    ret

EnterDoubleSpeed:
    ldh a, [rKEY1]
    bit B_SPD_DOUBLE, a
    ret nz
    ld a, $30
    ldh [rJOYP], a              ; deselect both key rows before `stop`
    xor a
    ldh [rIE], a
    ldh [rIF], a
    ld a, SPD_PREPARE
    ldh [rKEY1], a
    stop
    ret

; Zeroes every WRAM bank. Real hardware powers up with garbage in RAM, and an
; emulator that happens to start it at zero will hide any dependency on that -
; which is exactly how a stale accumulator flag survived testing under PyBoy and
; produced nonsense on SameBoy.
ClearWram:
    ld a, 7                     ; banks 7..1 at $D000, then WRAM0
.bank
    ldh [rSVBK], a
    push af
    ld hl, $D000
    ld bc, $1000
    call ZeroBlock
    pop af
    dec a
    jr nz, .bank
    ld a, 1
    ldh [rSVBK], a
    ld hl, $C000
    ld bc, $1000
    ; fall through

ZeroBlock:
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, ZeroBlock
    ret

ClearVram:
    ld hl, $8000
    ld bc, $2000
.loop
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .loop
    ret

; Expands the 1bpp font into 2bpp tiles at $8000, writing each row to both
; bitplanes so lit pixels land on colour 3 and the rest on colour 0.
LoadFont:
    ld hl, FontData
    ld de, TILEBLOCK0
    ld bc, FONT_GLYPHS * 8
.loop
    ld a, [hl+]
    ld [de], a
    inc de
    ld [de], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, .loop
    ret

SetPalette:
    ld a, BGPI_AUTOINC          ; start at index 0 and step after each write
    ldh [rBCPS], a
    ld hl, PaletteData
    ld b, PAL_SIZE * 2          ; palette 0 normal, palette 1 inverted
.loop
    ld a, [hl+]
    ldh [rBCPD], a
    dec b
    jr nz, .loop
    ret

PaletteData:                        ; BGR555, parchment and ink
    dw $5BBF, $3ADA, $21B1, $0CA8   ; cream, tan, umber, dark brown
    dw $0CA8, $21B1, $3ADA, $5BBF   ; the same inverted, for the keyboard cursor

RecordStatus:
    ld b, STATUS_CGB
    ldh a, [rKEY1]
    bit B_SPD_DOUBLE, a
    jr z, .single
    set 1, b                    ; STATUS_DOUBLE
.single
    ld a, b
    ld [wStatus], a
    ret


; --- The measurement itself -------------------------------------------------

Measure:
    call Prof_Start
    ld bc, CAL_ITERS
.loop
    nop
    nop
    dec bc
    ld a, b
    or c
    jr nz, .loop
    call Prof_Stop
    ld de, wCalCycles
    jr SaveCycles

MeasureSelftest::
    call Selftest_Setup
    call Prof_Start
    call Selftest_Run
    call Prof_Stop
    ld de, wMvCycles
    ; fall through

; Copies the profiler result to de, so successive measurements both survive.
SaveCycles::
    ld hl, wProfCycles
    ld b, 4
.loop
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .loop
    ret


; --- Display ----------------------------------------------------------------

ReportTiming::
    ld a, $0A
    call Console_PutChar
    ld hl, sMv
    call Console_PrintStr
    ld hl, wTokCycles
    jp Print_Dec32At

sMv:       db "CYC/TOK ", 0

INCLUDE "font.inc"

; Runs Gate_Update on the exporter's known-answer vectors (layer 0's
; sigmoid, the vectors in layer 0's slices), so the recurrent kernel is
; judged in isolation before the forward pass ever runs. The harness
; compares wGateOut against test_gate_out; Generate re-zeroes wH before any
; token runs, so the state the test leaves behind is never seen.
GateSelftest::
    ld hl, test_gate_zl
    ld de, wZl
    ld bc, DIM
    call CopyBytes
    ld hl, test_gate_ht
    ld de, wHt
    ld bc, DIM
    call CopyBytes
    ld hl, test_gate_h
    ld de, wH
    ld bc, DIM
    call CopyBytes

    xor a
    ld [wLayer], a
    call Gate_Update

    ld hl, wH
    ld de, wGateOut
    ld bc, DIM
    jp CopyBytes

SECTION "Gate selftest state", WRAM0
wGateCycles:: ds 4
