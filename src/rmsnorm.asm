; RMSNorm: x_hat = x / rms(x), then an elementwise gain.
;
; The rms ratio is scale-free, so the input exponent cancels and never enters
; the arithmetic. With RSQRT_BITS 14, sqrt(DIM) = 2^3 and a Q11 intermediate,
; the constant part of the closing shift cancels too - only e/2 remains.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "RmsNorm state", WRAM0
wRnSrc::   dw
wRnGain::  dw
wRnDst::   dw
wRnShift:: db
wSS:       ds 4
wRnR:      dw
wRnE:      db

SECTION "RmsNorm code", ROM0

; --- RMSNorm ---------------------------------------------------------------
;
; x_hat = x / rms(x), then an elementwise gain. The rms ratio is scale-free, so
; the input exponent cancels and never enters the arithmetic. With RSQRT_BITS
; 14, sqrt(DIM) = 2^3 and a Q11 intermediate, the constant part of the shift
; cancels exactly and only e/2 remains.
RmsNorm::
    xor a
    ld [wSS + 0], a
    ld [wSS + 1], a
    ld [wSS + 2], a
    ld [wSS + 3], a

    ld a, [wRnSrc + 0]
    ld l, a
    ld a, [wRnSrc + 1]
    ld h, a
    ld b, DIM
; A square is one table read, not a multiply. The quarter-square table already
; in ROM holds f(x) = floor(x*x / 4), so f(2x) = x*x exactly - and |2x| tops out
; at 256, which is precisely the range the table covers. f is even, so the sign
; of x does not matter and only |x| is needed.
;
; This replaces a generic shift-add multiply and a 32-bit add per element with
; an absolute value, a shift and a lookup.
.sumsq
    ld a, [hl+]
    push hl
    bit 7, a
    jr z, :+
    cpl
    inc a                           ; |x|, and |-128| = 128 unsigned
:   ld l, a
    ld h, 0
    add hl, hl                      ; index = 2|x|
    add hl, hl                      ; two bytes per entry
    ld de, tbl_qsq
    add hl, de
    ld a, [hl+]
    ld e, a
    ld d, [hl]                      ; de = x * x

    ld hl, wSS
    ld a, [hl]
    add a, e
    ld [hl+], a
    ld a, [hl]
    adc a, d
    ld [hl+], a
    ld a, [hl]
    adc a, 0
    ld [hl+], a
    ld a, [hl]
    adc a, 0
    ld [hl], a

    pop hl
    dec b
    jr nz, .sumsq

    ld hl, wSS
    call BitLength32
    or a
    jp z, .zero
    bit 0, a
    jr z, :+
    inc a                           ; round up to even so sqrt(2^e) is a shift
:   ld b, a
    srl a
    ld [wRnE], a

    ld a, b
    sub a, 8
    ld hl, wSS
    call Shift32Trunc               ; index = ss >> (e - 8)
    ld a, [wSS + 0]
    ld l, a                         ; index * 2 must be computed 16-bit: the
    ld h, 0                         ; table has 256 entries and dd a, a
    add hl, hl                      ; would drop bit 8 for indices >= 128
    ld de, tbl_rsqrt
    add hl, de
    ld a, [hl+]
    ld [wRnR + 0], a
    ld a, [hl]
    ld [wRnR + 1], a

    ld a, [wRnSrc + 0]
    ld l, a
    ld a, [wRnSrc + 1]
    ld h, a
    ld b, DIM
.scale
    ld a, [hl+]
    push hl
    push bc

    ld [wMulA8], a                  ; x_hat = shr_round(x * r, e/2), as Q11
    ld a, [wRnR + 0]
    ld [wMy + 0], a
    ld a, [wRnR + 1]
    ld [wMy + 1], a
    call MulS8xS16
    ld a, [wRnE]
    call Requant_Shift

    ldh a, [wTmp32 + 0]              ; fold in the gain, land on int8
    ld [wMy + 0], a
    ldh a, [wTmp32 + 1]
    ld [wMy + 1], a
    ld a, [wRnGain + 0]
    ld e, a
    ld a, [wRnGain + 1]
    ld d, a
    ld a, [de]
    ld [wMulA8], a
    inc de
    ld a, e
    ld [wRnGain + 0], a
    ld a, d
    ld [wRnGain + 1], a
    call MulS8xS16
    ld a, [wRnShift]
    call Requant_Shift
    call Requant_Sat8

    ld c, a
    ld a, [wRnDst + 0]
    ld e, a
    ld a, [wRnDst + 1]
    ld d, a
    ld a, c
    ld [de], a
    inc de
    ld a, e
    ld [wRnDst + 0], a
    ld a, d
    ld [wRnDst + 1], a

    pop bc
    pop hl
    dec b
    jp nz, .scale
    ret

.zero
    ld a, [wRnDst + 0]
    ld l, a
    ld a, [wRnDst + 1]
    ld h, a
    ld b, DIM
    xor a
:   ld [hl+], a
    dec b
    jr nz, :-
    ret
