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

; (MulS8xS16_Reg, the signed 8 x 16 shift-and-add multiply that the norm's
; gain step first used, left with the nibble tables and MulS16xU8 below; it
; had no caller and is gone.)

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

; hl = shr_round(e:hl, b) for a result that fits in signed 16 bits, which
; the caller guarantees: with v = e:hl,
;     -2^(b+15) - 2^(b-1) <= v < 2^(b+15) - 2^(b-1)      (b >= 1)
;     -2^15 <= v < 2^15                                  (b = 0)
; i.e. v + 2^(b-1), the value the floor sees, lies in [-2^(b+15), 2^(b+15)).
; NOT |v| < 2^(b+15): v = 2^(b+15) - 1 meets that and rounds to 2^15, which
; is -32768 in hl. The bound is tight both ways (a bit model of this routine
; against Q.shr_round, every b in 0..24, both edges and the first value past
; each). On 24-bit input the lower edge exists only for b <= 7; above that
; every representable v is inside. b in 0..24. Clobbers a, b, e.
;
; Why the norm (src/rmsnorm.asm, the only caller) never reaches an edge:
; its first shift is x * r by p with |x| <= 2^p - 1 (x^2 <= ss < 2^2p) and
; r <= 32641 (tbl_rsqrt over idx 64..255), so |x r| <= (2^p - 1) 32641 <
; 2^(p-1) x 65282, under the bound 2^(p-1) x 65535 with 253 x 2^(p-1) to
; spare; its second is xh * g by s with |xh| <= 32641 (the first result's
; own bound) and g <= 127 (exporter-asserted), so |xh g| <= 4,145,407 <
; 2^22 - 2^6 = 4,194,240, the bound at s = 7, the smallest closing shift
; the exporter allows.
;
; The result has 16 bits, so only the two bytes above the rounding bit are
; wanted, plus the rounding bit itself:
;   b > 8: drop the low byte and shift the 16 bits above it right b - 8
;          times, truncating; the last bit out is the rounding bit (the
;          nested-floor argument ShiftRound24 gives, with the peel first).
;   b = 8: the rounding bit is bit 7 of the low byte; the result is e:h.
;   b < 8: shift the 24 bits left 8 - b times, then as b = 8. The shifted
;          value is v x 2^(8-b), under 2^23 by the bound; if the lower edge
;          takes it past -2^23 it wraps mod 2^24, and the answer is still
;          right: every step from here is arithmetic mod 2^16 on a result
;          that fits, and the rounding bit (bit b-1 of v) is untouched.
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
; against ~135 for the signed 8 x 16 shift-and-add it replaced.
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
