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

; The largest matvec any forward pass runs is an FFN half - the register
; argmax classifier never touches wAcc, so sizing it by VOCAB was a v0.4
; relic that cost 672 bytes. At hidden 352 those bytes are the difference
; between the stack fitting and not.
DEF ACC_SLOTS EQU FFN_SPLIT
IF DIM > ACC_SLOTS
REDEF ACC_SLOTS EQU DIM
ENDC
IF EXPERTS
IF HID_EXP > ACC_SLOTS               ; an expert's w1 runs whole: HID_EXP outputs
REDEF ACC_SLOTS EQU HID_EXP
ENDC
ENDC

SECTION "Model state", WRAM0, ALIGN[4]
wAcc::   ds ACC_SLOTS * ACC_BYTES   ; reused by every matvec
wX::     ds DIM                     ; residual stream
wXb::    ds DIM                     ; post-rmsnorm activations
wH1::    ds HIDDEN
wHb::    ds HIDDEN
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
    ; The remaining bits, in registers. Shifting the scratch in place cost
    ; four loads and four stores a bit - 28 cycles for what `sra`/`rr` do in
    ; eight. The value comes into d:e:h:l once, shifts there, and goes back
    ; once with the rounding carry folded in on the way. de and hl are
    ; preserved for callers that keep pointers in them.
.right
    push de
    push hl
    ldh a, [wTmp32 + 3]
    ld d, a
    ldh a, [wTmp32 + 2]
    ld e, a
    ldh a, [wTmp32 + 1]
    ld h, a
    ldh a, [wTmp32 + 0]
    ld l, a
.bit
    sra d                           ; arithmetic: preserves sign
    rr e
    rr h
    rr l
    dec b                           ; dec leaves the carry alone
    jr nz, .bit
    ld a, l                         ; carry still holds the last bit shifted out
    adc a, 0
    ldh [wTmp32 + 0], a
    ld a, h
    adc a, 0
    ldh [wTmp32 + 1], a
    ld a, e
    adc a, 0
    ldh [wTmp32 + 2], a
    ld a, d
    adc a, 0
    ldh [wTmp32 + 3], a
    pop hl
    pop de
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

; The same numbers as Requant_All, at a third of the cycles.
;
; The census put a requant row at ~400 cycles: a 16-bit accumulator was being
; sign-extended into the 32-bit scratch, shifted through it a bit at a time
; via HRAM, then rounded and saturated back out. Two facts make that
; unnecessary. Every exported shift is small (5 to 10 in pip6; the exporter
; asserts s >= 2), and round-half-up by s is exactly: arithmetic shift by
; s-1, add one, shift by one - which cannot overflow int16 once s >= 2. So a
; row lives in hl from load to store, with no scratch at all.
;   de = per-output shift table, bc = destination, wMvOut = count
Requant_All16::
    ld a, e
    ld [wRqSh + 0], a
    ld a, d
    ld [wRqSh + 1], a
    ld a, [wMvOut + 0]
    ld [wRqCnt + 0], a
    ld a, [wMvOut + 1]
    ld [wRqCnt + 1], a
    ld de, wAcc
.row
    push bc                         ; destination, back at the store
    push de                         ; accumulator pointer
    ld a, [wRqSh + 0]
    ld e, a
    ld a, [wRqSh + 1]
    ld d, a
    ld a, [de]                      ; this row's shift, s
    inc de
    ld b, a
    ld a, e
    ld [wRqSh + 0], a
    ld a, d
    ld [wRqSh + 1], a
    pop de
    ld a, [de]                      ; the accumulator, int16
    ld l, a
    inc de
    ld a, [de]
    ld h, a
    inc de
    ; The stream sits on the trainer's grid now (exponent -3), so a row of
    ; w2 can ask for no shift at all, or for one to the LEFT: its sum is
    ; already on the grid, or below it. Neither has a half to round.
    ld a, b
    or a
    jr z, .sat8                     ; s == 0: the sum is the answer
    bit 7, a
    jr z, .right
.left                               ; s < 0: times 2 per step, saturating
    ld a, h                         ; |hl| >= 16384 would leave int16 on
    add a, 64                       ; doubling; its int8 answer is the sign
    cp 128
    jr nc, .satSign
    add hl, hl
    inc b
    jr nz, .left
    jr .sat8
.satSign
    bit 7, h
    ld a, 127
    jr z, .store
    ld a, -127
    jr .store
.right
    dec b                           ; s - 1 arithmetic shifts
    jr nz, .shift
    ; s == 1: nothing to pre-shift, and the +1 below would wrap the one
    ; accumulator equal to 32767. Its true result saturates to 127 anyway.
    ld a, h
    cp $7F
    jr nz, .rounded
    ld a, l
    cp $FF
    jr nz, .rounded
    ld a, 127
    jr .store
.shift
    sra h
    rr l
    dec b
    jr nz, .shift
.rounded
    inc hl                          ; + 1, then one more: round-half-up
    sra h
    rr l
.sat8
    ld a, l                         ; saturate to [-127, 127]: h must be the
    add a, a                        ; sign extension of l
    sbc a, a
    cp h
    jr nz, .sat
    ld a, l
    cp $80
    jr nz, .store
    ld a, -127                      ; -128 is outside the symmetric range
    jr .store
.sat
    bit 7, h
    ld a, 127
    jr z, .store
    ld a, -127
.store
    pop bc
    ld [bc], a
    inc bc
    ld hl, wRqCnt
    ld a, [hl]
    sub 1
    ld [hl+], a
    ld a, [hl]
    sbc a, 0
    ld [hl-], a
    or [hl]                         ; zero only when both bytes are
    jr nz, .row
    ret
