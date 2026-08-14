; ChatGBC - Phase 0
;
; Proves the development loop end to end: boot CGB-only, switch to double speed,
; render text, and measure a block of work whose exact M-cycle cost is known by
; inspection. The test harness checks that measurement against the arithmetic,
; which is what makes every later timing number trustworthy.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; The calibration block below costs exactly 9 M-cycles per iteration
; (nop 1 + nop 1 + dec bc 2 + ld a,b 1 + or c 1 + jr taken 3), less 1 for the
; final untaken jr, plus 3 for the `ld bc` setup. py/test_phase0.py repeats this
; arithmetic and asserts the ROM agrees.
DEF CAL_ITERS EQU 10000

SECTION "VBlank IRQ", ROM0[$40]
    reti

SECTION "Entry", ROM0[$100]
    nop
    jp Main
    ds $150 - @, 0              ; rgbfix fills in the cartridge header

SECTION "Stack", WRAMX[$DF00], BANK[1]
wStack: ds 256

SECTION "Main state", WRAM0
wStatus::    db                 ; STATUS_* flags
wReady::     db                 ; READY_MAGIC once the ROM is finished
wCalCycles:: ds 4               ; hand-countable block, proves the profiler
wMvCycles::  ds 4               ; the matvec kernel
wRowCycles:: ds 4               ; the same sweep without the table build

SECTION "Main", ROM0

Main:
    di
    ld sp, wStack + 256

    ; The CGB boot ROM leaves $11 in A. The header is CGB-only, so this should
    ; be unreachable on real hardware, but a lenient emulator would sail past it.
    cp $11
    jr z, .isCgb
.hang
    jr .hang
.isCgb

    call LcdOff                 ; disabling the LCD outside VBlank is not safe
    call EnterDoubleSpeed

    ld a, 1
    ldh [rSVBK], a              ; WRAM bank 1 holds the stack

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
    call MeasureAddRow          ; leaves junk accumulators, so run it first
    call MeasureMatvec          ; this one's accumulators are what the tests check
    call Report
    call Console_Flush

    ld a, READY_MAGIC           ; last, so the harness never sees a half-drawn screen
    ld [wReady], a
.done
    jr .done


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
    ld b, PAL_SIZE
.loop
    ld a, [hl+]
    ldh [rBCPD], a
    dec b
    jr nz, .loop
    ret

PaletteData:
    dw $7FFF, $56B5, $2529, $0000   ; BGR555: white, light grey, dark grey, black

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

MeasureMatvec:
    call Prof_Start
    call Matvec_Run
    call Prof_Stop
    ld de, wMvCycles
    jr SaveCycles

MeasureAddRow:
    call Matvec_Load
    call Prof_Start
    call Matvec_RunNoLut
    call Prof_Stop
    ld de, wRowCycles
    ; fall through

; Copies the profiler result to de, so successive measurements both survive.
SaveCycles:
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

Report:
    ld hl, sBanner
    call Console_PrintStr

    ld a, [wStatus]
    and STATUS_DOUBLE
    ld hl, sSpeedOn
    jr nz, .speed
    ld hl, sSpeedOff
.speed
    call Console_PrintStr

    ld hl, sCal
    call Console_PrintStr

    ld hl, wCalCycles
    call Print_Dec32At
    ld a, $0A
    call Console_PutChar

    ld hl, sMacs
    call Console_PrintStr
    ld hl, sMv
    call Console_PrintStr
    ld hl, wMvCycles
    jp Print_Dec32At

sBanner:   db "CHATGBC PHASE 1", $0A, $0A, 0
sSpeedOn:  db "CGB OK   2X ON", $0A, $0A, 0
sSpeedOff: db "CGB OK   2X OFF", $0A, $0A, 0
sCal:      db "CAL {d:CAL_ITERS} = ", 0
sMacs:     db "MATVEC {d:MV_M}x{d:MV_N}", $0A, 0
sMv:       db "CYC ", 0

INCLUDE "font.inc"

