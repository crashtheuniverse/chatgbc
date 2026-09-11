; Standalone matvec + requantization self-test.
;
; Runs w1 of layer 0 against an exported activation vector and leaves the result
; in wH1, where py/tests/test_kernels.py checks it bit-for-bit against the twin.
; It exercises the same code the forward pass uses, but independently of it, so
; the kernel stays covered even while the full pass is being debugged.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Selftest code", ROM0

Selftest_Setup::
IF !(TERNARY || BINARY)
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

IF TERNARY || BINARY
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
IF TERNARY || BINARY
IF BINARY
DEF SELFTEST_RUN EQUS "Matvec4b_Run"
ELSE
DEF SELFTEST_RUN EQUS "Matvec3_Run"
ENDC
ELSE
DEF SELFTEST_RUN EQUS "Matvec_Run"
ENDC

Selftest_Run::
IF EXPERTS
    BLOCK_RUN
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

IF EXPERTS
; The sparse w2 kernel and its guard, on the exporter's two w1 output
; vectors for layer 0 / expert 0: `b` has more nonzero u than W2_SPARSE_MAX
; and must take the dense block kernel, `a` fewer and must take the sparse
; one. Each runs the forward pass's own Relu2_Row and W2_Run; the sums, the
; path W2_Run reports and the list count go to WRAM bank 1, beside the
; diffstep snapshots, for py/tests/test_sparse_w2.py. `a` runs last, so wHb
; and wSpList are its when the harness looks.
SECTION "Sparse selftest results", WRAMX, BANK[1]
wDbgSpAccA:: ds DIM * 2             ; wAcc after vector a, int16
wDbgSpAccB:: ds DIM * 2             ; and after vector b
wDbgSpPath:: ds 2                   ; W2_Run's answer for a, then b
wDbgSpCount:: ds 2                  ; wSpCount for a, then b

SECTION "Sparse selftest code", ROM0

MACRO SPARSE_CASE                   ; \1 = the vector blob, \2 = 0 for a, 1 for b
    ld a, BANK(\1)
    ld [rROMB0], a
    ld hl, \1
    ld de, wH1
    ld bc, HIDDEN
    call CopyBytes
    call Relu2_Row
    call W2_Run
    ld [wDbgSpPath + \2], a
    ld a, [wSpCount]
    ld [wDbgSpCount + \2], a
    ld hl, wAcc
    IF \2
    ld de, wDbgSpAccB
    ELSE
    ld de, wDbgSpAccA
    ENDC
    ld bc, DIM * 2
    call CopyBytes
ENDM

SparseSelftest::
    ld a, 1
    ldh [rSVBK], a
    xor a
    ld [wLayer], a                  ; layer 0, expert 0: matrix index 0
    ld [wExpIdx], a
    SPARSE_CASE test_sp_b, 1
    SPARSE_CASE test_sp_a, 0
    ret
ENDC
