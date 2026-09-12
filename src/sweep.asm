; The output-major sweep: wz, wh, wo, w1 and the router over resident block
; tables, the row's sum in a register pair, the requant fused, nothing stored.
;
; What it computes: for each row o of a ternary matrix, acc = sum over the
; 64 inputs of t[o,i] * x[i], exact in int16, then out[o] = sat8(shr_round(
; acc, s_o)) - the twin's Q.matvec_blocks(block=3, shift=0) followed by
; Q.requant_rows, row by row. The router's rows end in an argmax instead.
;
; Why it is exact: TERNARY_ACC_SHIFT = 0, so every block sum is exact and a
; row's sum is their plain sum, the same integer whatever the order; the twin
; asserts |acc| <= 32767, so the 16-bit register sum is that integer. The
; requant is round-half-up by s: shr_round(acc, s) = floor(acc / 2^s) + bit
; s-1 of acc, and s arithmetic shifts leave exactly that bit in the carry
; (dec b and jr touch no carry). For s >= 2 the same value is reached as
; (acc >> (s-1)) + 1 >> 1 with nothing able to overflow (|acc >> 1| <=
; 16383); for s = 1 the +1 could wrap the one sum 32767, so that path adds
; the carry after the shift instead. Saturation to [-127, 127] with -128 to
; -127 is Requant_All16's rule, and the twin's sat8.
;
; The tables: Matvec3_BuildAll (src/matvec3.asm) writes block k's 27 exact
; int16 sums into slot k of wMvTbl, 64 bytes a slot, four a page, so block k
; lives on page HIGH(wMvTbl) + (k >> 2). The exporter (export5.sweep_rows)
; ships a row as one byte per block, ((k & 3) << 6) | (code << 1): the low
; address byte of the entry inside its page. The weight byte IS the table
; index; b walks the pages, one inc every four blocks. Then the shift byte,
; AFTER the codes so b is free during the sweep. A group of rows ends with
; SWEEP_END ($FF, a byte no block-0 code can be), so a caller sweeps a
; group into a destination and the next group continues where it stopped:
; wz then wh over one build of xb; the router's rows (no shift byte) open
; every expert's w1 blob, so the router and the chosen expert's rows sweep
; one build of xf from one bank.
;
; Per row, counted (M-cycles, CGB double speed):
;   ld b, HIGH(wMvTbl) 2; ld a,[hl+] 2; ld c,a 1; inc a 1; jr z 2;
;   ld a,[bc] 2; ld e,a 1; inc c 1; ld a,[bc] 2; ld d,a 1        = 15
;   21 x (ld a,[hl+] 2; ld c,a 1; ld a,[bc] 2; add a,e 1; ld e,a 1;
;         inc c 1; ld a,[bc] 2; adc a,d 1; ld d,a 1 = 12) + 5 inc b = 257
;   ld a,[hl+] 2; ld b,a 1; dec b 1; jr z 2                      = 6
;   (s-1) x (sra d 2; rr e 2; dec b 1; jr nz 3) - 1; inc de 2; sra 2; rr 2
;                                                                = 8s - 3
;   sat8, in range: ld a,e 1; add a,a 1; sbc a,a 1; cp d 1; jr nz 2;
;   ld a,e 1; cp $80 2; jr nz 3                                  = 12
;   pop bc 3; ld [bc],a 2; inc bc 2; push bc 4; jp 4              = 15
;   = 302 + 8s: 318 at s = 2, 342 at s = 5 - the shipped streams' shifts
;   are 2..5 (every group decoded from build/blobs; nothing below 2, nothing
;   above 5). The group end costs 9.
; Per token at 1,104 rows and the model's shifts (sum ~3,450): ~361K,
; against 817K for the input-major kernels and their requants it replaces.
;
; SWEEP_ROW is instantiated twice, in Sweep_Rows and in Sweep_Route, ~205 B
; of ROM0 each. Sharing one copy as a subroutine would cost the call and the
; ret - 6 + 4 = 10 cycles a row (the group-end test stays where it is) - on
; 1,104 rows a token: ~11K cycles, 1.1% of the 973K token, to recover ~205 B
; that nothing needs (the app map shows 1,988 B of ROM0 free). It stays
; unrolled twice; take the 205 B back the day ROM0 is short, not before.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

DEF SWEEP_END EQU $FF               ; export5.SWEEP_END
DEF MV_TBL_PAGES EQU (BLOCKS_DIM + 3) / 4
ASSERT MV_TBL_PAGES <= 16, "sweep: the block tables must fit one WRAM bank"

; The slots: page-aligned so a code byte is a low address byte, in the bank
; the layer-0 probes already map, so the forward pass never toggles SVBK.
SECTION "Block tables", WRAMX, BANK[MV_TBL_BANK], ALIGN[8]
wMvTbl:: ds BLOCKS_DIM * 64

SECTION "Sweep state", WRAM0
wRtBest: dw                         ; the router's best sum: low, then high sign-flipped
wRtIdx:  db                         ; the router row being swept

SECTION "Sweep code", ROM0

; One row's sum into de: block 0 loads, blocks 1.. add, b walks the pages.
; Falls into \1 on the group's end byte with hl past it.
MACRO SWEEP_ROW
    ld b, HIGH(wMvTbl)
    ld a, [hl+]
    ld c, a
    inc a                           ; SWEEP_END + 1 = 0
    jr z, \1
    ld a, [bc]
    ld e, a
    inc c
    ld a, [bc]
    ld d, a
FOR k, 1, BLOCKS_DIM
    IF (k & 3) == 0
    inc b
    ENDC
    ld a, [hl+]
    ld c, a
    ld a, [bc]
    add a, e
    ld e, a
    inc c
    ld a, [bc]
    adc a, d
    ld d, a
ENDR
ENDM

; One group of rows: hl = the rows (their ROM bank mapped, the tables built),
; de = the destination. Each row's int8 lands at de and on; returns hl past
; the group's end byte, de past the last output. Clobbers all.
Sweep_Rows::
    push de                         ; the destination, popped and pushed a row
    jr .row
.done                               ; ahead of the row, within a jr of its test
    pop de
    ret
.row
    SWEEP_ROW .done
    ld a, [hl+]                     ; s, after the codes
    ld b, a
    dec b
    jr z, .one
.shift                              ; s - 1 arithmetic shifts, then round
    sra d
    rr e
    dec b
    jr nz, .shift
    inc de                          ; + 1, then one more shift: round-half-up
    sra d
    rr e
.sat8
    ld a, e                         ; saturate to [-127, 127]: d must be the
    add a, a                        ; sign extension of e
    sbc a, a
    cp d
    jr nz, .sat
    ld a, e
    cp $80
    jr nz, .store
    ld a, -127                      ; -128 is outside the symmetric range
    jr .store
.sat
    bit 7, d
    ld a, 127
    jr z, .store
    ld a, -127
.store
    pop bc
    ld [bc], a
    inc bc
    push bc
    jp .row
.one                                ; s = 1: shift once; the bit shifted out
    sra d                           ; is the rounding, added after so 32767
    rr e                            ; cannot wrap
    ld a, e
    adc a, 0
    ld e, a
    ld a, d
    adc a, 0
    ld d, a
    jr .sat8

IF EXPERTS
; The router's rows: hl = EXPERTS rows without shift bytes, then the group's
; end. wExpert = the index of the largest sum, the lowest on a tie - the
; twin's np.argmax over exact block sums (twin5.route). Signed order via the
; sign-flipped high byte, strictly greater in row order, the best starting
; at -32768 (which the twin's assertion excludes). Returns hl past the end
; byte. Clobbers all. Per row: the sweep's 272 + the compare, 40 at most.
Sweep_Route::
    xor a
    ld [wRtBest + 0], a
    ld [wRtBest + 1], a
    ld [wRtIdx], a
    ld [wExpert], a
    jr .row
.done
    ret
.row
    SWEEP_ROW .done
    ld a, d
    xor $80
    ld c, a                         ; c:e = this row's sum, flipped
    ld a, [wRtBest + 1]
    cp c
    jr c, .take                     ; high byte greater
    jr nz, .keep                    ; smaller
    ld a, [wRtBest + 0]
    cp e
    jr nc, .keep                    ; low byte not greater: the earlier stays
.take
    ld a, c
    ld [wRtBest + 1], a
    ld a, e
    ld [wRtBest + 0], a
    ld a, [wRtIdx]
    ld [wExpert], a
.keep
    ld a, [wRtIdx]
    inc a
    ld [wRtIdx], a
    jp .row
ENDC
