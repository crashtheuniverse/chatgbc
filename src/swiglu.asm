; SwiGLU: hb = silu(h1) * h3, with sigmoid read from the Q4.4 table.
;
; MulS8xS16 clobbers both hl and de, so the element pointers live in WRAM
; rather than in registers across the calls.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "SwiGLU state", WRAM0
wSiluIdxShift:  db
wSiluP1:        dw
wSiluP3:        dw
wSiluOutShift:: db
wHbPtr::        dw

SECTION "SwiGLU code", ROM0

; --- SwiGLU ----------------------------------------------------------------
;
; hb = silu(h1) * h3, with sigmoid read from the Q4.4-indexed table.
;   a = index shift, wSiluOutShift = output shift
; MulS8xS16 clobbers both hl and de, so the element pointers live in WRAM rather
; than in registers across the calls.
SiluMul::
    ld [wSiluIdxShift], a
    ld a, LOW(wH1)
    ld [wSiluP1 + 0], a
    ld a, HIGH(wH1)
    ld [wSiluP1 + 1], a
    ld a, LOW(wH3)
    ld [wSiluP3 + 0], a
    ld a, HIGH(wH3)
    ld [wSiluP3 + 1], a
    ld bc, HIDDEN
.elem
    push bc

    ld a, [wSiluP1 + 0]             ; index the sigmoid table in Q4.4
    ld l, a
    ld a, [wSiluP1 + 1]
    ld h, a
    ld a, [hl]
    ldh [wTmp32 + 0], a
    add a, a
    sbc a, a
    ldh [wTmp32 + 1], a
    ldh [wTmp32 + 2], a
    ldh [wTmp32 + 3], a
    ld a, [wSiluIdxShift]
    call Requant_Shift
    call Clamp127                   ; the table spans -128..127 in Q4.4
    add a, 128                      ; the table is indexed unsigned
    ld l, a
    ld h, 0
    ld de, tbl_sigmoid
    add hl, de
    ld a, [hl]
    ld [wMy + 0], a
    xor a
    ld [wMy + 1], a                 ; sigmoid output is unsigned Q0.8

    ld a, [wSiluP1 + 0]             ; silu = h1 * sigmoid(h1)
    ld l, a
    ld a, [wSiluP1 + 1]
    ld h, a
    ld a, [hl]
    ld [wMulA8], a
    call MulS8xS16
    ldh a, [wTmp32 + 0]
    ld [wMy + 0], a
    ldh a, [wTmp32 + 1]
    ld [wMy + 1], a

    ld a, [wSiluP3 + 0]             ; * h3
    ld l, a
    ld a, [wSiluP3 + 1]
    ld h, a
    ld a, [hl]
    ld [wMulA8], a
    call MulS8xS16
    ld a, [wSiluOutShift]
    call Requant_Shift
    call Requant_Sat8

    ld c, a
    ld a, [wHbPtr + 0]
    ld l, a
    ld a, [wHbPtr + 1]
    ld h, a
    ld [hl], c
    inc hl
    ld a, l
    ld [wHbPtr + 0], a
    ld a, h
    ld [wHbPtr + 1], a

    ld hl, wSiluP1                  ; advance both element pointers
    inc [hl]
    jr nz, :+
    inc hl
    inc [hl]
:   ld hl, wSiluP3
    inc [hl]
    jr nz, :+
    inc hl
    inc [hl]
:
    pop bc
    dec bc
    ld a, b
    or c
    jp nz, .elem
    ret

; Clamps wTmp32's low byte to -128..127 based on the full value.
Clamp127:
    ldh a, [wTmp32 + 1]
    ld b, a
    ldh a, [wTmp32 + 0]
    add a, a
    sbc a, a
    cp b
    jr nz, .out
    ldh a, [wTmp32 + 2]
    cp b
    jr nz, .out
    ldh a, [wTmp32 + 0]
    ret
.out
    ldh a, [wTmp32 + 3]
    bit 7, a
    ld a, 127
    ret z
    ld a, -128
    ret
