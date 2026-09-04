; Matvec3 - the ternary block kernel.
;
; A ternary weight is a coefficient in {-1, 0, +1}, and three of them name one
; of 27 signed sums of three activations. So the kernel builds, per block of
; three inputs, the table of all 27 exact sums, and the shipped inner body
; (Matvec_AddRow, byte for byte) then retires three multiply-accumulates per
; lookup. No product tables, no
; bank switch per input: the weights' bank stays mapped for the whole matvec.
;
; The table is walked incrementally, the way src/blockbench.asm measured it:
; entry 0 is (-1,-1,-1), and each of the 26 steps changes one coefficient by
; one, which is adding a precomputed +-k. The walk order defines the codes
; the exporter writes; py/tests/test_blockbench.py is the specification.
;
; Inputs not a multiple of three read past the end of the vector. The code for
; a pad position carries a zero coefficient, which selects an entry that does
; not depend on that activation - so what lies past the vector is irrelevant.
;
; Semantics: py/quant.py matvec_blocks(block=3, shift=0). The twin decides.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; The 27-entry table sits at the front of the shared HRAM region; the build's
; scratch sits behind it. All of it is ldh-reachable.
DEF hM3Tbl  EQU $FF00 + HLUT_BASE           ; 27 x 2 bytes
DEF hM3K    EQU hM3Tbl + 27 * 2             ; +k0 +k1 +k2, 16-bit
DEF hM3KN   EQU hM3K + 6                    ; -k0 -k1 -k2
DEF hM3Src  EQU hM3KN + 6                   ; the block's first activation
DEF hM3Left EQU hM3Src + 2                  ; blocks remaining
DEF hM3Acc  EQU hM3Left + 1                 ; accumulator base, when not wAcc
; hM3Acc + 2 = $FF00 + HLUT_BASE + 71, inside the 96-byte region.

SECTION "Matvec3 code", ROM0

; Sign-extends activation \1 of the block into de.
;
; The offset add carries into h. An earlier version added into l alone, and
; a block whose three activations straddled a 256-byte page read its third
; from the page below - silently, and only in the memory layout of a model
; whose buffers happened to put a boundary there. One layout shipped clean;
; the next dropped one input of one block and lost the golden by a hair.
MACRO M3_LOADK
    ldh a, [hM3Src + 0]
    ld l, a
    ldh a, [hM3Src + 1]
    ld h, a
    IF \1 > 0
        ld a, l
        add a, \1
        ld l, a
        ld a, h
        adc a, 0
        ld h, a
    ENDC
    ld a, [hl]
    ld e, a
    add a, a
    sbc a, a
    ld d, a
ENDM

; +de at hM3K + \1*2, -de at hM3KN + \1*2.
MACRO M3_STOREK
    ld a, e
    ldh [hM3K + \1 * 2], a
    ld a, d
    ldh [hM3K + \1 * 2 + 1], a
    xor a
    sub e
    ldh [hM3KN + \1 * 2], a
    ld a, 0
    sbc a, d
    ldh [hM3KN + \1 * 2 + 1], a
ENDM

; de = the delta word at hM3K + \1 (0,2,4 = +k; 6,8,10 = -k).
MACRO M3_LOADD
    ldh a, [hM3K + \1]
    ld e, a
    ldh a, [hM3K + \1 + 1]
    ld d, a
ENDM

MACRO M3_EMIT                       ; hl -> HRAM at c, c advances
    ld a, l
    ldh [c], a
    inc c
    ld a, h
    ldh [c], a
    inc c
ENDM

MACRO M3_STEP
    M3_LOADD \1
    add hl, de
    M3_EMIT
ENDM

DEF P0 EQU 0                        ; +k0
DEF P1 EQU 2                        ; +k1
DEF P2 EQU 4                        ; +k2
DEF N0 EQU 6                        ; -k0
DEF N1 EQU 8                        ; -k1
DEF N2 EQU 10                       ; -k2

; Builds the 27-entry table for the three activations at hM3Src. Each entry
; is the EXACT signed sum. The first version halved it with round-half-up to
; keep a 352-input row inside int16, and that rounding is a bias of +0.5 on
; every odd block - eleven units a row, enough to break a model that speaks
; in fp32. Rows are kept exact instead: 64 inputs is at most 8,128, and w2
; runs as two halves of 59 blocks.
Matvec3_Build:
    M3_LOADK 0
    M3_STOREK 0
    M3_LOADK 1
    M3_STOREK 1
    M3_LOADK 2
    M3_STOREK 2
    ld hl, 0
    M3_LOADD N0
    add hl, de
    M3_LOADD N1
    add hl, de
    M3_LOADD N2
    add hl, de                      ; hl = -k0-k1-k2, entry 0
    ld c, LOW(hM3Tbl)
    M3_EMIT
    ; c2 = -1 plane
    M3_STEP P0
    M3_STEP P0
    M3_STEP P1
    M3_STEP N0
    M3_STEP N0
    M3_STEP P1
    M3_STEP P0
    M3_STEP P0
    M3_STEP P2                     ; c2 -> 0
    ; c2 = 0 plane, reversed
    M3_STEP N0
    M3_STEP N0
    M3_STEP N1
    M3_STEP P0
    M3_STEP P0
    M3_STEP N1
    M3_STEP N0
    M3_STEP N0
    M3_STEP P2                     ; c2 -> +1
    ; c2 = +1 plane
    M3_STEP P0
    M3_STEP P0
    M3_STEP P1
    M3_STEP N0
    M3_STEP N0
    M3_STEP P1
    M3_STEP P0
    M3_STEP P0
    ret

; The configured matvec on the block kernel. wMvIn holds the number of BLOCKS;
; wMvOut, wMvGroups, wMvW, wMvBank and wMvXPtr mean what they mean for the
; 4-bit kernel. Two entry points, as Matvec_Run / Matvec_RunAccum.
Matvec3_Run::
    call Matvec_Zero
    jr Matvec3_Body

Matvec3_RunAccum::
    ; fall through

Matvec3_Body:
    ld a, [wMvBank]
    ld [rROMB0], a
    ld a, [wMvW + 0]
    ld [wMvWCur + 0], a
    ld a, [wMvW + 1]
    ld [wMvWCur + 1], a
    ld a, [wMvXPtr + 0]
    ldh [hM3Src + 0], a
    ld a, [wMvXPtr + 1]
    ldh [hM3Src + 1], a
    ld a, [wMvIn]
    ldh [hM3Left], a
    ld a, LOW(wAcc)
    ldh [hM3Acc + 0], a
    ld a, HIGH(wAcc)
    ldh [hM3Acc + 1], a
    jr Matvec3_Blocks

; As Matvec3_RunAccum, into accumulators at hl instead of wAcc - the ternary
; classifier keeps its 512 in a WRAM bank. The caller zeroes them.
Matvec3_RunAccumHL::
    ld a, l
    ldh [hM3Acc + 0], a
    ld a, h
    ldh [hM3Acc + 1], a
    ld a, [wMvBank]
    ld [rROMB0], a
    ld a, [wMvW + 0]
    ld [wMvWCur + 0], a
    ld a, [wMvW + 1]
    ld [wMvWCur + 1], a
    ld a, [wMvXPtr + 0]
    ldh [hM3Src + 0], a
    ld a, [wMvXPtr + 1]
    ldh [hM3Src + 1], a
    ld a, [wMvIn]
    ldh [hM3Left], a
    ; fall through

Matvec3_Blocks:
.block
    call Matvec3_Build
    ldh a, [hM3Acc + 0]
    ld l, a
    ldh a, [hM3Acc + 1]
    ld h, a
    call Matvec_AddRowHL            ; walks wMvWCur one block of codes forward
    ldh a, [hM3Src + 0]
    add a, 3
    ldh [hM3Src + 0], a
    jr nc, :+
    ldh a, [hM3Src + 1]
    inc a
    ldh [hM3Src + 1], a
:   ldh a, [hM3Left]
    dec a
    ldh [hM3Left], a
    jr nz, .block
    ret
