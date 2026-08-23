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
    ; The multiply itself is the eight-iteration loop below - about 92 cycles.
    ; The version this replaces spent another ~117 on top of it: it negated the
    ; 16-bit operand into registers, wrote it back to wMy, and then read it
    ; straight out again because the loop lived behind a separate entry point
    ; that took its operand from memory. Then it negated the 32-bit *result*, in
    ; memory, through another call.
    ;
    ; Now the operand stays in bc, the sign rides on the stack, and a negative
    ; result is negated in registers before it is ever stored.

    ld a, [wMulA8]                  ; sign of the product = signA xor signB
    ld b, a
    ld a, [wMy + 1]
    xor b
    push af

    ld a, b                         ; |A| -> d, the multiplier
    bit 7, a
    jr z, :+
    cpl
    inc a
:   ld d, a

    ld a, [wMy + 0]                 ; |B| -> bc, the multiplicand
    ld c, a
    ld a, [wMy + 1]
    ld b, a
    bit 7, b
    jr z, :+
    ld a, c
    cpl
    ld c, a
    ld a, b
    cpl
    ld b, a
    inc bc
:
    ld hl, 0                        ; hl = product low 16, e = bits 16..23
    ld e, 0
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

    pop af
    bit 7, a
    jr z, .store

    ld a, l                         ; negate the 24-bit result in place
    cpl
    ld l, a
    ld a, h
    cpl
    ld h, a
    ld a, e
    cpl
    ld e, a
    inc hl
    ld a, h
    or l
    jr nz, .store
    inc e

.store
    ld a, l
    ldh [wTmp32 + 0], a
    ld a, h
    ldh [wTmp32 + 1], a
    ld a, e
    ldh [wTmp32 + 2], a
    add a, a                        ; |A*B| <= 2^22, so bit 23 is the sign
    sbc a, a
    ldh [wTmp32 + 3], a
    ret

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

; --- quarter-square multiply ------------------------------------------------
;
; a = first operand, b = second, both signed 8-bit.
; Returns the exact signed 16-bit product in hl. Clobbers a, bc, de, hl.
;
;   a*b == f(a+b) - f(a-b),  f(x) = floor(x*x / 4)
;
; Exact, not approximate: a+b and a-b always share parity, so either both floors
; are exact or both discard the same quarter. f is even, so tbl_qsq stores only
; |x| for x in 0..256 - 514 bytes, which is what lets it live in ROM0.
;
; This exists for attention, where both operands are runtime values and the
; matvec's precomputed product tables cannot help.
Mul_S8xS8::
    ld e, a
    add a, a
    sbc a, a
    ld d, a                         ; de = a, sign-extended

    ld c, b
    ld a, b
    add a, a
    sbc a, a
    ld b, a                         ; bc = b, sign-extended

    ld h, d
    ld l, e
    add hl, bc                      ; a + b
    call QuarterSquare
    push hl

    ld a, c                         ; -b, so the second term is another add
    cpl
    ld l, a
    ld a, b
    cpl
    ld h, a
    inc hl
    add hl, de                      ; a - b
    call QuarterSquare

    ld d, h
    ld e, l
    pop hl
    ld a, l
    sub e
    ld l, a
    ld a, h
    sbc d
    ld h, a
    ret

; hl = a signed value in [-256, 256]  ->  hl = tbl_qsq[|hl|].
QuarterSquare:
    bit 7, h
    jr z, .abs
    ld a, l
    cpl
    ld l, a
    ld a, h
    cpl
    ld h, a
    inc hl
.abs
    ; The base is folded in through a rather than `ld de` + `add hl, de`, so this
    ; leaves de alone. Mul_S8xS8 keeps its first operand there across both
    ; lookups, and clobbering it cost a whole afternoon.
    add hl, hl                      ; two bytes per entry
    ld a, l
    add a, LOW(tbl_qsq)
    ld l, a
    ld a, h
    adc a, HIGH(tbl_qsq)
    ld h, a
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ret
