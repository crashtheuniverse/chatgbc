; Matvec4b - the one-bit block kernel.
;
; A one-bit weight is +1 or -1, so four of them applied to four activations
; is one of 16 signed sums. The kernel builds, per block of four inputs, the
; table of all 16 exact sums in HRAM, and the shipped inner body
; (Matvec_AddRowHL, byte for byte) then retires four multiply-accumulates
; per lookup. Measured on the lab bench (src/binbench.asm on neolab): 7.22
; cycles a MAC at 64 outputs, 5.48 at 176, against the ternary block
; kernel's 10.70 - and a weight costs one bit of ROM instead of 2.67.
;
; The table is walked in Gray-code order: entry 0 is (-1,-1,-1,-1), the
; empty positive set, and step p flips the coefficient of input ctz(p),
; which is one add of +-2k_i. Entry p therefore holds the signs given by
; gray(p) = p ^ (p >> 1), bit i set meaning +1 on input i - and the exporter
; writes, for each block and output, the position whose gray code is the
; row's sign pattern, already scaled to an HRAM offset. No decode happens
; here. py/twin5.py sums the same blocks in numpy with the same signs; the
; twin decides.
;
; Every width the model uses is a multiple of four (64, 96, 176, 256), so
; there is never a partial block and never a coefficient of zero to pad
; with - which a one-bit codebook could not express.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; The 16-entry table sits at the front of the shared HRAM region; the
; build's scratch behind it. 53 bytes, all ldh-reachable.
DEF hM4Tbl  EQU $FF00 + HLUT_BASE           ; 16 x 2 bytes
DEF hM4K    EQU hM4Tbl + 16 * 2             ; +2k0 .. +2k3, 16-bit
DEF hM4KN   EQU hM4K + 8                    ; -2k0 .. -2k3
DEF hM4Src  EQU hM4KN + 8                   ; the block's first activation
DEF hM4Left EQU hM4Src + 2                  ; blocks remaining
DEF hM4Acc  EQU hM4Left + 1                 ; accumulator base

SECTION "Matvec4b code", ROM0

; Sign-extends activation \1 of the block into de, DOUBLED: a Gray step
; flips a coefficient from -1 to +1 or back, which moves the sum by 2k.
; The offset add carries into h (the page-boundary lesson of matvec3).
MACRO M4_LOADK
    ldh a, [hM4Src + 0]
    ld l, a
    ldh a, [hM4Src + 1]
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
    sla e
    rl d
ENDM

; +de at hM4K + \1*2, -de at hM4KN + \1*2.
MACRO M4_STOREK
    ld a, e
    ldh [hM4K + \1 * 2], a
    ld a, d
    ldh [hM4K + \1 * 2 + 1], a
    xor a
    sub e
    ldh [hM4KN + \1 * 2], a
    ld a, 0
    sbc a, d
    ldh [hM4KN + \1 * 2 + 1], a
ENDM

; de = the delta word at hM4K + \1 (0,2,4,6 = +2k; 8,10,12,14 = -2k).
MACRO M4_LOADD
    ldh a, [hM4K + \1]
    ld e, a
    ldh a, [hM4K + \1 + 1]
    ld d, a
ENDM

MACRO M4_EMIT                       ; hl -> HRAM at c, c advances
    ld a, l
    ldh [c], a
    inc c
    ld a, h
    ldh [c], a
    inc c
ENDM

MACRO M4_STEP
    M4_LOADD \1
    add hl, de
    M4_EMIT
ENDM

DEF P0 EQU 0                        ; +2k0
DEF P1 EQU 2
DEF P2 EQU 4
DEF P3 EQU 6
DEF N0 EQU 8                        ; -2k0
DEF N1 EQU 10
DEF N2 EQU 12
DEF N3 EQU 14

; Builds the 16-entry table for the four activations at hM4Src. Entry 0 is
; -(k0+k1+k2+k3): half the sum of the negated doubled words, an arithmetic
; shift that is exact because the doubled sum is even. Then the Gray walk,
; p = 1..15: input ctz(p) flips, on if gray(p) has that bit, off otherwise.
Matvec4b_Build:
    M4_LOADK 0
    M4_STOREK 0
    M4_LOADK 1
    M4_STOREK 1
    M4_LOADK 2
    M4_STOREK 2
    M4_LOADK 3
    M4_STOREK 3
    ld hl, 0
    M4_LOADD N0
    add hl, de
    M4_LOADD N1
    add hl, de
    M4_LOADD N2
    add hl, de
    M4_LOADD N3
    add hl, de                      ; hl = -2(k0+k1+k2+k3)
    sra h
    rr l                            ; hl = -(k0+k1+k2+k3), entry 0
    ld c, LOW(hM4Tbl)
    M4_EMIT
    M4_STEP P0                      ; p=1  gray 0001: input 0 on
    M4_STEP P1                      ; p=2  gray 0011: input 1 on
    M4_STEP N0                      ; p=3  gray 0010: input 0 off
    M4_STEP P2                      ; p=4  gray 0110: input 2 on
    M4_STEP P0                      ; p=5  gray 0111: input 0 on
    M4_STEP N1                      ; p=6  gray 0101: input 1 off
    M4_STEP N0                      ; p=7  gray 0100: input 0 off
    M4_STEP P3                      ; p=8  gray 1100: input 3 on
    M4_STEP P0                      ; p=9  gray 1101: input 0 on
    M4_STEP P1                      ; p=10 gray 1111: input 1 on
    M4_STEP N0                      ; p=11 gray 1110: input 0 off
    M4_STEP N2                      ; p=12 gray 1010: input 2 off
    M4_STEP P0                      ; p=13 gray 1011: input 0 on
    M4_STEP N1                      ; p=14 gray 1001: input 1 off
    M4_STEP N0                      ; p=15 gray 1000: input 0 off
    ret

; The configured matvec on the one-bit block kernel. wMvIn holds the number
; of BLOCKS; the rest means what it means for the other kernels. Three entry
; points, as Matvec3's.
Matvec4b_Run::
    call Matvec_Zero
    jr Matvec4b_Body

Matvec4b_RunAccum::
    ; fall through

Matvec4b_Body:
    ld a, [wMvBank]
    ld [rROMB0], a
    ld a, [wMvW + 0]
    ld [wMvWCur + 0], a
    ld a, [wMvW + 1]
    ld [wMvWCur + 1], a
    ld a, [wMvXPtr + 0]
    ldh [hM4Src + 0], a
    ld a, [wMvXPtr + 1]
    ldh [hM4Src + 1], a
    ld a, [wMvIn]
    ldh [hM4Left], a
    ld a, LOW(wAcc)
    ldh [hM4Acc + 0], a
    ld a, HIGH(wAcc)
    ldh [hM4Acc + 1], a
    jr Matvec4b_Blocks

; As Matvec4b_RunAccum, into accumulators at hl instead of wAcc. The caller
; zeroes them.
Matvec4b_RunAccumHL::
    ld a, l
    ldh [hM4Acc + 0], a
    ld a, h
    ldh [hM4Acc + 1], a
    ld a, [wMvBank]
    ld [rROMB0], a
    ld a, [wMvW + 0]
    ld [wMvWCur + 0], a
    ld a, [wMvW + 1]
    ld [wMvWCur + 1], a
    ld a, [wMvXPtr + 0]
    ldh [hM4Src + 0], a
    ld a, [wMvXPtr + 1]
    ldh [hM4Src + 1], a
    ld a, [wMvIn]
    ldh [hM4Left], a
    ; fall through

Matvec4b_Blocks:
.block
    call Matvec4b_Build
    ldh a, [hM4Acc + 0]
    ld l, a
    ldh a, [hM4Acc + 1]
    ld h, a
    call Matvec_AddRowHL            ; walks wMvWCur one block of codes forward
    ldh a, [hM4Src + 0]
    add a, 4
    ldh [hM4Src + 0], a
    jr nc, :+
    ldh a, [hM4Src + 1]
    inc a
    ldh [hM4Src + 1], a
:   ldh a, [hM4Left]
    dec a
    ldh [hM4Left], a
    jr nz, .block
    ret
