; Phase 2 work in progress: drives one real matvec + requantization so the
; generalized kernel can be checked bit-exact before the rest of the layer is
; built on top of it.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Phase2 code", ROM0

; Points the matvec at w1 of layer 0 with the exported test activation vector.
Phase2_Setup::
    ld hl, cb_w1
    ld de, wCbBuf
    ld bc, CB_LEVELS
    call CopyBytes

    ld hl, test_x
    ld de, wXb
    ld bc, DIM
    call CopyBytes

    ld a, BANK(w1_l0)
    ld [wMvBank], a
    ld a, LOW(w1_l0)
    ld [wMvW + 0], a
    ld a, HIGH(w1_l0)
    ld [wMvW + 1], a

    ld a, DIM
    ld [wMvIn], a
    ld hl, HIDDEN
    call Matvec_SetOut

    ld a, LOW(wXb)
    ld [wMvXPtr + 0], a
    ld a, HIGH(wXb)
    ld [wMvXPtr + 1], a
    ld a, LOW(wCbBuf)
    ld [wMvCb + 0], a
    ld a, HIGH(wCbBuf)
    ld [wMvCb + 1], a
    ret

; matvec + requant into wH1, which is what the test compares.
Phase2_Run::
    call Matvec_Run
    ld de, w1_sh_l0
    ld bc, wH1
    jp Requant_All
