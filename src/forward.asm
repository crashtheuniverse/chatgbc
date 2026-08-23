; The transformer forward pass and greedy decode loop.
;
; Mirrors forward_q() in py/quant.py step for step. Every matvec goes through
; the same Matvec_Run / Requant_All pair; only the manifest entry, the shift
; table and the destination change.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Forward debug", WRAM0
; Layer 0 snapshots, so py/diffstep.py can tell an attention bug from an FFN one.
wDbgAtt::   ds DIM
wDbgFfn::   ds DIM
wDbgRes::   ds DIM

SECTION "Forward state", WRAM0
wToken::    dw
wStep::     db
wMatIdx:    db
wBestTok::  dw
wBest:      ds 4
wClsPart:   db

SECTION "Forward code", ROM0

; --- matvec plumbing -------------------------------------------------------

; Points the matvec at a matrix's precomputed product tables.
;   a = bank, hl = base address
SetLut:
    ld [wMvLutBank], a
    ld a, l
    ld [wMvLutAddr + 0], a
    ld a, h
    ld [wMvLutAddr + 1], a
    ret

; Points the matvec at one (tensor, layer) chunk.
;   hl = banks table, de = addrs table, a = layer
SetMatrix:
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [wMvBank], a
    ld h, d
    ld l, e
    add hl, bc
    add hl, bc
    ld a, [hl+]
    ld [wMvW + 0], a
    ld a, [hl]
    ld [wMvW + 1], a
    ret

; hl = shift table pointer for layer a.
ShiftTable:
    ld c, a
    ld b, 0
    add hl, bc
    add hl, bc
    ld a, [hl+]
    ld c, a
    ld a, [hl]
    ld h, a
    ld l, c
    ret

SetXPtr:
    ld a, l
    ld [wMvXPtr + 0], a
    ld a, h
    ld [wMvXPtr + 1], a
    ret

; --- one layer -------------------------------------------------------------

; Runs layer wLayer over wX.
ForwardLayer::
    ld a, [wLayer]
    call Attn_SelectBank

    ; --- attention block ---
    ld hl, rms_att                  ; gain for this layer
    ld a, [wLayer]
    ld de, DIM
    call OffsetByLayer
    ld a, l
    ld [wRnGain + 0], a
    ld a, h
    ld [wRnGain + 1], a
    ld hl, rmsatt_shift
    ld a, [wLayer]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [wRnShift], a
    ld hl, wX
    call SetRnSrc
    ld hl, wXb
    call SetRnDst
    call RmsNorm

    ld hl, wXb
    call SetXPtr
    ld a, DIM
    ld [wMvIn], a

    ld a, BANK(lut_wq)
    ld hl, lut_wq
    call SetLut
    ld hl, wq_banks
    ld de, wq_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
    call Matvec_Run
    ld hl, wq_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wQ
    call Requant_All

    ; 8-bit, nibble-split. No SetLut: the hi/lo tables depend only on
    ; the activation, not on the matrix, so Matvec_BuildLutCls names
    ; them directly and wk has no product table of its own.
    ld hl, wk_banks
    ld de, wk_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, KV_DIM
    call Matvec_SetOut
    call Matvec_RunCls
    ld hl, wk_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wKvec
    call Requant_All

    ; 8-bit, nibble-split. No SetLut: the hi/lo tables depend only on
    ; the activation, not on the matrix, so Matvec_BuildLutCls names
    ; them directly and wv has no product table of its own.
    ld hl, wv_banks
    ld de, wv_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, KV_DIM
    call Matvec_SetOut
    call Matvec_RunCls
    ld hl, wv_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wVvec
    call Requant_All

    ld a, [wAbsPos]
    ld [wRopePos], a
    ld hl, wQ
    ld b, DIM
    call Rope
    ld a, [wAbsPos]
    ld [wRopePos], a
    ld hl, wKvec
    ld b, KV_DIM
    call Rope

    call StoreKV

    ld hl, att_shift
    ld a, [wLayer]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [wAttShift], a
    ld hl, attout_shift
    ld a, [wLayer]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [wAttOutShift], a
    call Attention

    ld a, [wLayer]                  ; snapshot layer 0's attention output
    or a
    jr nz, :+
    ld hl, wXb2
    ld de, wDbgAtt
    ld bc, DIM
    call CopyBytes
:
    ld hl, wXb2
    call SetXPtr
    ld a, DIM
    ld [wMvIn], a
    ld a, BANK(lut_wo)
    ld hl, lut_wo
    call SetLut
    ld hl, wo_banks
    ld de, wo_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
    call Matvec_Run
    ld hl, wo_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wXb
    call Requant_All
    ld hl, wXb                      ; residual: both sides already share X_EXP
    ld de, wX
    ld b, DIM
    call AddSaturating
    ld a, [wLayer]                  ; snapshot x after the attention residual
    or a
    jr nz, :+
    ld hl, wX
    ld de, wDbgRes
    ld bc, DIM
    call CopyBytes
:

    ; --- feed-forward block ---
    ld hl, rms_ffn
    ld a, [wLayer]
    ld de, DIM
    call OffsetByLayer
    ld a, l
    ld [wRnGain + 0], a
    ld a, h
    ld [wRnGain + 1], a
    ld hl, rmsffn_shift
    ld a, [wLayer]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [wRnShift], a
    ld hl, wX
    call SetRnSrc
    ld hl, wXb
    call SetRnDst
    call RmsNorm

    ld hl, wXb
    call SetXPtr
    ld a, DIM
    ld [wMvIn], a

    ld a, BANK(lut_w1)
    ld hl, lut_w1
    call SetLut
    ld hl, w1_banks
    ld de, w1_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, HIDDEN
    call Matvec_SetOut
    call Matvec_Run
    ld hl, w1_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wH1
    call Requant_All

    ld a, BANK(lut_w3)
    ld hl, lut_w3
    call SetLut
    ld hl, w3_banks
    ld de, w3_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, HIDDEN
    call Matvec_SetOut
    call Matvec_Run
    ld hl, w3_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wH3
    call Requant_All

    ld hl, silu_out_shift
    ld a, [wLayer]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [wSiluOutShift], a
    ld a, LOW(wHb)
    ld [wHbPtr + 0], a
    ld a, HIGH(wHb)
    ld [wHbPtr + 1], a
    ld hl, silu_idx_shift
    ld a, [wLayer]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    call SiluMul

    ld hl, wHb
    call SetXPtr
    ld a, HIDDEN
    ld [wMvIn], a
    ld a, BANK(lut_w2)
    ld hl, lut_w2
    call SetLut
    ld hl, w2_banks
    ld de, w2_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
    call Matvec_Run
    ld hl, w2_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wXb
    call Requant_All
    ld a, [wLayer]                  ; snapshot layer 0's FFN output
    or a
    jr nz, :+
    ld hl, wXb
    ld de, wDbgFfn
    ld bc, DIM
    call CopyBytes
:
    ld hl, wXb
    ld de, wX
    ld b, DIM
    jp AddSaturating

SetRnSrc:
    ld a, l
    ld [wRnSrc + 0], a
    ld a, h
    ld [wRnSrc + 1], a
    ret

SetRnDst:
    ld a, l
    ld [wRnDst + 0], a
    ld a, h
    ld [wRnDst + 1], a
    ret

; hl += a * de
OffsetByLayer:
    or a
    ret z
    ld b, a
.loop
    add hl, de
    dec b
    jr nz, .loop
    ret

; de[i] = sat8(de[i] + hl[i]) for b elements.
; Requant_Sat8 uses b and c as scratch, so the counter has to be saved.
; Both operands are sign-extended to a full 32 bits before adding. Extending
; only one of them and carrying `adc a, 0` into the top bytes turns a negative
; addend into a huge positive, which then saturates to +127.
AddSaturating::
    ld a, [hl+]
    push hl
    push de
    push bc
    ldh [wTmp32 + 0], a
    add a, a
    sbc a, a
    ldh [wTmp32 + 1], a
    ldh [wTmp32 + 2], a
    ldh [wTmp32 + 3], a
    ld a, [de]
    ldh [wSave32 + 0], a
    add a, a
    sbc a, a
    ldh [wSave32 + 1], a
    ldh [wSave32 + 2], a
    ldh [wSave32 + 3], a
    call AddSaveToTmp
    call Requant_Sat8
    pop bc
    pop de
    ld [de], a
    inc de
    pop hl
    dec b
    jr nz, AddSaturating
    ret

; Copies wKvec/wVvec into this layer's cache slot for the current position.
StoreKV:
    ; Ring: position p occupies slot p mod SEQ_LEN.
    ;
    ; A mask would be one instruction but only works for power-of-two windows,
    ; and that constraint cost the best window on the quality curve. This runs
    ; five times a token - once per layer - so even the naive form is free:
    ; at most ten subtractions, about 70 cycles, against twelve million.
    ld a, [wAbsPos]
.slot
    cp SEQ_LEN
    jr c, .haveSlot
    sub SEQ_LEN
    jr .slot
.haveSlot
    ld l, a
    ld h, 0
REPT 5
    add hl, hl                      ; pos * KV_DIM
ENDR
    push hl
    ld de, KV_K_BASE
    add hl, de
    ld d, h
    ld e, l
    ld hl, wKvec
    ld bc, KV_DIM
    call CopyBytes
    pop hl
    ld de, KV_V_BASE
    add hl, de
    ld d, h
    ld e, l
    ld hl, wVvec
    ld bc, KV_DIM
    jp CopyBytes

; --- whole forward pass ----------------------------------------------------

; wToken -> the argmax token, left in wBestTok.
Forward::
    call EmbedToken

    xor a
    ld [wLayer], a
.layer
    call ForwardLayer
    ld a, [wLayer]
    inc a
    ld [wLayer], a
    cp N_LAYERS
    jp c, .layer

    ld hl, rms_final
    ld a, l
    ld [wRnGain + 0], a
    ld a, h
    ld [wRnGain + 1], a
    ld a, RMSFINAL_SHIFT
    ld [wRnShift], a
    ld hl, wX
    call SetRnSrc
    ld hl, wXb
    call SetRnDst
    call RmsNorm
    ; fall through

; Streams the classifier and keeps only the running best, so 512 logits never
; have to be stored. Each vocabulary row carries its own scale, so the raw
; accumulators are not comparable until the row shift is applied.
Classify::
    ld hl, VOCAB
    call Matvec_SetOut

    ; Stream the classifier one bank at a time, accumulating into the same
    ; outputs. Four parts now that each weight carries two HRAM offsets.
    xor a
    ld [wClsPart], a
.part
    ld a, [wClsPart]
    ld l, a
    ld h, 0
    ld de, cls_banks
    add hl, de
    ld a, [hl]
    ld [wMvBank], a

    ld a, [wClsPart]
    add a, a
    ld l, a
    ld h, 0
    ld de, cls_addrs
    add hl, de
    ld a, [hl+]
    ld [wMvW + 0], a
    ld a, [hl]
    ld [wMvW + 1], a

    ld a, CLS_INPUTS_PER_PART
    ld [wMvIn], a

    ld a, [wClsPart]                ; x slice for this part
    ld l, a
    ld h, 0
REPT 4
    add hl, hl                      ; * CLS_INPUTS_PER_PART (16)
ENDR
    ld de, wXb
    add hl, de
    call SetXPtr

    ld a, [wClsPart]
    or a
    jr nz, .accum
    call Matvec_RunCls              ; first part clears the accumulators
    jr .next
.accum
    call Matvec_RunClsAccum
.next
    ld a, [wClsPart]
    inc a
    ld [wClsPart], a
    cp CLS_PARTS
    jr c, .part

    ld a, DIM                       ; the bias covers every input, every part
    ld [wMvIn], a
    call Requant_SetBias

    ld a, $80                       ; best = most negative int32
    ld [wBest + 3], a
    xor a
    ld [wBest + 0], a
    ld [wBest + 1], a
    ld [wBest + 2], a
    ld [wBestTok + 0], a
    ld [wBestTok + 1], a

    ld a, LOW(wAcc)
    ld [wRqAcc + 0], a
    ld a, HIGH(wAcc)
    ld [wRqAcc + 1], a
    ld a, LOW(cls_lshift)
    ld [wRqSh + 0], a
    ld a, HIGH(cls_lshift)
    ld [wRqSh + 1], a
    xor a
    ld [wRqCnt + 0], a
    ld [wRqCnt + 1], a

.scan
    ld a, [wRqAcc + 0]
    ld l, a
    ld a, [wRqAcc + 1]
    ld h, a
    call Requant_LoadUnbiased
    ld a, l
    ld [wRqAcc + 0], a
    ld a, h
    ld [wRqAcc + 1], a

    ld a, [wRqSh + 0]
    ld l, a
    ld a, [wRqSh + 1]
    ld h, a
    ld a, [hl+]
    ld c, a
    ld a, l
    ld [wRqSh + 0], a
    ld a, h
    ld [wRqSh + 1], a

    ld a, c                         ; the table holds a left shift
    cpl
    inc a
    call Requant_Shift

    call CompareBest

    ld hl, wRqCnt                   ; advance the token index
    ld a, [hl]
    add a, 1
    ld [hl+], a
    ld a, [hl]
    adc a, 0
    ld [hl], a
    ld a, [wRqCnt + 0]
    cp LOW(VOCAB)
    jp nz, .scan
    ld a, [wRqCnt + 1]
    cp HIGH(VOCAB)
    jp nz, .scan
    ret

; Keeps wTmp32 if it beats wBest, recording the current index as the winner.
;
; The SM83 has no sign flag, so a signed compare is done by hand: if the sign
; bits differ the positive value wins, otherwise an unsigned compare from the
; top byte down gives the right answer.
CompareBest:
    ldh a, [wTmp32 + 3]
    ld b, a
    ld a, [wBest + 3]
    ld c, a
    xor b
    bit 7, a
    jr z, .sameSign
    bit 7, b
    ret nz                          ; candidate is negative, best is not
    jr .take

.sameSign
    ld a, b
    cp c
    ret c
    jr nz, .take
    ld hl, wBest + 2
    ldh a, [wTmp32 + 2]
    cp [hl]
    ret c
    jr nz, .take
    ld hl, wBest + 1
    ldh a, [wTmp32 + 1]
    cp [hl]
    ret c
    jr nz, .take
    ld hl, wBest + 0
    ldh a, [wTmp32 + 0]
    cp [hl]
    ret c
    ret z                           ; ties keep the earlier token, as argmax does

.take
    ld hl, wTmp32
    ld de, wBest
    ld bc, 4
    call CopyBytes
    ld a, [wRqCnt + 0]
    ld [wBestTok + 0], a
    ld a, [wRqCnt + 1]
    ld [wBestTok + 1], a
    ret

; wX = requantized embedding row for wToken. The table is 32 KB, so it spans two
; banks of 256 tokens each.
EmbedToken:
    ld a, [wToken + 1]
    or a
    jr z, .part0
    ld de, emb_rows_p1
    ld a, BANK(emb_rows_p1)
    jr .haveBank
.part0
    ld de, emb_rows_p0
    ld a, BANK(emb_rows_p0)
.haveBank
    ld [rROMB0], a

    ld a, [wToken + 0]
    ld l, a
    ld h, 0
REPT 6
    add hl, hl                      ; (token & 255) * DIM
ENDR
    add hl, de

    ld de, wX
    ld bc, DIM
    push hl
    call CopyBytes
    pop hl

    ld a, [wToken + 0]              ; per-token shift
    ld l, a
    ld a, [wToken + 1]
    ld h, a
    ld de, emb_shift
    add hl, de
    ld a, [hl]
    ld [wRnShift], a

    ld hl, wX                       ; rescale in place
    ld b, DIM
.scale
    ld a, [hl]
    push hl
    push bc                         ; Requant_Shift and Requant_Sat8 both use b
    ldh [wTmp32 + 0], a
    add a, a
    sbc a, a
    ldh [wTmp32 + 1], a
    ldh [wTmp32 + 2], a
    ldh [wTmp32 + 3], a
    ld a, [wRnShift]
    call Requant_Shift
    call Requant_Sat8
    pop bc
    pop hl
    ld [hl+], a
    dec b
    jp nz, .scale
    ret
