; Grouped-query attention over the banked KV cache.
;
; The cache gives each layer one whole WRAM bank: 64 positions of 32 bytes of K
; followed by 64 of V is exactly 4096 bytes. So a layer switch is a single
; write to SVBK and every offset inside is a constant.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"


SECTION "Attention state", WRAM0
wAtHead:  db
wAtKvOff: db
wAtT:     db
wAtRecip: dw
wAtBits:  db
wAtMax:   ds 4
wAtDst:   dw

SECTION "Attention code", ROM0

; Selects the WRAM bank holding layer a's KV cache.
Attn_SelectBank::
    add a, KV_BANK_BASE
    ldh [rSVBK], a
    ret

; hl = K or V row base for position a (a = t), given wAtKvOff.
;   base + t * KV_DIM + kvOff
Attn_RowK:
    ld l, a
    ld h, 0
REPT 5
    add hl, hl                      ; t * 32
ENDR
    ld de, KV_K_BASE
    add hl, de
    ld a, [wAtKvOff]
    add a, l
    ld l, a
    ret nc
    inc h
    ret

Attn_RowV:
    ld l, a
    ld h, 0
REPT 5
    add hl, hl
ENDR
    ld de, KV_V_BASE
    add hl, de
    ld a, [wAtKvOff]
    add a, l
    ld l, a
    ret nc
    inc h
    ret

; scores[t] = sum over d of q[d] * K[t][kvOff + d], as int24 in wScores.
Attn_Scores:
    xor a
    ld [wAtT], a
.pos
    ld a, [wAtT]
    call Attn_RowK
    push hl

    xor a                           ; accumulator
    ld [wTmp32 + 0], a
    ld [wTmp32 + 1], a
    ld [wTmp32 + 2], a
    ld [wTmp32 + 3], a
    ld hl, wSave32
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a
    ld [hl], a

    pop hl
    ld a, [wHeadQ + 0]
    ld e, a
    ld a, [wHeadQ + 1]
    ld d, a
    ld b, HEAD_SIZE
.dot
    push bc
    push hl
    push de
    ld a, [de]                      ; q[d]
    ld [wMulA8], a
    ld a, [hl]                      ; K[t][kvOff+d]
    call SetMyFromS8
    call MulS8xS16
    ld hl, wSave32
    call Tmp32_AddTo
    pop de
    pop hl
    pop bc
    inc hl
    inc de
    dec b
    jr nz, .dot

    ld a, [wAtT]                    ; store the score
    ld l, a
    ld h, 0
    ld d, h
    ld e, l
    add hl, de
    add hl, de                      ; t * 3
    ld de, wScores
    add hl, de
    ld a, [wSave32 + 0]
    ld [hl+], a
    ld a, [wSave32 + 1]
    ld [hl+], a
    ld a, [wSave32 + 2]
    ld [hl], a

    ld a, [wAtT]
    inc a
    ld [wAtT], a
    ld b, a
    ld a, [wPos]
    cp b
    jp nc, .pos
    ret

; Loads scores[t] into wTmp32, sign-extended.
Attn_LoadScore:
    ld l, a
    ld h, 0
    ld d, h
    ld e, l
    add hl, de
    add hl, de
    ld de, wScores
    add hl, de
    ld a, [hl+]
    ld [wTmp32 + 0], a
    ld a, [hl+]
    ld [wTmp32 + 1], a
    ld a, [hl]
    ld [wTmp32 + 2], a
    jp Tmp32_SignExtend

; exp(score - max) into wAtt, and the running total into wTotal.
Attn_Softmax:
    xor a                           ; max = scores[0]
    call Attn_LoadScore
    ld hl, wTmp32
    ld de, wAtMax
    ld bc, 4
    call CopyBytes

    ld a, 1
    ld [wAtT], a
.findMax
    ld a, [wAtT]
    ld b, a
    ld a, [wPos]
    cp b
    jr c, .haveMax
    ld a, [wAtT]
    call Attn_LoadScore
    call SaveTmp32                  ; wSave32 = score
    ld hl, wAtMax                   ; wTmp32 = max, wSave32 = score
    ld de, wTmp32
    ld bc, 4
    call CopyBytes
    call SubTmpFromSave             ; wTmp32 = score - max
    ld a, [wTmp32 + 3]
    bit 7, a
    jr nz, .noNewMax
    ld a, [wAtT]
    call Attn_LoadScore
    ld hl, wTmp32
    ld de, wAtMax
    ld bc, 4
    call CopyBytes
.noNewMax
    ld a, [wAtT]
    inc a
    ld [wAtT], a
    jr .findMax

.haveMax
    xor a
    ld [wTotal + 0], a
    ld [wTotal + 1], a
    ld [wTotal + 2], a
    ld [wTotal + 3], a
    ld [wAtT], a
.expLoop
    ld a, [wAtT]
    call Attn_LoadScore
    call SaveTmp32                  ; wSave32 = score
    ld hl, wAtMax
    ld de, wTmp32
    ld bc, 4
    call CopyBytes                  ; wTmp32 = max
    call SwapSaveTmp                ; wSave32 = max, wTmp32 = score
    call SubTmpFromSave             ; wTmp32 = max - score, always >= 0
    ld a, [wAttShift]
    call Requant_Shift
    call ClampIndex255

    add a, a                        ; 16-bit table entries
    ld l, a
    ld h, 0
    ld de, tbl_exp
    add hl, de
    ld a, [hl+]
    ld c, a
    ld a, [hl]
    ld b, a                         ; bc = exp value

    ld a, [wAtT]                    ; store it in wAtt
    add a, a
    ld l, a
    ld h, 0
    ld de, wAtt
    add hl, de
    ld a, c
    ld [hl+], a
    ld a, b
    ld [hl], a

    ld a, c                         ; total += exp
    ld [wTmp32 + 0], a
    ld a, b
    ld [wTmp32 + 1], a
    xor a
    ld [wTmp32 + 2], a
    ld [wTmp32 + 3], a
    ld hl, wTotal
    call Tmp32_AddTo

    ld a, [wAtT]
    inc a
    ld [wAtT], a
    ld b, a
    ld a, [wPos]
    cp b
    jp nc, .expLoop

    ; Normalize with a reciprocal lookup instead of a division.
    ld hl, wTotal
    call BitLength32
    ld [wAtBits], a
    sub a, 8
    ld hl, wTotal
    call Shift32Trunc
    ld a, [wTotal + 0]
    add a, a
    ld l, a
    ld h, 0
    ld de, tbl_recip
    add hl, de
    ld a, [hl+]
    ld [wAtRecip + 0], a
    ld a, [hl]
    ld [wAtRecip + 1], a

    xor a
    ld [wAtT], a
.normLoop
    ld a, [wAtT]
    add a, a
    ld l, a
    ld h, 0
    ld de, wAtt
    add hl, de
    push hl
    ld a, [hl+]
    ld [wMx + 0], a
    ld a, [hl]
    ld [wMx + 1], a
    ld a, [wAtRecip + 0]
    ld [wMy + 0], a
    ld a, [wAtRecip + 1]
    ld [wMy + 1], a
    call MulU16
    ld a, [wAtBits]
    add a, RECIP_BITS - EXP_BITS
    call Requant_Shift
    pop hl
    ld a, [wTmp32 + 0]
    ld [hl+], a
    ld a, [wTmp32 + 1]
    ld [hl], a

    ld a, [wAtT]
    inc a
    ld [wAtT], a
    ld b, a
    ld a, [wPos]
    cp b
    jp nc, .normLoop
    ret

SwapSaveTmp:
    ld hl, wTmp32
    ld de, wSave32
    ld b, 4
.loop
    ld a, [hl]
    ld c, a
    ld a, [de]
    ld [hl+], a
    ld a, c
    ld [de], a
    inc de
    dec b
    jr nz, .loop
    ret

; Clamps wTmp32 into 0..255, returned in a.
ClampIndex255:
    ld a, [wTmp32 + 3]
    bit 7, a
    jr nz, .low
    ld a, [wTmp32 + 3]
    or a
    jr nz, .high
    ld a, [wTmp32 + 2]
    or a
    jr nz, .high
    ld a, [wTmp32 + 1]
    or a
    jr nz, .high
    ld a, [wTmp32 + 0]
    ret
.low
    xor a
    ret
.high
    ld a, 255
    ret

; xb2[h*HEAD_SIZE + d] = sat8(shr_round(sum over t of att[t] * V[t][kvOff+d]))
Attn_Weighted:
    ld b, HEAD_SIZE
    ld c, 0                         ; d
.dim
    push bc

    xor a
    ld hl, wSave32
    ld [hl+], a
    ld [hl+], a
    ld [hl+], a
    ld [hl], a

    xor a
    ld [wAtT], a
.acc
    ld a, [wAtT]
    call Attn_RowV
    ld b, 0
    ld a, c
    add a, l
    ld l, a
    jr nc, :+
    inc h
:   ld a, [hl]                      ; V[t][kvOff + d]
    ld [wMulA8], a

    ld a, [wAtT]
    add a, a
    ld l, a
    ld h, 0
    ld de, wAtt
    add hl, de
    ld a, [hl+]
    ld [wMy + 0], a
    ld a, [hl]
    ld [wMy + 1], a

    push bc
    call MulS8xS16
    ld hl, wSave32
    call Tmp32_AddTo
    pop bc

    ld a, [wAtT]
    inc a
    ld [wAtT], a
    ld d, a
    ld a, [wPos]
    cp d
    jp nc, .acc

    ld hl, wSave32
    ld de, wTmp32
    push bc
    ld bc, 4
    call CopyBytes
    pop bc
    ld a, [wAttOutShift]
    call Requant_Shift
    call Requant_Sat8

    ld e, a
    ld a, [wAtDst + 0]
    ld l, a
    ld a, [wAtDst + 1]
    ld h, a
    ld [hl], e
    inc hl
    ld a, l
    ld [wAtDst + 0], a
    ld a, h
    ld [wAtDst + 1], a

    pop bc
    inc c
    dec b
    jp nz, .dim
    ret

; Runs every head for the current layer, filling wXb2.
Attention::
    ld a, LOW(wXb2)
    ld [wAtDst + 0], a
    ld a, HIGH(wXb2)
    ld [wAtDst + 1], a
    xor a
    ld [wAtHead], a
.head
    ld a, [wAtHead]                 ; q slice for this head
    ld l, a
    ld h, 0
REPT 3
    add hl, hl                      ; h * HEAD_SIZE
ENDR
    ld de, wQ
    add hl, de
    ld a, l
    ld [wHeadQ + 0], a
    ld a, h
    ld [wHeadQ + 1], a

    ld a, [wAtHead]                 ; grouped queries: kv head = h / KV_MUL
    srl a
    add a, a
    add a, a
    add a, a                        ; * HEAD_SIZE
    ld [wAtKvOff], a

    call Attn_Scores
    call Attn_Softmax
    call Attn_Weighted

    ld a, [wAtHead]
    inc a
    ld [wAtHead], a
    cp N_HEADS
    jr c, .head
    ret
