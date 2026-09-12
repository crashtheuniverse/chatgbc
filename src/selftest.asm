; Standalone matvec + requantization self-test.
;
; Runs w1 of layer 0 against an exported activation vector and leaves the result
; in wH1, where py/tests/test_kernels.py checks it bit-for-bit against the twin.
; It exercises the same code the forward pass uses, but independently of it, so
; the kernel stays covered even while the full pass is being debugged. On the
; sweep it first routes the vector through layer 0's router rows (the expert
; into wDbgSwExpert), then runs the same w1 rows a second time at shifts the
; model never asks for (s = 1, saturating rows) into wDbgSwOut, and leaves
; the block tables of the test vector in wMvTbl for py/tests/test_sweep.py.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Selftest code", ROM0

; The test vector into wXb; then, for the input-major kernels only, their
; configuration cells. The sweep (EXPERTS && SWEEP) takes its input pointer
; and its rows as arguments and reads none of wMvBank / wMvW / wMvIn /
; wMvXPtr / wMvOut, so on that build the copy is the whole setup.
Selftest_Setup::
    ld hl, test_x
    ld de, wXb
    ld bc, DIM
    call CopyBytes
IF EXPERTS && SWEEP
    ret
ELSE
IF !(TERNARY || BINARY)
    ld a, BANK(lut_w1)
    ld [wMvLutBank], a
    ld a, LOW(lut_w1)
    ld [wMvLutAddr + 0], a
    ld a, HIGH(lut_w1)
    ld [wMvLutAddr + 1], a
ENDC

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
ENDC                                ; EXPERTS && SWEEP

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
IF SWEEP
    ld de, wXb
    call Matvec3_BuildAll           ; the tables of test_x, left for the test
    ld a, BANK(w1_l0_e0)
    ld [rROMB0], a
    ld hl, w1_l0_e0
    call Sweep_Route                ; the router rows that open the blob
    ld a, [wExpert]
    ld [wDbgSwExpert], a            ; bank 1, which Matvec3_BuildAll mapped
    ld de, wH1
    call Sweep_Rows                 ; the forward pass's own w1 path, expert 0
    ld a, BANK(test_sw)
    ld [rROMB0], a
    ld hl, test_sw
    ld de, wDbgSwOut
    jp Sweep_Rows
ELSE
    BLOCK_RUN
    ld de, w1_sh_l0_e0
    ld bc, wH1
    jp Requant_All16
ENDC
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
; layer-0 snapshots, for py/tests/test_sparse_w2.py. `a` runs last, so wHb
; and wSpList are its when the harness looks.
SECTION "Sparse selftest results", WRAMX, BANK[1]
wDbgSpAccA:: ds DIM * 2             ; wAcc after vector a, int16
wDbgSpAccB:: ds DIM * 2             ; and after vector b
wDbgSpPath:: ds 2                   ; W2_Run's answer for a, then b
wDbgSpCount:: ds 2                  ; wSpCount for a, then b
IF SWEEP
wDbgSwOut:: ds HID_EXP              ; the sweep over test_sw's synthetic shifts
wDbgSwExpert:: db                   ; layer 0's router on test_x
ENDC

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

IF DEF(PROBES)
; The embedding copy and the residual add, on the exporter's vectors, for
; py/tests/test_module_f.py. Lab builds only (build.ps1 -Lab): the app ROM
; has no reader for the answers and ROM0 has no room to spare. Both run
; after the generation, and both clobber wX / wXb - MeasureSelftest, which
; runs last, plants its own wXb.
SECTION "Module F selftest results", WRAMX, BANK[1]
wDbgEmb:: ds DIM                    ; wX after EmbedToken on TEST_EMB_TOKEN
wDbgAdd:: ds TEST_ADD_ROWS * DIM    ; wX after each row's AddSat_Stream

SECTION "Module F selftest code", ROM0

EmbedSelftest::
    ld a, 1
    ldh [rSVBK], a
    ld a, LOW(TEST_EMB_TOKEN)
    ld [wToken + 0], a
    ld a, HIGH(TEST_EMB_TOKEN)
    ld [wToken + 1], a
    call EmbedToken
    ld hl, wX
    ld de, wDbgEmb
    ld bc, DIM
    jp CopyBytes

; Row r of test_add_x into wX, row r of test_add_y into wXb, the add, and
; wX out to wDbgAdd + r * DIM, for r = 0..TEST_ADD_ROWS-1.
AddSelftest::
    ld a, 1
    ldh [rSVBK], a
    ld b, 0                         ; the row
    ld de, wDbgAdd
.row
    push de
    push bc
    ld a, BANK(test_add_x)
    ld [rROMB0], a
    ld hl, test_add_x
    ld a, b
    call .rowptr
    ld de, wX
    ld bc, DIM
    call CopyBytes
    pop bc
    push bc
    ld a, BANK(test_add_y)
    ld [rROMB0], a
    ld hl, test_add_y
    ld a, b
    call .rowptr
    ld de, wXb
    ld bc, DIM
    call CopyBytes
    call AddSat_Stream
    pop bc
    pop de
    push bc
    ld hl, wX
    ld bc, DIM
    call CopyBytes                  ; de advances to the next row's slot
    pop bc
    inc b
    ld a, b
    cp TEST_ADD_ROWS
    jr nz, .row
    ret
.rowptr                             ; hl += a * DIM; clobbers de
    or a
    ret z
    ld de, DIM
:   add hl, de
    dec a
    jr nz, :-
    ret
ENDC
