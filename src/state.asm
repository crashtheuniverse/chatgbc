; Activation buffers, the shared 32-bit scratch, and requantization.
;
; Everything lives in WRAM bank 0 so it is always mapped; the switchable banks
; are reserved for the KV cache, one bank per layer.
;
; wTmp32 is the scratch every kernel funnels through: multiplies land in it,
; Requant_Shift rescales it, Requant_Sat8 reads it out as int8. Having one
; scratch and one shift routine is why there is no second, subtly different
; rounding rule anywhere in the model.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Model state", WRAM0, ALIGN[4]
wAcc::   ds VOCAB * ACC_BYTES       ; reused by every matvec; the classifier is largest
wX::     ds DIM                     ; residual stream
wXb::    ds DIM                     ; post-rmsnorm activations
wXb2::   ds DIM                     ; attention output
wQ::     ds DIM
wH1::    ds HIDDEN
wH3::    ds HIDDEN
wHb::    ds HIDDEN
wScores:: ds SEQ_LEN * SCORE_BYTES  ; raw attention scores, int24
wAtt::   ds SEQ_LEN * 2             ; softmax weights, Q0.12
wCbBuf:: ds CB_LEVELS               ; working copy of the active codebook
wTmp32:: ds 4                       ; shared signed scratch
wBias::  ds 3                       ; nIn * MV_BIAS, removed once per matvec

SECTION "Requant state", WRAM0
wRqAcc:: dw
wRqSh::  dw
wRqDst:: dw
wRqCnt:: dw

SECTION "Requant code", ROM0

; Nothing to unwind: the exported tables are signed and pre-halved, so the
; accumulator is a plain signed 16-bit sum.
Requant_SetBias::
    ret

; Sign-extends wTmp32's third byte into the fourth.
Tmp32_SignExtend::
    ld a, [wTmp32 + 2]
    add a, a
    sbc a, a                        ; $FF if negative, else $00
    ld [wTmp32 + 3], a
    ret

; hl -> accumulator slot. Sign-extends the signed 16-bit accumulator into
; wTmp32 and advances hl past the slot.
Requant_LoadUnbiased::
    ld a, [hl+]
    ld [wTmp32 + 0], a
    ld a, [hl+]
    ld [wTmp32 + 1], a
    add a, a                        ; carry = bit 15
    sbc a, a                        ; $FF if negative, else $00
    ld [wTmp32 + 2], a
    ld [wTmp32 + 3], a
    ret

; Shifts wTmp32 by the signed count in a. Negative shifts left.
; Clobbers a and b - callers holding a loop counter there must save it.
;
; Round-half-up needs no precomputed constant: (x + 2^(s-1)) >> s carries into
; bit s exactly when bit s-1 of x was set, and that bit is what the final shift
; leaves in the carry flag. `dec b` and `jr nz` touch Z/N/H but not C, so the
; carry survives the loop and a chain of `adc a, 0` applies it.
Requant_Shift::
    bit 7, a
    jr nz, .leftShift
    or a
    ret z
    ld b, a
.right
    ld a, [wTmp32 + 3]
    sra a                           ; arithmetic: preserves sign
    ld [wTmp32 + 3], a
    ld a, [wTmp32 + 2]
    rra
    ld [wTmp32 + 2], a
    ld a, [wTmp32 + 1]
    rra
    ld [wTmp32 + 1], a
    ld a, [wTmp32 + 0]
    rra
    ld [wTmp32 + 0], a
    dec b
    jr nz, .right

    ld a, [wTmp32 + 0]              ; carry still holds the last bit shifted out
    adc a, 0
    ld [wTmp32 + 0], a
    ld a, [wTmp32 + 1]
    adc a, 0
    ld [wTmp32 + 1], a
    ld a, [wTmp32 + 2]
    adc a, 0
    ld [wTmp32 + 2], a
    ld a, [wTmp32 + 3]
    adc a, 0
    ld [wTmp32 + 3], a
    ret

.leftShift
    cpl
    inc a                           ; a = -shift
    ld b, a
.left
    ld a, [wTmp32 + 0]
    add a, a
    ld [wTmp32 + 0], a
    ld a, [wTmp32 + 1]
    adc a, a
    ld [wTmp32 + 1], a
    ld a, [wTmp32 + 2]
    adc a, a
    ld [wTmp32 + 2], a
    ld a, [wTmp32 + 3]
    adc a, a
    ld [wTmp32 + 3], a
    dec b
    jr nz, .left
    ret

; Saturates wTmp32 into a, matching quant.py's sat8 range of [-127, 127].
; Clobbers b and c.
Requant_Sat8::
    ld a, [wTmp32 + 0]
    ld c, a
    add a, a
    sbc a, a                        ; b = $FF if the low byte is negative
    ld b, a
    ld a, [wTmp32 + 1]
    cp b
    jr nz, .clamp
    ld a, [wTmp32 + 2]
    cp b
    jr nz, .clamp
    ld a, [wTmp32 + 3]
    cp b
    jr nz, .clamp
    ld a, c                         ; the high bytes are pure sign extension
    cp $80
    ret nz
    ld a, -127                      ; -128 is outside the symmetric range
    ret
.clamp
    ld a, [wTmp32 + 3]
    bit 7, a
    ld a, 127
    ret z
    ld a, -127
    ret

; Converts every accumulator in wAcc to int8.
;   de = per-output shift table (ROM0, one signed byte each)
;   bc = destination buffer
; wMvOut gives the count, wMvIn the bias.
Requant_All::
    ld a, e
    ld [wRqSh + 0], a
    ld a, d
    ld [wRqSh + 1], a
    ld a, c
    ld [wRqDst + 0], a
    ld a, b
    ld [wRqDst + 1], a
    ld a, [wMvOut + 0]
    ld [wRqCnt + 0], a
    ld a, [wMvOut + 1]
    ld [wRqCnt + 1], a
    call Requant_SetBias
    ld a, LOW(wAcc)
    ld [wRqAcc + 0], a
    ld a, HIGH(wAcc)
    ld [wRqAcc + 1], a

.next
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

    ld a, c
    call Requant_Shift
    call Requant_Sat8

    ld c, a
    ld a, [wRqDst + 0]
    ld l, a
    ld a, [wRqDst + 1]
    ld h, a
    ld [hl], c
    inc hl
    ld a, l
    ld [wRqDst + 0], a
    ld a, h
    ld [wRqDst + 1], a

    ld hl, wRqCnt
    ld a, [hl]
    sub a, 1
    ld [hl+], a
    ld a, [hl]
    sbc a, 0
    ld [hl], a
    ld b, a
    ld a, [wRqCnt + 0]
    or b
    jr nz, .next
    ret
