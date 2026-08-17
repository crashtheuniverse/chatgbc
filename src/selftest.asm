; Standalone matvec + requantization self-test.
;
; Runs w1 of layer 0 against an exported activation vector and leaves the result
; in wH1, where py/tests/test_matvec.py checks it bit-for-bit against the twin.
; It exercises the same code the forward pass uses, but independently of it, so
; the kernel stays covered even while the full pass is being debugged.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Selftest code", ROM0

Selftest_Setup::
    ld a, BANK(lut_w1)
    ld [wMvLutBank], a
    ld a, LOW(lut_w1)
    ld [wMvLutAddr + 0], a
    ld a, HIGH(lut_w1)
    ld [wMvLutAddr + 1], a

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
    ret

Selftest_Run::
    call Matvec_Run
    ld de, w1_sh_l0
    ld bc, wH1
    jp Requant_All
