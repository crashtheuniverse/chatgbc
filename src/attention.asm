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
wWAcc:    ds HEAD_SIZE * 4      ; one accumulator per dimension

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
; wSave32 += hl, sign-extended. Three bytes is enough: a score is q.k over eight
; terms and peaks at 129,032.
Score_Add:
    ld a, h
    add a, a
    sbc a, a
    ld d, a
    ldh a, [wSave32 + 0]
    add a, l
    ldh [wSave32 + 0], a
    ldh a, [wSave32 + 1]
    adc a, h
    ldh [wSave32 + 1], a
    ldh a, [wSave32 + 2]
    adc a, d
    ldh [wSave32 + 2], a
    ret

Attn_Scores:
    xor a
    ld [wAtT], a
.pos
    ld a, [wAtT]
    call Attn_RowK
    push hl

    xor a                           ; accumulator
    ldh [wTmp32 + 0], a
    ldh [wTmp32 + 1], a
    ldh [wTmp32 + 2], a
    ldh [wTmp32 + 3], a
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
    ld b, a
    ld a, [hl]                      ; K[t][kvOff+d]
    call Mul_S8xS8                  ; hl = the exact product
    call Score_Add
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
    ldh a, [wSave32 + 0]
    ld [hl+], a
    ldh a, [wSave32 + 1]
    ld [hl+], a
    ldh a, [wSave32 + 2]
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
    ldh [wTmp32 + 0], a
    ld a, [hl+]
    ldh [wTmp32 + 1], a
    ld a, [hl]
    ldh [wTmp32 + 2], a
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
    ldh a, [wTmp32 + 3]
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
    ldh [wTotal + 0], a
    ldh [wTotal + 1], a
    ldh [wTotal + 2], a
    ldh [wTotal + 3], a
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

    ld l, a                         ; 16-bit index; dd a, a would drop bit 8
    ld h, 0
    add hl, hl
    ld de, tbl_exp
    add hl, de
    ld a, [hl+]
    ld c, a
    ld a, [hl]
    ld b, a                         ; bc = exp value

    ld a, [wAtT]                    ; store it in wAtt
    ld l, a
    ld h, 0
    add hl, hl
    ld de, wAtt
    add hl, de
    ld a, c
    ld [hl+], a
    ld a, b
    ld [hl], a

    ld a, c                         ; total += exp
    ldh [wTmp32 + 0], a
    ld a, b
    ldh [wTmp32 + 1], a
    xor a
    ldh [wTmp32 + 2], a
    ldh [wTmp32 + 3], a
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
    ldh a, [wTotal + 0]
    ld l, a                         ; 16-bit index; recip indices are always >= 128
    ld h, 0
    add hl, hl
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
    ld l, a
    ld h, 0
    add hl, hl
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
    ldh a, [wTmp32 + 0]
    ld [hl+], a
    ldh a, [wTmp32 + 1]
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
    ldh a, [wTmp32 + 3]
    bit 7, a
    jr nz, .low
    ldh a, [wTmp32 + 3]
    or a
    jr nz, .high
    ldh a, [wTmp32 + 2]
    or a
    jr nz, .high
    ldh a, [wTmp32 + 1]
    or a
    jr nz, .high
    ldh a, [wTmp32 + 0]
    ret
.low
    xor a
    ret
.high
    ld a, 255
    ret

; xb2[h*HEAD_SIZE + d] = sat8(shr_round(sum over t of att[t] * V[t][kvOff+d]))
Attn_Weighted:
    ; One accumulator per dimension, so the loops can be the right way round.
    ;
    ; This used to iterate d on the outside and t on the inside, which meant the
    ; V row pointer and the attention weight were recomputed for every (d, t)
    ; pair - eight times more often than they change. Now t is outermost: the
    ; row and the weight are set up once per position and eight products are
    ; taken against them.
    ;
    ; Summation order changes, which for integers changes nothing: the total is
    ; the same and the result stays bit-exact.
    ld hl, wWAcc
    ld b, HEAD_SIZE * 4
    xor a
.zero
    ld [hl+], a
    dec b
    jr nz, .zero

    xor a
    ld [wAtT], a
.pos
    ld a, [wAtT]                    ; wMy = wAtt[t], once per position
    ld l, a
    ld h, 0
    add hl, hl
    ld de, wAtt
    add hl, de
    ld a, [hl+]
    ld [wMy + 0], a
    ld a, [hl]
    ld [wMy + 1], a

    ld a, [wAtT]                    ; hl = &V[t][kvOff], once per position
    call Attn_RowV

    ld c, 0
.dim
    ld a, [hl]                      ; V[t][kvOff + d]
    ld [wMulA8], a
    push hl
    push bc
    call MulS8xS16
    pop bc
    ld a, c                         ; hl = &wWAcc[d]
    add a, a
    add a, a
    ld l, a
    ld h, 0
    ld de, wWAcc
    add hl, de
    call Tmp32_AddTo
    pop hl
    inc hl
    inc c
    ld a, c
    cp HEAD_SIZE
    jr c, .dim

    ld a, [wAtT]
    inc a
    ld [wAtT], a
    ld d, a
    ld a, [wPos]
    cp d
    jp nc, .pos

    ; Requantize each accumulator and write it out.
    ld c, 0
.out
    ld a, c
    add a, a
    add a, a
    ld l, a
    ld h, 0
    ld de, wWAcc
    add hl, de
    ld de, wTmp32
    push bc
    ld bc, 4
    call CopyBytes
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
    ld a, c
    cp HEAD_SIZE
    jr c, .out
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
