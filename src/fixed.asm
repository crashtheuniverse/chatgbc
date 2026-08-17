; Shared fixed-point scratch helpers.
;
; Every kernel funnels through wTmp32: multiplies land in it, Requant_Shift
; rescales it, Requant_Sat8 reads it out as int8. One scratch and one shift
; routine is why there is no second, subtly different rounding rule anywhere
; in the model. wSave32 is the second operand for the 32-bit add/subtract.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Fixed state", WRAM0
wTotal::  ds 4
wSave32:: ds 4

SECTION "Fixed code", ROM0

; --- shared 32-bit helpers --------------------------------------------------

SaveTmp32::
    ld hl, wTmp32
    ld de, wSave32
    ld bc, 4
    jp CopyBytes

; wTmp32 = wSave32 - wTmp32. Loads and inc de leave the flags alone, so the
; borrow chain runs unbroken.
SubTmpFromSave::
    ld hl, wTmp32
    ld de, wSave32
    ld a, [de]
    sub a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    sbc a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    sbc a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    sbc a, [hl]
    ld [hl], a
    ret

AddSaveToTmp::
    ld hl, wTmp32
    ld de, wSave32
    ld a, [de]
    add a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    adc a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    adc a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    adc a, [hl]
    ld [hl], a
    ret

; Truncating arithmetic shift of the 4 bytes at hl by the signed count in a.
; Table indices must truncate, not round, to match the twin.
Shift32Trunc::
    bit 7, a
    jr nz, .left
    or a
    ret z
    ld b, a
.right
    push hl
    inc hl
    inc hl
    inc hl
    ld a, [hl]
    sra a
    ld [hl-], a
    ld a, [hl]
    rra
    ld [hl-], a
    ld a, [hl]
    rra
    ld [hl-], a
    ld a, [hl]
    rra
    ld [hl], a
    pop hl
    dec b
    jr nz, .right
    ret
.left
    cpl
    inc a
    ld b, a
.leftLoop
    push hl
    ld a, [hl]
    add a, a
    ld [hl+], a
    ld a, [hl]
    adc a, a
    ld [hl+], a
    ld a, [hl]
    adc a, a
    ld [hl+], a
    ld a, [hl]
    adc a, a
    ld [hl], a
    pop hl
    dec b
    jr nz, .leftLoop
    ret
