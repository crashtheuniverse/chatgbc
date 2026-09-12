; Matvec3 - the ternary block-of-three table build, and the input-major
; kernel the dense w2 fallback still runs.
;
; A ternary weight is a coefficient in {-1, 0, +1}, and three of them name one
; of 27 signed sums of three activations. So the kernels build, per block of
; three inputs, the table of all 27 EXACT sums, and a weight byte then retires
; three multiply-accumulates per lookup. No product tables, no bank switch per
; input: the weights' bank stays mapped for the whole matvec.
;
; The 27 sums are a direct sum, {0,-x0,+x0} + {0,-x1,+x1} + {0,-x2,+x2}, so
; the table is built by derivation: entries 0..2 are (0, -x0, +x0); entries
; 3..5 are entries 0..2 minus x1 and 6..8 the same plus x1; entries 9..17 are
; entries 0..8 minus x2 and 18..26 plus x2. Every entry past the first three
; is one 16-bit add from an earlier one, read back through bc while hl
; writes forward, 12 cycles an entry. The code of a coefficient triple is
; d(c0) + 3 d(c1) + 9 d(c2) with d(0) = 0, d(-1) = 1, d(+1) = 2 - the
; exporter's block_codes(), which py/tests/test_sweep.py decodes back. The
; snake walk this replaces (26 delta reloads and six +-k words in HRAM) cost
; 636 cycles a block; this is 381.
;
; One routine serves both homes of a table: the 64-byte WRAM slots the sweep
; (src/sweep.asm) reads, and the HRAM table at hM3Tbl the input-major kernel
; below indexes with ldh. Both are plain addresses to `ld [hl+]` and
; `ld a, [bc]`; the only requirement is that the 54 bytes stay inside one
; 256-byte page, which a 64-byte-aligned slot and $FF80 both meet.
;
; Inputs not a multiple of three read past the end of the vector. The code for
; a pad position carries a zero coefficient - digit 0 - so it selects an entry
; that does not depend on that activation, and what lies past the vector is
; irrelevant. Matvec3_BuildAll builds the pad block as only the entries a
; digit-0 pad can reach: three for one real input, nine for two.
;
; Per block, counted (M-cycles): call 6; the three activations into HRAM
; 21; push de 4; bc = base 2; x0 into de 7; entries 0..2 = 20; x1 7; minus
; plane 3 x 12 = 36; c back to base 4; plus plane 36; x2 7; reset 4; minus
; plane 9 x 12 = 108; reset 4; plus plane 108; pop de 3; ret 4 = 381.
;
; Semantics: py/quant.py matvec_blocks(block=3, shift=0). The twin decides.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; The 27-entry table sits at the front of the shared HRAM region; the build's
; scratch sits behind it. All of it is ldh-reachable.
DEF hM3Tbl  EQU $FF00 + HLUT_BASE           ; 27 x 2 bytes
DEF hM3X    EQU hM3Tbl + 27 * 2             ; the block's three activations
DEF hM3Src  EQU hM3X + 3                    ; the input-major kernel's walk
DEF hM3Left EQU hM3Src + 2                  ; blocks remaining
DEF hM3Acc  EQU hM3Left + 1                 ; accumulator base, when not wAcc
; hM3Acc + 2 = $FF00 + HLUT_BASE + 62, inside the 96-byte region.

DEF M3_FULL EQU DIM / 3                     ; blocks with three real inputs
DEF M3_PAD  EQU DIM % 3                     ; real inputs in the pad block, if any
ASSERT M3_FULL + (M3_PAD > 0) == BLOCKS_DIM, "matvec3: BLOCKS_DIM is not DIM in threes"

SECTION "Matvec3 code", ROM0

; de = the activation at hM3X + \1, sign-extended.
MACRO M3_LOADX
    ldh a, [hM3X + \1]
    ld e, a
    add a, a
    sbc a, a
    ld d, a
ENDM

; Entries 0..2 at hl: (0, -de, +de). hl advances by 6.
MACRO M3_BASE
    xor a
    ld [hl+], a
    ld [hl+], a
    xor a
    sub e
    ld [hl+], a
    ld a, 0
    sbc a, d
    ld [hl+], a
    ld a, e
    ld [hl+], a
    ld a, d
    ld [hl+], a
ENDM

; \1 entries at hl = the \1 entries at bc minus de (\2 = 0) or plus de
; (\2 = 1); both pointers advance, 12 cycles an entry.
MACRO M3_PLANE
REPT \1
    ld a, [bc]
    IF \2
    add a, e
    ELSE
    sub e
    ENDC
    ld [hl+], a
    inc c
    ld a, [bc]
    IF \2
    adc a, d
    ELSE
    sbc a, d
    ENDC
    ld [hl+], a
    inc c
ENDR
ENDM

; c back to the table base after a plane of \1 entries.
MACRO M3_REWIND
    ld a, c
    sub \1 * 2
    ld c, a
ENDM

; Builds the 27-entry table at hl for the three activations at de. Each entry
; is the EXACT signed sum. The first version halved it with round-half-up to
; keep a 352-input row inside int16, and that rounding is a bias of +0.5 on
; every odd block - eleven units a row, enough to break a model that speaks
; in fp32. Rows are kept exact instead: 64 inputs is at most 8,128, and an
; expert's 176-input w2 is at most 22,352.
;   hl = table base (54 bytes inside one page), de -> the activations
;   returns hl = base + 54, de += 3; clobbers a, bc
Matvec3_Build::
    ld a, [de]
    inc de
    ldh [hM3X + 0], a
    ld a, [de]
    inc de
    ldh [hM3X + 1], a
    ld a, [de]
    inc de
    ldh [hM3X + 2], a
    push de
    ld b, h
    ld c, l                         ; bc reads the entries back, from 0
    M3_LOADX 0
    M3_BASE                         ; 0..2
    M3_LOADX 1
    M3_PLANE 3, 0                   ; 3..5 = 0..2 - x1
    M3_REWIND 3
    M3_PLANE 3, 1                   ; 6..8 = 0..2 + x1
    M3_LOADX 2
    M3_REWIND 3
    M3_PLANE 9, 0                   ; 9..17 = 0..8 - x2
    M3_REWIND 9
    M3_PLANE 9, 1                   ; 18..26 = 0..8 + x2
    pop de
    ret

IF M3_PAD == 1
; The pad block with one real input: digit 0 on both pad positions, so only
; entries 0..2 are ever read - (0, -x, +x), 26 cycles with the ret.
;   hl = table base, de -> the activation
Matvec3_BuildPad:
    ld a, [de]
    ld e, a
    add a, a
    sbc a, a
    ld d, a
    M3_BASE
    ret
ELIF M3_PAD == 2
; Two real inputs: entries 0..8, the x2 planes never read.
;   hl = table base, de -> the two activations
Matvec3_BuildPad:
    ld a, [de]
    inc de
    ldh [hM3X + 0], a
    ld a, [de]
    ldh [hM3X + 1], a
    ld b, h
    ld c, l
    M3_LOADX 0
    M3_BASE
    M3_LOADX 1
    M3_PLANE 3, 0
    M3_REWIND 3
    M3_PLANE 3, 1
    ret
ENDC

; Every block table of the DIM-wide vector at de into the sweep's WRAM slots
; (wMvTbl, src/sweep.asm): block k at slot k, 64 bytes each, four a page.
; Maps the slots' WRAM bank and leaves it mapped. Clobbers all.
;
; Per full block 381 + 17 of slot advance and count (ld a,l 1; add 2; ld l,a
; 1; jr nc 3 either way; ldh 3; dec 1; ldh 3; jr nz 3); the pad block 34
; with its jp; the entry 13 and the call 6. 22 blocks of a 64-wide vector =
; 21 x 398 + 34 + 19 = 8,411.
Matvec3_BuildAll::
    ld a, MV_TBL_BANK
    ldh [rSVBK], a
    ld hl, wMvTbl
    ld a, M3_FULL
    ldh [hM3Left], a
.block
    call Matvec3_Build              ; hl = slot + 54, de past the three
    ld a, l                         ; the next slot: 64 bytes on
    add a, 64 - 54
    ld l, a
    jr nc, :+
    inc h
:   ldh a, [hM3Left]
    dec a
    ldh [hM3Left], a
    jr nz, .block
IF M3_PAD
    jp Matvec3_BuildPad
ELSE
    ret
ENDC

; --- the input-major kernel: the dense w2 fallback -------------------------

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

; Every block: its table into HRAM, then one pass over the outputs. The
; build walks the activations three at a time; a block past the vector's
; end reads what follows it, which its zero coefficients ignore.
Matvec3_Blocks:
.block
    ldh a, [hM3Src + 0]
    ld e, a
    ldh a, [hM3Src + 1]
    ld d, a
    ld hl, hM3Tbl
    call Matvec3_Build
    ld a, e
    ldh [hM3Src + 0], a
    ld a, d
    ldh [hM3Src + 1], a
    ldh a, [hM3Acc + 0]
    ld l, a
    ldh a, [hM3Acc + 1]
    ld h, a
    call Matvec_AddRowHL            ; walks wMvWCur one block of codes forward
    ldh a, [hM3Left]
    dec a
    ldh [hM3Left], a
    jr nz, .block
    ret
