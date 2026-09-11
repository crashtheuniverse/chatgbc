; ReLU^2 as one page lookup, and the record of where it came out nonzero.
;
; The activation between w1 and w2 is u = sat8(shr_round(relu(a)^2, r)), a
; the int8 output of w1 and r one constant per layer: a function of one byte.
; So the exporter evaluates the twin's line (twin5.forward_q5) at all 256
; bytes and ships it as a page per layer, relu2_tbl (py/export5.py,
; relu2_page); this loop indexes the page by the raw byte. Entries 128..255
; are the negative a and hold zero, so the clamp is in the table with the
; square, the shift and the saturation - where the register path this
; replaces spent ~190 cycles per element in ShiftRound24 and Sat8_24.
;
; u is mostly zero (measured on 6,291 tokens: 27 / 23 / 42 nonzero of 176
; per layer), and the place that knows which are not is this loop. So it
; also writes the list the sparse w2 kernel walks (src/matvec_sparse.asm):
; (i, u) for every nonzero u in index order, a $FF sentinel after the last,
; and the count in wSpCount for the guard. The dense vector wHb stays: the
; layer-0 snapshot and the dense fallback read it.
;
; Placement makes the loop. wH1 ends at the top of its page and wHb sits at
; the same offset of the page above, so l indexes both (inc h to store) and
; `inc l` wrapping to zero is the end test - no counter, no compare.
;
; Per element, counted (M-cycles):
;   ld c, [hl]      2   a
;   ld a, [bc]      2   u = T[a]
;   inc h           1
;   ld [hl], a      2   wHb[i]
;   dec h           1
;   or a            1
;   jr nz, .nz      2   (3 when taken)
;   inc l           1
;   = 12, plus `jr nz, .elem` (3) once per four elements: 51 per four.
; A nonzero element adds 17: the taken branch, ld c,a 1; ld a,l 1; sub 2;
; ld [de],a 2; inc de 2; ld a,c 1; ld [de],a 2; inc de 2; jr .back 3.
; Per layer: 176 x 12 + 44 x 3 - 1 + 17 n + 43 (setup 13, sentinel and
; count 20, call and ret 10) = 2,286 + 17 n; at the measured means n = 27 /
; 23 / 42 that is 8,422 a token. The 8-token census says 8,752 (its own
; timers included) against 59,032 for the register path on the same tree.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; With experts the hidden width is per expert and HID_EXP == HIDDEN; the
; loop's page trick needs the vector inside one page, and the sentinel
; needs index 255 free.
ASSERT HIDDEN <= 255, "relu2: the hidden vector must fit one page below the sentinel"
ASSERT HIDDEN % 4 == 0, "relu2: the loop runs four elements a turn"
IF EXPERTS
ASSERT HID_EXP == HIDDEN, "relu2: an expert's hidden is the model's hidden"
ENDC

SECTION "FFN activations", WRAM0, ALIGN[8, 256 - HIDDEN]
wH1::   ds HIDDEN                   ; w1 output, int8, ending at the page top
        ds 256 - HIDDEN
wHb::   ds HIDDEN                   ; after ReLU^2, at the same offset above

SECTION "Sparse list", WRAM0
wSpList::  ds HIDDEN * 2 + 1        ; (i, u) for each nonzero u, then $FF
wSpCount:: db                       ; how many pairs

SECTION "ReLU2 code", ROM0

MACRO RELU2_ELEM                    ; \1 numbers the out-of-line nonzero stub
    ld c, [hl]
    ld a, [bc]
    inc h
    ld [hl], a
    dec h
    or a
    jr nz, .nz\1
.back\1
    inc l
ENDM

MACRO RELU2_NZ                      ; a = u, l = i + LOW(wH1), de = the list
.nz\1
    ld c, a
    ld a, l
    sub LOW(wH1)
    ld [de], a
    inc de
    ld a, c
    ld [de], a
    inc de
    jr .back\1
ENDM

; wH1 -> wHb through the layer's page, wSpList and wSpCount from what was
; nonzero. hl walks wH1, b:c is the page and the byte, de the list.
Relu2_Row::
    ld hl, wH1
    ld de, wSpList
    ld a, [wLayer]
    add a, HIGH(relu2_tbl)
    ld b, a
.elem
    RELU2_ELEM 0
    RELU2_ELEM 1
    RELU2_ELEM 2
    RELU2_ELEM 3
    jr nz, .elem
    ld a, $FF                       ; the sentinel the kernel stops on
    ld [de], a
    ld a, e                         ; count = (de - wSpList) / 2
    sub LOW(wSpList)
    ld c, a
    ld a, d
    sbc HIGH(wSpList)
    srl a
    rr c
    ld a, c
    ld [wSpCount], a
    ret
    RELU2_NZ 0
    RELU2_NZ 1
    RELU2_NZ 2
    RELU2_NZ 3
