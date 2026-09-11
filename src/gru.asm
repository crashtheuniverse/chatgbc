; The recurrent heart, and the cheap square: what replaced attention.
;
; Two row kernels. Sigmoid_Row turns wz's output into Q0.8 gates through a
; per-layer ROM table - the exponent is baked into the table, so the kernel
; never sees it. Gate_Update folds the new candidate into the layer's state:
;
;     h = sat8( (zg*ht + (256-zg)*h + 128) >> 8 )
;
; computed as M(zg-128,ht) - M(zg-128,h) + ((ht+h) << 7) because the SM83's
; multiplier is the signed quarter-square table; the two forms are the same
; integer. The sum can reach 17 bits, so it accumulates in wTmp32 and closes
; through the same Requant_Shift/Sat8 every other kernel uses - one rounding
; rule in the whole machine.
;
; The MLP's activation, ReLU^2, lives in src/relu2.asm: one page lookup per
; element, and the list of nonzeros the sparse w2 kernel walks.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Gru state", WRAM0
wZl::   ds DIM                      ; wz output: gate logits, int8
wZg::   ds DIM                      ; sigmoid(logits), Q0.8
wHt::   ds DIM                      ; wh output: the candidate state
wGruH:: dw                          ; -> this layer's slice of wH
wGruSig:: dw                        ; -> this layer's sigmoid table

SECTION "Gru HRAM", HRAM
hGruCnt: db

SECTION "Gru code", ROM0

; wZl -> wZg through the layer's table. The table index is zl + 128, which as
; a byte is zl XOR $80.
Sigmoid_Row::
    ld a, [wGruSig + 0]
    ld e, a
    ld a, [wGruSig + 1]
    ld d, a
    ld hl, wZl
    ld bc, wZg
    ld a, DIM
    ldh [hGruCnt], a
.dim
    ld a, [hl+]
    xor $80
    push hl
    ld l, a
    ld h, 0
    add hl, de
    ld a, [hl]
    pop hl
    ld [bc], a
    inc bc
    ldh a, [hGruCnt]
    dec a
    ldh [hGruCnt], a
    jr nz, .dim
    ret

; One layer's state update, in place: wH slice = gate(wZg, wHt, wH slice).
Gate_Update::
    ld a, DIM
    ldh [hGruCnt], a
    ld a, LOW(wZg)
    ld [wGzPtr + 0], a
    ld a, HIGH(wZg)
    ld [wGzPtr + 1], a
    ld a, LOW(wHt)
    ld [wGtPtr + 0], a
    ld a, HIGH(wHt)
    ld [wGtPtr + 1], a
    ld a, [wGruH + 0]
    ld [wGhPtr + 0], a
    ld a, [wGruH + 1]
    ld [wGhPtr + 1], a

.dim
    ; s = M(zs, ht) - M(zs, h) + ((ht + h) << 7), and |s| <= 32,512 (the
    ; twin's bound), so the whole element fits signed 16-bit registers. The
    ; scratch-based version of this cost ~800 cycles an element: two exact
    ; products stored, subtracted and added through HRAM a byte at a time.
    ld a, [wGzPtr + 0]
    ld l, a
    ld a, [wGzPtr + 1]
    ld h, a
    ld a, [hl]
    xor $80                         ; zs = zg - 128, as a signed byte
    ld c, a
    ld a, [wGtPtr + 0]
    ld l, a
    ld a, [wGtPtr + 1]
    ld h, a
    ld b, [hl]                      ; ht
    push bc                         ; Mul_S8xS8 clobbers everything
    ld a, c
    call Mul_S8xS8                  ; hl = zs * ht
    pop bc
    push hl
    push bc
    ld a, [wGhPtr + 0]
    ld l, a
    ld a, [wGhPtr + 1]
    ld h, a
    ld b, [hl]                      ; h
    ld a, c
    call Mul_S8xS8                  ; hl = zs * h
    ld a, l                         ; de = -(zs * h)
    cpl
    ld e, a
    ld a, h
    cpl
    ld d, a
    inc de
    pop bc                          ; b = ht
    pop hl                          ; zs * ht
    add hl, de                      ; zs * (ht - h)
    push hl
    ld a, [wGhPtr + 0]
    ld l, a
    ld a, [wGhPtr + 1]
    ld h, a
    ld a, [hl]                      ; h
    ld l, a
    add a, a
    sbc a, a
    ld h, a                         ; hl = h, s16
    ld e, b
    ld a, b
    add a, a
    sbc a, a
    ld d, a                         ; de = ht, s16
    add hl, de                      ; ht + h, |.| <= 254
REPT 7
    add hl, hl
ENDR
    pop de
    add hl, de                      ; s

    ; sat8(shr_round(s, 8)): shift by seven, add one, shift once more.
REPT 7
    sra h
    rr l
ENDR
    inc hl
    sra h
    rr l
    ld a, l
    add a, a
    sbc a, a
    cp h
    jr nz, .sat
    ld a, l
    cp $80
    jr nz, .have
    ld a, -127                      ; -128 is outside the symmetric range
    jr .have
.sat
    bit 7, h
    ld a, 127
    jr z, .have
    ld a, -127
.have

    ld c, a                         ; store the new state, advance all three
    ld a, [wGhPtr + 0]
    ld l, a
    ld a, [wGhPtr + 1]
    ld h, a
    ld [hl], c
    inc hl
    ld a, l
    ld [wGhPtr + 0], a
    ld a, h
    ld [wGhPtr + 1], a
    ld hl, wGzPtr
    inc [hl]
    jr nz, :+
    ld hl, wGzPtr + 1
    inc [hl]
:   ld hl, wGtPtr
    inc [hl]
    jr nz, :+
    ld hl, wGtPtr + 1
    inc [hl]
:   ldh a, [hGruCnt]
    dec a
    ldh [hGruCnt], a
    jp nz, .dim
    ret

SECTION "Gru pointers", WRAM0
wGzPtr: dw
wGtPtr: dw
wGhPtr: dw
