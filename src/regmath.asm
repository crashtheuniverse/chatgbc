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
; the value untouched, as Requant_Shift does. Exact for every b in 0..24.
; Clobbers a, b.
;
; A shift of eight is a byte move, and Requant_Shift's rule carries over:
; while more than eight bits remain, a whole byte may leave by truncation,
; because every bit it holds sits below the rounding bit -
; floor((floor(v / 256) + 2^(b-9)) / 2^(b-8)) = floor((v + 2^(b-1)) / 2^b)
; by nested floors. The last bit still leaves singly, so the carry it strands
; is the rounding bit the tail reads. The test is `> 8`, not `>= 8`, for
; that reason. 15 cycles a byte peeled, against 80 of bit steps.
ShiftRound24::
    ld a, b
    or a
    ret z
.bytes
    cp 9
    jr c, .bit
    ld l, h
    ld h, e
    ld a, e
    add a, a
    sbc a, a                        ; $FF if negative, else $00
    ld e, a
    ld a, b
    sub a, 8
    ld b, a
    jr .bytes
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

; hl = shr_round(e:hl, b) for a result that fits in signed 16 bits - i.e.
; |e:hl| < 2^(b+15), which the caller guarantees. b in 0..24. Clobbers a, b, e.
;
; The result has 16 bits, so only the two bytes above the rounding bit are
; wanted, plus the rounding bit itself:
;   b > 8: drop the low byte and shift the 16 bits above it right b - 8
;          times, truncating; the last bit out is the rounding bit (the
;          nested-floor argument ShiftRound24 gives, with the peel first).
;   b = 8: the rounding bit is bit 7 of the low byte; the result is e:h.
;   b < 8: shift the 24 bits left 8 - b times - no overflow, since the
;          bound above puts the shifted value under 2^23 - then as b = 8.
; Then add the carry into the 16-bit result.
;
; Cycles with the call: b = 6: 50, 7: 42, 8: 32, 9: 36, 10: 44, 11: 52,
; 12: 60, 13: 68 - against 31 + 10 b for ShiftRound24 before its peel
; (13: 161), 66 + 8 (b - 8) - 1 after it.
ShrRound24to16::
    ld a, b
    sub a, 8
    jr c, .left
    jr nz, .peel
    ld a, l                         ; b = 8: carry = bit 7 of the dropped byte
    add a, a
    ld l, h
    ld h, e
    jr .round
.peel
    ld b, a                         ; b - 8 bits remain, on 16 bits
    ld l, h
    ld h, e
.rbit
    sra h
    rr l
    dec b                           ; leaves carry alone
    jr nz, .rbit
.round
    ld a, l                         ; carry = the rounding bit
    adc a, 0
    ld l, a
    ld a, h
    adc a, 0
    ld h, a
    ret
.left
    cpl
    inc a                           ; 8 - b
    ld b, a
.lbit
    add hl, hl
    rl e
    dec b
    jr nz, .lbit
    ld a, l                         ; now as b = 8
    add a, a
    ld l, h
    ld h, e
    jr .round

; bc (signed 16-bit) * a (unsigned, 0..127) -> e:hl, signed 24-bit.
; Clobbers a, d. bc is preserved.
;
; The multiplier is seven bits, so seven shift-and-add iterations, MSB first,
; with bc read as the unsigned value u = xh + 2^16 [xh < 0]. That over-counts
; by g * 2^16 when xh is negative, and since the accumulator is shifted left
; seven times, starting it at -g * 2^9 = -(2g) * 2^8 puts exactly -g * 2^16
; into the sum, modulo 2^24. |xh * g| < 2^23, so the 24-bit residue is the
; signed product. This replaces an abs of the multiplicand and a 24-bit
; negate of the result with a 16-bit negate of one byte.
;
; ~103 cycles with the call at a typical gain (72 + 4.5 per set bit + setup),
; against ~135 for MulS8xS16_Reg.
MulS16xU8::
    ld d, a
    ld l, 0
    bit 7, b
    jr z, .pos
    add a, a                        ; 2g, no carry: g <= 127
    ld h, a
    xor a
    sub a, h
    ld h, a                         ; h = -(2g) mod 256
    sbc a, a                        ; $FF iff 2g was nonzero: the sign byte
    ld e, a                         ; e:hl = -(2g) << 8
    jr .go
.pos
    ld h, l
    ld e, l                         ; e:hl = 0
.go
    sla d                           ; bit 7 is clear by contract: skip it
REPT 7
    add hl, hl
    rl e
    sla d
    jr nc, :+
    add hl, bc
    jr nc, :+
    inc e
:
ENDR
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
