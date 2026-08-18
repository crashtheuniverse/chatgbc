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
wBias::  ds 3                       ; nIn * MV_BIAS, removed once per matvec

; The shared 32-bit scratch lives in HRAM, not WRAM. Every kernel funnels
; through it, and absolute access to $FF00-$FFFE assembles as `ldh` - a two-byte
; instruction costing 3 M-cycles where `ld a, [nn]` costs 4. One cycle per
; access does not sound like much until you count how many accesses there are:
; Requant_Shift alone touches it eight times per bit shifted.
SECTION "Scratch HRAM", HRAM
wTmp32::  ds 4                      ; shared signed scratch
wSave32:: ds 4                      ; second operand for the 32-bit add/subtract
wTotal::  ds 4                      ; softmax running total

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
    ldh a, [wTmp32 + 2]
    add a, a
    sbc a, a                        ; $FF if negative, else $00
    ldh [wTmp32 + 3], a
    ret

; hl -> accumulator slot. Sign-extends the signed 16-bit accumulator into
; wTmp32 and advances hl past the slot.
Requant_LoadUnbiased::
    ld a, [hl+]
    ldh [wTmp32 + 0], a
    ld a, [hl+]
    ldh [wTmp32 + 1], a
    add a, a                        ; carry = bit 15
    sbc a, a                        ; $FF if negative, else $00
    ldh [wTmp32 + 2], a
    ldh [wTmp32 + 3], a
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
    jp nz, .leftShift
    or a
    ret z
    ld b, a
    ; A shift of eight is a byte move, not eight shifts. The counts here are
    ; calibration data - 13 to 16 in practice - so peeling whole bytes off first
    ; replaces ~350 cycles of bit shifting with ~30. The test is `> 8` and not
    ; `>= 8` on purpose: the last bit to leave the value must still go one bit at
    ; a time, because the carry it strands is the rounding bit the tail reads.
.bytes
    ld a, b
    cp 9
    jp c, .nibble
    ldh a, [wTmp32 + 1]
    ldh [wTmp32 + 0], a
    ldh a, [wTmp32 + 2]
    ldh [wTmp32 + 1], a
    ldh a, [wTmp32 + 3]
    ldh [wTmp32 + 2], a
    add a, a
    sbc a, a                        ; $FF if negative, else $00
    ldh [wTmp32 + 3], a
    ld a, b
    sub 8
    ld b, a
    jr .bytes

    ; And a shift of four is a nibble swap. `swap` exchanges the two halves of a
    ; byte in one instruction - it is an SM83 addition the Z80 never had - so a
    ; 4-bit shift is one pass of swap-and-merge instead of four passes of
    ; shift-through-carry. At most one of these ever runs, since b is 8 or less
    ; by the time we get here, and the same `one bit must leave singly` rule
    ; applies: the threshold is 5, not 4.
    ;
    ; Bytes are rewritten low to high. Each one needs the low nibble of the byte
    ; above it, so that byte has to still be untouched when its turn comes.
.nibble
    cp 5
    jr c, .right
    push de
FOR i, 3
    ldh a, [wTmp32 + i + 1]
    swap a
    and $F0                         ; the byte above supplies the high nibble
    ld d, a
    ldh a, [wTmp32 + i]
    swap a
    and $0F
    or d
    ldh [wTmp32 + i], a
ENDR
    ldh a, [wTmp32 + 3]
    add a, a
    sbc a, a                        ; $FF if negative, else $00
    and $F0                         ; sign fills the nibble the shift vacates
    ld d, a
    ldh a, [wTmp32 + 3]
    swap a
    and $0F
    or d
    ldh [wTmp32 + 3], a
    pop de
    ld a, b
    sub 4
    ld b, a
.right
    ldh a, [wTmp32 + 3]
    sra a                           ; arithmetic: preserves sign
    ldh [wTmp32 + 3], a
    ldh a, [wTmp32 + 2]
    rra
    ldh [wTmp32 + 2], a
    ldh a, [wTmp32 + 1]
    rra
    ldh [wTmp32 + 1], a
    ldh a, [wTmp32 + 0]
    rra
    ldh [wTmp32 + 0], a
    dec b
    jr nz, .right

    ldh a, [wTmp32 + 0]              ; carry still holds the last bit shifted out
    adc a, 0
    ldh [wTmp32 + 0], a
    ldh a, [wTmp32 + 1]
    adc a, 0
    ldh [wTmp32 + 1], a
    ldh a, [wTmp32 + 2]
    adc a, 0
    ldh [wTmp32 + 2], a
    ldh a, [wTmp32 + 3]
    adc a, 0
    ldh [wTmp32 + 3], a
    ret

.leftShift
    cpl
    inc a                           ; a = -shift
    ld b, a
.left
    ldh a, [wTmp32 + 0]
    add a, a
    ldh [wTmp32 + 0], a
    ldh a, [wTmp32 + 1]
    adc a, a
    ldh [wTmp32 + 1], a
    ldh a, [wTmp32 + 2]
    adc a, a
    ldh [wTmp32 + 2], a
    ldh a, [wTmp32 + 3]
    adc a, a
    ldh [wTmp32 + 3], a
    dec b
    jr nz, .left
    ret

; Saturates wTmp32 into a, matching quant.py's sat8 range of [-127, 127].
; Clobbers b and c.
Requant_Sat8::
    ldh a, [wTmp32 + 0]
    ld c, a
    add a, a
    sbc a, a                        ; b = $FF if the low byte is negative
    ld b, a
    ldh a, [wTmp32 + 1]
    cp b
    jr nz, .clamp
    ldh a, [wTmp32 + 2]
    cp b
    jr nz, .clamp
    ldh a, [wTmp32 + 3]
    cp b
    jr nz, .clamp
    ld a, c                         ; the high bytes are pure sign extension
    cp $80
    ret nz
    ld a, -127                      ; -128 is outside the symmetric range
    ret
.clamp
    ldh a, [wTmp32 + 3]
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
