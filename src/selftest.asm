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
IF !TERNARY
    ld a, BANK(lut_w1)
    ld [wMvLutBank], a
    ld a, LOW(lut_w1)
    ld [wMvLutAddr + 0], a
    ld a, HIGH(lut_w1)
    ld [wMvLutAddr + 1], a
ENDC

    ld hl, test_x
    ld de, wXb
    ld bc, DIM
    call CopyBytes

IF EXPERTS
    ld a, BANK(w1_l0_e0)            ; expert 0 of layer 0, whole
    ld [wMvBank], a
    ld a, LOW(w1_l0_e0)
    ld [wMvW + 0], a
    ld a, HIGH(w1_l0_e0)
    ld [wMvW + 1], a
    ld a, BLOCKS_DIM
    ld [wMvIn], a
    ld hl, HID_EXP
    call Matvec_SetOut
ELSE
    ld a, BANK(w1a_l0)
    ld [wMvBank], a
    ld a, LOW(w1a_l0)
    ld [wMvW + 0], a
    ld a, HIGH(w1a_l0)
    ld [wMvW + 1], a

IF TERNARY
    ld a, BLOCKS_DIM
ELSE
    ld a, DIM
ENDC
    ld [wMvIn], a
    ld hl, FFN_SPLIT
    call Matvec_SetOut
ENDC

    ld a, LOW(wXb)
    ld [wMvXPtr + 0], a
    ld a, HIGH(wXb)
    ld [wMvXPtr + 1], a
    ret

; Both halves, exactly as the forward pass runs them, so the split path is the
; covered path and test_h1 stays the full row.
IF TERNARY
DEF SELFTEST_RUN EQUS "Matvec3_Run"
ELSE
DEF SELFTEST_RUN EQUS "Matvec_Run"
ENDC

Selftest_Run::
IF EXPERTS
    call Matvec3_Run
    ld de, w1_sh_l0_e0
    ld bc, wH1
    jp Requant_All16
ELSE
    call SELFTEST_RUN
    ld de, w1a_sh_l0
    ld bc, wH1
    call Requant_All16
    ld a, BANK(w1b_l0)
    ld [wMvBank], a
    ld a, LOW(w1b_l0)
    ld [wMvW + 0], a
    ld a, HIGH(w1b_l0)
    ld [wMvW + 1], a
    ld hl, HIDDEN - FFN_SPLIT
    call Matvec_SetOut
    call SELFTEST_RUN
    ld de, w1b_sh_l0
    ld bc, wH1 + FFN_SPLIT
    jp Requant_All16
ENDC
