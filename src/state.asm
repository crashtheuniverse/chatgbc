; Activation buffers and requantization.
;
; Everything lives in WRAM bank 0 so it is always mapped; the switchable banks
; are reserved entirely for the KV cache, one bank per layer.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Model state", WRAM0, ALIGN[4]
wAcc::   ds VOCAB * ACC_BYTES       ; reused by every matvec; the classifier is largest
wX::     ds DIM                     ; residual stream
wXb::    ds DIM                     ; post-rmsnorm activations
wXb2::   ds DIM                     ; attention output
wQ::     ds DIM
wKvec::  ds KV_DIM
wVvec::  ds KV_DIM
wH1::    ds HIDDEN
wH3::    ds HIDDEN
wHb::    ds HIDDEN
wAtt::   ds SEQ_LEN * 2             ; softmax weights, Q0.12
wCbBuf:: ds CB_LEVELS               ; working copy of the active codebook
wTmp24:: ds 3
wBias::  ds 3                       ; nIn * MV_BIAS, removed once per matvec

SECTION "Requant state", WRAM0
wRqAcc:  dw
wRqSh:   dw
wRqDst:  dw
wRqCnt:  dw

SECTION "Requant code", ROM0

; The matvec accumulates nIn * MV_BIAS. MV_BIAS is 1<<14, so the correction is
; just nIn shifted left 14 - no multiply.
Requant_SetBias::
    ld a, [wMvIn]
    ld b, a
    xor a
    ld [wBias + 0], a               ; low byte is always zero
    ld a, b
    rrca
    rrca
    and %00111111
    ld [wBias + 2], a               ; nIn >> 2
    ld a, b
    rlca
    rlca
    rlca
    rlca
    rlca
    rlca
    and %11000000
    ld [wBias + 1], a               ; (nIn << 6) & $FF
    ret

; hl -> accumulator slot. Loads it into wTmp24 minus the bias, leaving a signed
; int24, and advances hl past the slot.
Requant_LoadUnbiased:
    ld a, [wBias + 0]
    ld c, a
    ld a, [hl+]
    sub a, c
    ld [wTmp24 + 0], a
    ld a, [wBias + 1]
    ld c, a
    ld a, [hl+]
    sbc a, c
    ld [wTmp24 + 1], a
    ld a, [wBias + 2]
    ld c, a
    ld a, [hl+]
    sbc a, c
    ld [wTmp24 + 2], a
    ret

; Shifts wTmp24 by the signed count in a. Negative shifts left.
;
; Round-half-up needs no precomputed constant: (x + 2^(s-1)) >> s carries into
; bit s exactly when bit s-1 of x was set, and that bit is what the final shift
; leaves in the carry flag. `dec b` and `jr nz` touch Z/N/H but not C, so the
; carry survives the loop and a chain of `adc a, 0` applies it.
Requant_Shift:
    bit 7, a
    jr nz, .leftShift
    or a
    ret z
    ld b, a
.right
    ld a, [wTmp24 + 2]
    sra a                           ; arithmetic: preserves sign
    ld [wTmp24 + 2], a
    ld a, [wTmp24 + 1]
    rra
    ld [wTmp24 + 1], a
    ld a, [wTmp24 + 0]
    rra
    ld [wTmp24 + 0], a
    dec b
    jr nz, .right

    ld a, [wTmp24 + 0]              ; carry still holds the last bit shifted out
    adc a, 0
    ld [wTmp24 + 0], a
    ld a, [wTmp24 + 1]
    adc a, 0
    ld [wTmp24 + 1], a
    ld a, [wTmp24 + 2]
    adc a, 0
    ld [wTmp24 + 2], a
    ret

.leftShift
    cpl
    inc a                           ; a = -shift
    ld b, a
.left
    ld a, [wTmp24 + 0]
    add a, a
    ld [wTmp24 + 0], a
    ld a, [wTmp24 + 1]
    adc a, a
    ld [wTmp24 + 1], a
    ld a, [wTmp24 + 2]
    adc a, a
    ld [wTmp24 + 2], a
    dec b
    jr nz, .left
    ret

; Saturates wTmp24 into a, matching quant.py's sat8 range of [-127, 127].
Requant_Sat8:
    ld a, [wTmp24 + 0]
    ld c, a
    add a, a
    sbc a, a                        ; b = $FF if the low byte is negative, else $00
    ld b, a
    ld a, [wTmp24 + 1]
    cp b
    jr nz, .clamp
    ld a, [wTmp24 + 2]
    cp b
    jr nz, .clamp
    ld a, c                         ; the high bytes are pure sign extension
    cp $80
    ret nz
    ld a, -127                      ; -128 is outside the symmetric range
    ret
.clamp
    ld a, [wTmp24 + 2]
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
