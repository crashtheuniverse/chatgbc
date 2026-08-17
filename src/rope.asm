; Rotary position embedding.
;
; A rotation preserves magnitude, so the site exponent is unchanged and the
; only shift is the Q15 table's own 15 bits. The table is (position, pair, 2)
; int16, so one position occupies HEAD_SIZE/2 * 2 * 2 = 16 bytes.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Rope state", WRAM0
wRopePos:: db
wRopePtr:  dw
wRopeTbl:  dw
wRopeC:    dw
wRopeS:    dw
wRopeV0:   db
wRopeV1:   db

SECTION "Rope code", ROM0

; --- RoPE ------------------------------------------------------------------
;
; A rotation preserves magnitude, so the site exponent is unchanged and the only
; shift is the Q15 table's own 15 bits. The table is (position, pair, 2) int16,
; so one position is HEAD_SIZE/2 * 2 * 2 = 16 bytes.
;   hl = vector, b = element count
Rope::
    ld a, BANK(tbl_rope)
    ld [rROMB0], a
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
