; Register arithmetic: multiply, round-shift and saturate without the 32-bit
; scratch.
;
; The generic path - operands stored to WRAM, product stored to the HRAM
; scratch, shifted there, read back, saturated back out - costs several times
; its arithmetic. These take operands in registers, leave a 24-bit result in
; e:hl, shift and saturate it there, and store nothing until the caller does.
; Every rule is the scratch path's: exact product, round-half-up on the last
; bit shifted out, saturation to [-127, 127] with -128 mapped to -127.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"

SECTION "Register math", ROM0

; a (signed 8-bit) * bc (signed 16-bit) -> e:hl, signed 24-bit.
; The loop is MulS8xS16's; only the operand and result traffic is gone.
MulS8xS16_Reg::
    ld d, a
    xor b                           ; sign of the product = signA xor signB
    push af
    ld a, d
    bit 7, a
    jr z, :+
    cpl
    inc a
:   ld d, a                         ; |A|, the multiplier
    bit 7, b
    jr z, :+
    ld a, c
    cpl
    ld c, a
    ld a, b
    cpl
    ld b, a
    inc bc                          ; |B|, the multiplicand
:
    ld hl, 0
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
    ret z
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
    ret nz
    inc e
    ret

; e:hl >>= b, arithmetic, round-half-up on the last bit out. b = 0 leaves
; the value untouched, as Requant_Shift does. Clobbers a, b.
ShiftRound24::
    ld a, b
    or a
    ret z
.bit
    sra e
    rr h
    rr l
    dec b                           ; leaves carry alone
    jr nz, .bit
    ld a, l                         ; carry = the last bit shifted out
    adc a, 0
    ld l, a
    ld a, h
    adc a, 0
    ld h, a
    ld a, e
    adc a, 0
    ld e, a
    ret

; a = sat8(e:hl): [-127, 127], with -128 mapped to -127. Clobbers nothing else.
Sat8_24::
    ld a, l
    add a, a
    sbc a, a                        ; the sign l would extend to
    cp h
    jr nz, .clamp
    cp e
    jr nz, .clamp
    ld a, l
    cp $80
    ret nz
    ld a, -127
    ret
.clamp
    bit 7, e
    ld a, 127
    ret z
    ld a, -127
    ret
