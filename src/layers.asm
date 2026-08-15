; RMSNorm, RoPE, softmax, SwiGLU and GQA attention.
;
; Each routine is a direct transcription of the matching function in
; py/quant.py, using the same tables and the same rounding, so the two can be
; diffed value for value.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Layer state", WRAM0
wRnSrc::   dw
wRnGain::  dw
wRnDst::   dw
wRnShift:: db
wSS:       ds 4
wRnR:      dw
wRnE:      db

wKvec::    ds KV_DIM
wVvec::    ds KV_DIM

wRopePos:: db
wRopePtr:  dw
wRopeTbl:  dw
wRopeC:    dw
wRopeS:    dw
wRopeV0:   db
wRopeV1:   db

wAttShift::    db
wAttOutShift:: db
wPos::         db                   ; current sequence position
wLayer::       db
wTotal::       ds 4
wSave32::      ds 4
wAccum:        ds 4
wHeadQ::       dw
wKvOff:        db

SECTION "Layer code", ROM0

; --- shared 32-bit helpers --------------------------------------------------

SaveTmp32::
    ld hl, wTmp32
    ld de, wSave32
    ld bc, 4
    jp CopyBytes

; wTmp32 = wSave32 - wTmp32. Loads and inc de leave the flags alone, so the
; borrow chain runs unbroken.
SubTmpFromSave::
    ld hl, wTmp32
    ld de, wSave32
    ld a, [de]
    sub a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    sbc a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    sbc a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    sbc a, [hl]
    ld [hl], a
    ret

AddSaveToTmp::
    ld hl, wTmp32
    ld de, wSave32
    ld a, [de]
    add a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    adc a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    adc a, [hl]
    ld [hl+], a
    inc de
    ld a, [de]
    adc a, [hl]
    ld [hl], a
    ret

; Truncating arithmetic shift of the 4 bytes at hl by the signed count in a.
; Table indices must truncate, not round, to match the twin.
Shift32Trunc::
    bit 7, a
    jr nz, .left
    or a
    ret z
    ld b, a
.right
    push hl
    inc hl
    inc hl
    inc hl
    ld a, [hl]
    sra a
    ld [hl-], a
    ld a, [hl]
    rra
    ld [hl-], a
    ld a, [hl]
    rra
    ld [hl-], a
    ld a, [hl]
    rra
    ld [hl], a
    pop hl
    dec b
    jr nz, .right
    ret
.left
    cpl
    inc a
    ld b, a
.leftLoop
    push hl
    ld a, [hl]
    add a, a
    ld [hl+], a
    ld a, [hl]
    adc a, a
    ld [hl+], a
    ld a, [hl]
    adc a, a
    ld [hl+], a
    ld a, [hl]
    adc a, a
    ld [hl], a
    pop hl
    dec b
    jr nz, .leftLoop
    ret

; --- RMSNorm ---------------------------------------------------------------
;
; x_hat = x / rms(x), then an elementwise gain. The rms ratio is scale-free, so
; the input exponent cancels and never enters the arithmetic. With RSQRT_BITS
; 14, sqrt(DIM) = 2^3 and a Q11 intermediate, the constant part of the shift
; cancels exactly and only e/2 remains.
RmsNorm::
    xor a
    ld [wSS + 0], a
    ld [wSS + 1], a
    ld [wSS + 2], a
    ld [wSS + 3], a

    ld a, [wRnSrc + 0]
    ld l, a
    ld a, [wRnSrc + 1]
    ld h, a
    ld b, DIM
.sumsq
    ld a, [hl+]
    push hl
    push bc
    ld [wMulA8], a
    call SetMyFromS8
    call MulS8xS16
    ld hl, wSS
    call Tmp32_AddTo
    pop bc
    pop hl
    dec b
    jr nz, .sumsq

    ld hl, wSS
    call BitLength32
    or a
    jp z, .zero
    bit 0, a
    jr z, :+
    inc a                           ; round up to even so sqrt(2^e) is a shift
:   ld b, a
    srl a
    ld [wRnE], a

    ld a, b
    sub a, 8
    ld hl, wSS
    call Shift32Trunc               ; index = ss >> (e - 8)
    ld a, [wSS + 0]
    add a, a                        ; 16-bit table entries
    ld l, a
    ld h, 0
    ld de, tbl_rsqrt
    add hl, de
    ld a, [hl+]
    ld [wRnR + 0], a
    ld a, [hl]
    ld [wRnR + 1], a

    ld a, [wRnSrc + 0]
    ld l, a
    ld a, [wRnSrc + 1]
    ld h, a
    ld b, DIM
.scale
    ld a, [hl+]
    push hl
    push bc

    ld [wMulA8], a                  ; x_hat = shr_round(x * r, e/2), as Q11
    ld a, [wRnR + 0]
    ld [wMy + 0], a
    ld a, [wRnR + 1]
    ld [wMy + 1], a
    call MulS8xS16
    ld a, [wRnE]
    call Requant_Shift

    ld a, [wTmp32 + 0]              ; fold in the gain, land on int8
    ld [wMy + 0], a
    ld a, [wTmp32 + 1]
    ld [wMy + 1], a
    ld a, [wRnGain + 0]
    ld e, a
    ld a, [wRnGain + 1]
    ld d, a
    ld a, [de]
    ld [wMulA8], a
    inc de
    ld a, e
    ld [wRnGain + 0], a
    ld a, d
    ld [wRnGain + 1], a
    call MulS8xS16
    ld a, [wRnShift]
    call Requant_Shift
    call Requant_Sat8

    ld c, a
    ld a, [wRnDst + 0]
    ld e, a
    ld a, [wRnDst + 1]
    ld d, a
    ld a, c
    ld [de], a
    inc de
    ld a, e
    ld [wRnDst + 0], a
    ld a, d
    ld [wRnDst + 1], a

    pop bc
    pop hl
    dec b
    jp nz, .scale
    ret

.zero
    ld a, [wRnDst + 0]
    ld l, a
    ld a, [wRnDst + 1]
    ld h, a
    ld b, DIM
    xor a
:   ld [hl+], a
    dec b
    jr nz, :-
    ret

; --- RoPE ------------------------------------------------------------------
;
; A rotation preserves magnitude, so the site exponent is unchanged and the only
; shift is the Q15 table's own 15 bits. The table is (position, pair, 2) int16,
; so one position is HEAD_SIZE/2 * 2 * 2 = 16 bytes.
;   hl = vector, b = element count
Rope::
    ld a, l
    ld [wRopePtr + 0], a
    ld a, h
    ld [wRopePtr + 1], a

    ld a, [wRopePos]
    ld l, a
    ld h, 0
REPT 4
    add hl, hl                      ; pos * 16 bytes
ENDR
    ld de, tbl_rope
    add hl, de
    ld a, l
    ld [wRopeTbl + 0], a
    ld a, h
    ld [wRopeTbl + 1], a

    srl b                           ; pairs, not elements
    ld c, 0                         ; pair index, restarts at each head
.pair
    push bc

    ld a, c                         ; 4 bytes of table per pair
    add a, a
    add a, a
    ld e, a
    ld d, 0
    ld a, [wRopeTbl + 0]
    ld l, a
    ld a, [wRopeTbl + 1]
    ld h, a
    add hl, de
    ld a, [hl+]
    ld [wRopeC + 0], a
    ld a, [hl+]
    ld [wRopeC + 1], a
    ld a, [hl+]
    ld [wRopeS + 0], a
    ld a, [hl]
    ld [wRopeS + 1], a

    ld a, [wRopePtr + 0]
    ld l, a
    ld a, [wRopePtr + 1]
    ld h, a
    ld a, [hl+]
    ld [wRopeV0], a
    ld a, [hl]
    ld [wRopeV1], a

    ld a, [wRopeV0]                 ; out0 = shr_round(v0*c - v1*s, 15)
    ld [wMulA8], a
    call SetMyFromRopeC
    call MulS8xS16
    call SaveTmp32
    ld a, [wRopeV1]
    ld [wMulA8], a
    call SetMyFromRopeS
    call MulS8xS16
    call SubTmpFromSave
    ld a, 15
    call Requant_Shift
    call Requant_Sat8
    ld c, a

    ld a, [wRopePtr + 0]
    ld l, a
    ld a, [wRopePtr + 1]
    ld h, a
    ld [hl], c

    ld a, [wRopeV0]                 ; out1 = shr_round(v0*s + v1*c, 15)
    ld [wMulA8], a
    call SetMyFromRopeS
    call MulS8xS16
    call SaveTmp32
    ld a, [wRopeV1]
    ld [wMulA8], a
    call SetMyFromRopeC
    call MulS8xS16
    call AddSaveToTmp
    ld a, 15
    call Requant_Shift
    call Requant_Sat8
    ld c, a

    ld a, [wRopePtr + 0]
    ld l, a
    ld a, [wRopePtr + 1]
    ld h, a
    inc hl
    ld [hl], c
    inc hl
    ld a, l
    ld [wRopePtr + 0], a
    ld a, h
    ld [wRopePtr + 1], a

    pop bc
    inc c
    ld a, c
    cp HEAD_SIZE / 2
    jr c, :+
    ld c, 0
:   dec b
    jp nz, .pair
    ret

SetMyFromRopeC:
    ld a, [wRopeC + 0]
    ld [wMy + 0], a
    ld a, [wRopeC + 1]
    ld [wMy + 1], a
    ret

SetMyFromRopeS:
    ld a, [wRopeS + 0]
    ld [wMy + 0], a
    ld a, [wRopeS + 1]
    ld [wMy + 1], a
    ret

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
    ld [wTmp32 + 0], a
    add a, a
    sbc a, a
    ld [wTmp32 + 1], a
    ld [wTmp32 + 2], a
    ld [wTmp32 + 3], a
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
    ld a, [wTmp32 + 0]
    ld [wMy + 0], a
    ld a, [wTmp32 + 1]
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
    ld a, [wTmp32 + 1]
    ld b, a
    ld a, [wTmp32 + 0]
    add a, a
    sbc a, a
    cp b
    jr nz, .out
    ld a, [wTmp32 + 2]
    cp b
    jr nz, .out
    ld a, [wTmp32 + 0]
    ret
.out
    ld a, [wTmp32 + 3]
    bit 7, a
    ld a, 127
    ret z
    ld a, -128
    ret

SECTION "Silu state", WRAM0
wSiluIdxShift:  db
wSiluP1:        dw
wSiluP3:        dw
wSiluOutShift:: db
wHbPtr::        dw
