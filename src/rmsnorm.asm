; RMSNorm: x_hat = x / rms(x), then an elementwise gain. wX -> wXb.
;
; The rms ratio is scale-free, so the input exponent cancels and never enters
; the arithmetic. With RSQRT_BITS 14, sqrt(DIM) = 2^3 and a Q11 intermediate,
; the constant part of the closing shift cancels too - only e/2 remains.
;
; The twin (py/quant.py rmsnorm) is the definition, integer for integer:
;   ss  = sum x^2                       (x int8, so ss < 2^20 at DIM 64)
;   e   = bitlen(ss) rounded up to even, p = e/2
;   idx = ss >> (e - 8)                 (64..255), r = tbl_rsqrt[idx]
;   xh  = shr_round(x * r, p)           (Q11, |xh| < 2^15)
;   y   = sat8(shr_round(xh * g, s))    (s = out_exp + 11 - wexp, per norm)
;
; What this file does differently from the scratch-based version it replaces,
; and why each step is still the same integer:
;
; 1. The sum of squares lives in registers: 16 bits in bc, the third byte in
;    HRAM, no fourth byte (ss < 2^20). x^2 is one read of tbl_qsq[2|x|] as
;    before; the table is page-aligned now so the index is arithmetic on
;    bytes. 33 cycles an element (below), where the WRAM accumulate cost 61.
;
; 2. idx and p come from the top nonzero byte of ss and its bit length
;    rounded up to even: idx is the 16-bit window (top byte : next byte)
;    shifted right by that length, which is a byte select and at most a
;    nibble swap - ~40 cycles a norm where Shift32Trunc took ~480. Exact
;    because ss >> (e - 8) only ever sees the top two bytes: e - 8 >= 8 * pos,
;    and the bits below cannot carry into a floor.
;
; 3. x * r is not a multiply. r is one constant for all 64 elements, so the
;    norm builds two 16-entry tables once - TL[n] = n * r and
;    TH[m] = (16m - 256 * [m >= 8]) * r, the signed high nibble - and
;    x * r = TH[x >> 4] + TL[x & 15] is two reads and a 24-bit add: 44 cycles
;    against ~135 for the shift-and-add multiply. The tables are 32 entries
;    of 3 bytes = exactly the matvec's 96-byte HRAM product region, which is
;    dead between matvecs (every matvec rebuilds it). Building them costs
;    ~950 cycles a norm, well under what they save over 64 elements.
;
; 4. Both rounding shifts produce a 16-bit result, and ShrRound24to16 (in
;    regmath.asm) exploits that: whole bytes below the rounding bit are
;    truncated, or the value is shifted left by 8 - b when b < 8, and one
;    carry-rounded byte take finishes. |x| < 2^p (x^2 <= ss < 2^2p) bounds
;    x * r under 2^(p+15), and s >= 7 (asserted at export) bounds xh * g
;    under 2^(s+15), so both fit the routine's contract. 32 cycles at p = 8,
;    68 at s = 13, where ShiftRound24 spent 111 and 161.
;
; 5. xh * g uses the gain as an unsigned 7-bit multiplier (the exporter
;    asserts every gain is in 0..127): seven iterations, and the sign of xh
;    folded into the accumulator's starting value instead of an abs and a
;    24-bit negate. ~103 cycles against ~135.
;
; 6. The per-element plumbing keeps the walking index and the constants in
;    HRAM and reaches wX, wXb and the gain row through one low address byte
;    each: the buffers are asserted not to cross a page and the exporter
;    64-aligns the gain rows. 55 cycles an element, where the old loop
;    re-read five WRAM pointers and pushed and popped twice for ~114.
;
; Per element, counted from the listing: plumbing 54 + x*r 44 + first shift
; 32 (p = 8; 50 at p = 6, 44 at p = 10) + xh*g ~103 + second shift 68
; (s = 13; 52 at s = 11) + sat8 12 = ~313. Per norm: 64 x 313 + sum of
; squares ~2,150 + tables ~950 + idx/r ~60 = ~23,200, seven norms ~162K a
; token; the census measures 162,808 where it read 326,024 before.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "RmsNorm state", WRAM0
wRnGain::  dw                       ; this norm's gain row: DIM int8 in ROM0,
                                    ; inside one 256-byte page (exporter-aligned)
wRnShift:: db                       ; s = out_exp + 11 - wexp, 7..24

SECTION "RmsNorm HRAM", HRAM
UNION
hRnIdx:  db                         ; low address byte of the element in hand
hRnP:    db                         ; e / 2, the first shift
NEXTU                               ; the same two bytes, before the walk:
hRnT2:   db                         ; the table step's third byte
hRnSS2:  db                         ; the third byte of ss, until p replaces it
ENDU
hRnS:    db                         ; the gain shift
hRnGain: db                         ; low address byte of the gain in hand

; The two nibble tables in the matvec's HRAM product region: 3 bytes an
; entry, little-endian, TL at +0 and TH at +48 - 96 bytes, exactly hLut.
DEF hRnTbl EQU $FF00 + HLUT_BASE
DEF hRnLo  EQU hRnTbl               ; TL[n] = n * r,               n = x & 15
DEF hRnHi  EQU hRnTbl + 48          ; TH[m] = (16m - 256[m>=8]) * r, m = x >> 4
ASSERT CB_LEVELS * 3 * 2 >= 96, "the norm's tables need the matvec's 96 HRAM bytes"

; The walk touches wX, wXb and the gain row through one low byte each. Both
; loops end on the low byte of the address one past wX, LOW(wX + DIM): the
; same byte as LOW(wX) + DIM except when wX ends its page, where that sum is
; 256 and LOW() of the address is the 0 the incremented byte actually holds.
ASSERT wXb == wX + DIM, "RmsNorm writes wXb at wX's offset plus DIM"
ASSERT LOW(wX) + DIM <= 256, "wX must not cross a 256-byte page"
ASSERT LOW(wXb) + DIM <= 256, "wXb must not cross a 256-byte page"
ASSERT DIM % 4 == 0, "RmsNorm's sum of squares takes four elements a turn"
ASSERT LOW(tbl_qsq) == 0, "tbl_qsq must be page-aligned (export5 aligns it)"
ASSERT LOW(rms_att) % DIM == 0, "rms_att rows must not cross a page (export5 aligns them)"
ASSERT LOW(rms_ffn) % DIM == 0, "rms_ffn rows must not cross a page (export5 aligns them)"
ASSERT LOW(rms_final) % DIM == 0, "rms_final must not cross a page (export5 aligns it)"

SECTION "RmsNorm code", ROM0

; Adds the step in b:c (third byte hRnT2) to the entry at hl and writes the
; sum to de, entry after entry, until the write pointer's low byte reaches
; \1. 27 cycles an entry. The read pointer trails the write pointer by one
; entry, so each entry is the previous one plus the step.
MACRO RN_FILL
.fill\@
    ld a, [hl+]
    add a, c
    ld [de], a
    inc e
    ld a, [hl+]
    adc a, b
    ld [de], a
    inc e
    ldh a, [hRnT2]                  ; ld leaves the carry alone
    adc a, [hl]
    inc l
    ld [de], a
    inc e
    ld a, e
    cp \1
    jr nz, .fill\@
ENDM

; --- RMSNorm ---------------------------------------------------------------
;
; wX -> wXb with the gain row at wRnGain and the closing shift wRnShift.
; Clobbers everything, including the matvec's HRAM product region.
RmsNorm::
    ; --- sum of squares, 20 bits in hRnSS2:b:c ---
    ;
    ; A square is one table read, not a multiply: tbl_qsq holds floor(k*k/4),
    ; so entry 2|x| is x*x exactly, and |x| <= 128 keeps the index inside its
    ; 257 entries. Per element: ld a,[de] 2, inc e 1, abs ~6, index 11 (the
    ; table is page-aligned, so 4|x| splits into a byte and a page carry),
    ; two reads and adds 8, carry test 2 (+7 on a carry, at most 15 a norm),
    ; and 7 of loop control shared by four = ~33.
    xor a
    ldh [hRnSS2], a
    ld b, a
    ld c, a
    ld de, wX
.sumsq
REPT 4
    ld a, [de]
    inc e
    bit 7, a
    jr z, :+
    cpl
    inc a                           ; |x|, and |-128| = 128 unsigned
:   ld l, a
    ld h, 0
    add hl, hl
    add hl, hl                      ; hl = 4|x|, the byte offset of entry 2|x|
    ld a, h
    add a, HIGH(tbl_qsq)
    ld h, a
    ld a, [hl+]
    add a, c
    ld c, a
    ld a, [hl]
    adc a, b
    ld b, a
    jr nc, :+
    ldh a, [hRnSS2]
    inc a
    ldh [hRnSS2], a
:
ENDR
    ld a, e
    cp LOW(wX + DIM)                ; e after the last element, mod 256
    jp nz, .sumsq                   ; four bodies put the top out of jr's reach

    ; --- e, p and idx from the top byte of ss ---
    ;
    ; With the top nonzero byte t at position pos and the byte below it n,
    ; bitlen(ss) = 8 pos + bitlen(t). Rounding bitlen(t) up to even gives
    ; et in {2,4,6,8} by t's range, e = 8 pos + et, p = 4 pos + et/2, and
    ; idx = ss >> (e - 8) = (t:n) >> et - the bytes below n sit under the
    ; floor. At pos 0 n is zero, which is the twin's ss << (8 - e).
    ldh a, [hRnSS2]
    or a
    jr nz, .top2
    ld a, b
    or a
    jr nz, .top1
    ld a, c
    or a
    jp z, .zero
    ld b, c                         ; window = c:0
    ld c, 0
    ld d, 0                         ; p = 0 + et/2
    jr .window
.top1                               ; window = b:c
    ld d, 4
    jr .window
.top2                               ; window = ss2:b
    ld c, b
    ld b, a
    ld d, 8
.window                             ; b = t (nonzero), c = n, d = 4 pos
    ld a, b
    cp 64
    jr nc, .et8
    cp 16
    jr nc, .et6
    cp 4
    jr nc, .et4
    srl b                           ; t in 1..3: idx = (t:n) >> 2
    rr c
    srl b
    rr c
    ld a, c
    inc d
    jr .idx
.et4                                ; t in 4..15: idx = (t << 4) | (n >> 4)
    swap b
    ld a, c
    swap a
    and $0F
    or b
    inc d
    inc d
    jr .idx
.et6                                ; t in 16..63: idx = (t:n) >> 6
    sla c
    rl b
    sla c
    rl b
    ld a, b
    inc d
    inc d
    inc d
    jr .idx
.et8                                ; t in 64..255: idx = t
    inc d
    inc d
    inc d
    inc d
.idx                                ; a = idx in 64..255, d = p in 1..11
    ld l, a
    ld a, d
    ldh [hRnP], a
    ld h, 0
    add hl, hl                      ; two bytes per entry; idx >= 128 needs
    ld de, tbl_rsqrt                ; the 16-bit form
    add hl, de
    ld a, [hl+]
    ld c, a
    ld b, [hl]                      ; bc = r, 16400..32641

    ; --- the nibble tables of r ---
    ;
    ; TL[0] = 0, then 15 steps of r (third byte 0). TH[0] = 0 and seven
    ; steps of 16r for the non-negative high nibbles; TH[8] = -128 r and
    ; seven more steps of 16r for the negative ones. 16r reaches 2^19, so
    ; its third byte rides in hRnT2 and RN_FILL adds it with the carry.
    ld hl, hRnLo
    xor a
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a                     ; TL[0] = 0
    ldh [hRnT2], a
    ld de, hRnLo + 3
    ld hl, hRnLo
    RN_FILL LOW(hRnLo + 48)         ; TL[1..15]

    ld hl, hRnHi
    xor a
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a                     ; TH[0] = 0

    ; TH[8] = -(r << 7): negate r to 16 bits, shift it right once keeping the
    ; bit that falls out, and the bytes of (-r) << 7 are (bit << 7, lo, hi).
    xor a
    sub c
    ld l, a
    ld a, 0
    sbc a, b
    ld h, a                         ; hl = -r
    sra h
    rr l                            ; hl = -r >> 1, carry = bit 0 of -r
    ld a, 0
    rra                             ; a = that bit << 7
    ldh [hRnHi + 24 + 0], a
    ld a, l
    ldh [hRnHi + 24 + 1], a
    ld a, h
    ldh [hRnHi + 24 + 2], a

    ld a, b                         ; the step 16r: third byte r >> 12,
    swap a                          ; low 16 bits r << 4
    and $0F
    ldh [hRnT2], a
REPT 4
    sla c
    rl b
ENDR
    ld de, hRnHi + 3
    ld hl, hRnHi
    RN_FILL LOW(hRnHi + 24)         ; TH[1..7]
    ld de, hRnHi + 27
    ld hl, hRnHi + 24
    RN_FILL LOW(hRnHi + 48)         ; TH[9..15]

    ; --- the per-element pass ---
    ld a, LOW(wX)
    ldh [hRnIdx], a
    ld a, [wRnGain + 0]
    ldh [hRnGain], a
    ld a, [wRnShift]
    ldh [hRnS], a
.elem
    ldh a, [hRnIdx]
    ld l, a
    ld h, HIGH(wX)
    ld a, [hl]                      ; x

    ; x * r = TH[x >> 4] + TL[x & 15], 24-bit; the tables are 3 bytes apart.
    ld c, a
    and $F0
    swap a                          ; m
    ld l, a
    add a, a
    add a, l                        ; 3m
    add a, LOW(hRnHi)
    ld l, a
    ld h, HIGH(hRnHi)
    ld e, [hl]
    inc l
    ld d, [hl]
    inc l
    ld b, [hl]                      ; b:d:e = TH[m]
    ld a, c
    and $0F
    ld l, a
    add a, a
    add a, l                        ; 3n
    add a, LOW(hRnLo)
    ld l, a
    ld a, [hl+]
    add a, e
    ld e, a
    ld a, [hl+]
    adc a, d
    ld d, a
    ld a, [hl]
    adc a, b
    ld h, d
    ld l, e
    ld e, a                         ; e:hl = x * r

    ldh a, [hRnP]
    ld b, a
    call ShrRound24to16             ; hl = xh = shr_round(x * r, p), Q11
    ld b, h
    ld c, l

    ldh a, [hRnGain]                ; the gain, and advance
    ld l, a
    inc a
    ldh [hRnGain], a
    ld a, [wRnGain + 1]
    ld h, a
    ld a, [hl]
    call MulS16xU8                  ; e:hl = xh * g
    ldh a, [hRnS]
    ld b, a
    call ShrRound24to16             ; hl = shr_round(xh * g, s)

    ; sat8 of hl: in range when h is the sign l would extend to, with -128
    ; mapped to -127 as the twin's clip does; otherwise the sign of h picks
    ; the bound.
    ld a, l
    add a, a
    sbc a, a
    cp h
    jr nz, .clamp
    ld a, l
    cp $80
    jr nz, .store
    ld a, -127
    jr .store
.clamp
    bit 7, h
    ld a, 127
    jr z, .store
    ld a, -127
.store
    ld c, a
    ldh a, [hRnIdx]
    add a, DIM                      ; wXb sits DIM above wX, same page
    ld l, a
    ld h, HIGH(wXb)
    ld [hl], c
    sub a, DIM - 1                  ; the next source byte
    ldh [hRnIdx], a
    cp LOW(wX + DIM)
    jr nz, .elem
    ret

.zero                               ; ss = 0: the twin returns zeros
    ld hl, wXb
    ld b, DIM
    xor a
:   ld [hl+], a
    dec b
    jr nz, :-
    ret
