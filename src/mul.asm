; Multiplication helpers for everything outside the matvec inner loop.
;
; The SM83 has no multiply, so one shift-and-add core does all the work and the
; wider forms are built from it. All results land in wTmp32, the same scratch
; Requant_Shift and Requant_Sat8 operate on, so a caller can multiply, rescale
; and saturate without moving anything.
;
; Cost is roughly 130 cycles for the 8x16 form. That is deliberate: these run
; a few thousand times per token, against ~300,000 for the matvec, so clarity
; wins here and the optimization effort belongs in matvec.asm.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Mul state", WRAM0
wMulA8:: db                         ; 8-bit operand
wMulB8:: db                         ; second 8-bit operand, used by Mul8x8
wMx::    dw                         ; 16-bit operand (MulU16 only)
wMy::    dw                         ; 16-bit operand
wMulSv:  ds 4                       ; partial product held across MulU16

SECTION "Mul code", ROM0

; a = unsigned 8-bit, wMy = unsigned 16-bit  ->  wTmp32 (unsigned, 24 bits used)
;
; Shifts the accumulator up rather than the multiplicand, so the multiplicand
; stays in bc and never needs to widen past 16 bits.
MulU8xU16::
    ld d, a                         ; multiplier, consumed MSB first
    ld a, [wMy + 0]
    ld c, a
    ld a, [wMy + 1]
    ld b, a                         ; bc = multiplicand
    ld hl, 0                        ; hl = accumulator low 16
    ld e, 0                         ; e  = accumulator bits 16..23
REPT 8
    add hl, hl
    rl e
    sla d
    jr nc, :+
    add hl, bc
    ld a, e
    adc a, 0
    ld e, a
:
ENDR
    ld a, l
    ldh [wTmp32 + 0], a
    ld a, h
    ldh [wTmp32 + 1], a
    ld a, e
    ldh [wTmp32 + 2], a
    xor a
    ldh [wTmp32 + 3], a
    ret

; Negates wTmp32 in place.
; `ld a, 0` does not disturb flags, so the borrow chain survives it.
Tmp32_Negate::
    xor a
    ld hl, wTmp32
    sub a, [hl]
    ld [hl+], a
    ld a, 0
    sbc a, [hl]
    ld [hl+], a
    ld a, 0
    sbc a, [hl]
    ld [hl+], a
    ld a, 0
    sbc a, [hl]
    ld [hl], a
    ret

; wMulA8 (signed 8-bit) * wMy (signed 16-bit)  ->  wTmp32 (signed)
MulS8xS16::
    ld c, 0                         ; counts negative operands
    ld a, [wMulA8]
    bit 7, a
    jr z, .aPos
    cpl
    inc a
    inc c
.aPos
    ld b, a                         ; |A|

    ld a, [wMy + 1]
    bit 7, a
    jr z, .bPos
    ld a, [wMy + 0]                 ; negate the 16-bit operand
    cpl
    ld e, a
    ld a, [wMy + 1]
    cpl
    ld d, a
    inc e
    jr nz, :+
    inc d
:   ld a, e
    ld [wMy + 0], a
    ld a, d
    ld [wMy + 1], a
    inc c
.bPos
    push bc
    ld a, b
    call MulU8xU16
    pop bc
    bit 0, c                        ; exactly one negative operand
    ret z
    jp Tmp32_Negate

; Sets wMy to the sign-extension of a.
SetMyFromS8::
    ld [wMy + 0], a
    add a, a
    sbc a, a
    ld [wMy + 1], a
    ret

; wMx (unsigned 16) * wMy (unsigned 16) -> wTmp32 (unsigned 32)
;
; Split into two 8x16 products: X*Y = (Xhi*Y << 8) + Xlo*Y. Cheaper than a
; 16-iteration loop and reuses the core above.
MulU16::
    ld a, [wMx + 0]
    call MulU8xU16
    ld hl, wTmp32                   ; stash the low partial product
    ld de, wMulSv
    ld bc, 4
    call CopyBytes

    ld a, [wMx + 1]
    call MulU8xU16
    ldh a, [wTmp32 + 2]              ; << 8, as a byte move
    ldh [wTmp32 + 3], a
    ldh a, [wTmp32 + 1]
    ldh [wTmp32 + 2], a
    ldh a, [wTmp32 + 0]
    ldh [wTmp32 + 1], a
    xor a
    ldh [wTmp32 + 0], a

    ld hl, wMulSv                   ; add the stashed partial product back
    ldh a, [wTmp32 + 0]
    add a, [hl]
    ldh [wTmp32 + 0], a
    inc hl
    ldh a, [wTmp32 + 1]
    adc a, [hl]
    ldh [wTmp32 + 1], a
    inc hl
    ldh a, [wTmp32 + 2]
    adc a, [hl]
    ldh [wTmp32 + 2], a
    inc hl
    ldh a, [wTmp32 + 3]
    adc a, [hl]
    ldh [wTmp32 + 3], a
    ret

; Adds wTmp32 into the 4-byte little-endian value at hl.
Tmp32_AddTo::
    ld de, wTmp32
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

; Bit length of the 4-byte value at hl, returned in a. Zero gives zero.
BitLength32::
    ld b, 24
    inc hl
    inc hl
    inc hl
    ld a, [hl-]
    or a
    jr nz, .scan
    ld b, 16
    ld a, [hl-]
    or a
    jr nz, .scan
    ld b, 8
    ld a, [hl-]
    or a
    jr nz, .scan
    ld b, 0
    ld a, [hl]
    or a
    ret z
.scan
    ld c, 0
.loop
    inc c
    srl a
    jr nz, .loop
    ld a, b
    add a, c
    ret
