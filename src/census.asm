; Stage census state and the accumulator. See census.inc for the macros and
; forward.asm for where the stages begin and end.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "census.inc"

; Everything here exists only in a census build. The shipping ROM must stay
; byte-identical: even twenty bytes of ROM0 shift every section after them.
IF DEF(CENSUS)

; Bank 1, like the layer-0 debug snapshots: WRAM0 is full, and ForwardLayer
; already selects bank 1 at entry. The accumulator selects it again itself,
; because the classifier leaves its own bank mapped.
SECTION "Stage census", WRAMX, BANK[1]
wStage:: ds CENSUS_STAGES * 4

SECTION "Stage census code", ROM0

; [de] += wProfCycles, 32-bit. Called after Prof_Stop has computed the cycles.
Census_Accum::
    ld a, 1
    ldh [rSVBK], a
    ld hl, wProfCycles
    ld b, 4
    or a                            ; clear carry for the chain
.byte
    ld a, [de]
    adc a, [hl]
    ld [de], a
    inc de
    inc hl
    dec b                           ; dec leaves carry alone
    jr nz, .byte
    ret

ENDC
