; The sparse w2 kernel: only the pairs that are nonzero.
;
; w2's input u is 82% zero and its ternary weights are 34-40% zero, so of the
; 11,264 multiply-accumulates in the dense matvec about 1,240 a layer are
; between two nonzeros. src/relu2.asm records which u are nonzero as it makes
; them, and the exporter stores w2 by INPUT column as two lists of output
; offsets - the +1 set, then the -1 set, one byte each, 2*o being the low
; address byte of output o's accumulator (py/export5.py sparse_column_blob).
; This kernel zeroes the 64 accumulators and, for each listed (i, u), adds
; the 16-bit value (0:u) at every + offset and subtracts it at every - one.
;
; Exact: each accumulator is the integer sum of the same terms the dense
; block kernel adds, in a different order, and integer addition commutes -
; the twin's matvec_blocks result reaches Requant_All16 either way. u is
; non-negative (ReLU^2 output), so (0:u) is its int16, and the high byte
; moves only on the low byte's carry (or borrow), which is the rare path.
;
; Counted (M-cycles), per pair on the + list:
;   ld a, [hl+]     2   2*o
;   ld e, a         1
;   ld a, [de]      2   accumulator, low byte
;   add a, c        1
;   ld [de], a      2
;   jr nc, .noc     3   (2 when the carry falls through)
;   inc e           1
;   ld a, [de]      2   accumulator, high byte
;   inc a           1
;   ld [de], a      2
;   = 11 without a carry, 16 with; the - list is the same with sub / dec.
; Two pairs a loop turn, so `dec b; jr nz` is 2 a pair. Per listed (i, u):
; 38 to reach its column, ~15 of list control for each of its two lists,
; 6 back to the list: ~74. Zeroing 128 bytes: 16 stores a turn, 293 with
; its setup. Setup from the manifest: 46 with the call. Measured, 8-token
; census: 67,632 a token for the three layers against the block kernel's
; 344,696 on the same tree (data-dependent: the pairs per token vary by a
; factor of ten story to story).
;
; Guard: W2_Run (src/forward.asm) runs the dense block kernel instead when
; wSpCount exceeds W2_SPARSE_MAX, which the exporter derives from these
; counts, the model's fullest column and the dense kernel's own counted
; listing (src/matvec3.asm, src/matvec.asm) - never from a census figure.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

ASSERT (DIM * 2) % 16 == 0, "matvec_sparse: the zero loop clears 16 bytes a turn"
ASSERT DIM * 2 <= 256, "matvec_sparse: the accumulators must stay in wAcc's page"
; A list byte is 2*o and nothing else - the kernel loads it straight into e
; with d = HIGH(wAcc) - so accumulator o must sit at LOW(wAcc) + 2*o = 2*o.
; state.asm aligns the section; the exporter writes the lists on the same
; assumption (sparse_column_blob, acc_low = 0).
ASSERT LOW(wAcc) == 0, "matvec_sparse: wAcc must start its page - the list bytes are 2*o alone"

SECTION "Sparse HRAM", HRAM
hSpBase: dw                         ; the routed expert's column table

SECTION "Sparse kernel", ROM0

; acc[o] += (0:u) at 2*o for each listed offset; the carry lifts the high byte.
MACRO SP_ADD
    ld a, [hl+]
    ld e, a
    ld a, [de]
    add a, c
    ld [de], a
    jr nc, .noc\@
    inc e
    ld a, [de]
    inc a
    ld [de], a
.noc\@
ENDM

; acc[o] -= (0:u) likewise; the borrow drops the high byte.
MACRO SP_SUB
    ld a, [hl+]
    ld e, a
    ld a, [de]
    sub c
    ld [de], a
    jr nc, .nob\@
    inc e
    ld a, [de]
    dec a
    ld [de], a
.nob\@
ENDM

; One list: its count byte at hl, then that many offsets. Two pairs a turn;
; an odd count does its first pair before the loop.
MACRO SP_LIST                       ; \1 = the pair macro, \2 = a label stem
    ld a, [hl+]
    srl a
    ld b, a
    jr nc, .even\2
    \1
.even\2
    inc b
    jr .test\2
.loop\2
    \1
    \1
.test\2
    dec b
    jr nz, .loop\2
ENDM

; wAcc = w2 of the matrix indexed by a (layer * EXPERTS + expert) over the
; u listed in wSpList. Leaves the column blob's bank mapped.
MatvecSparse_Run::
    ld c, a
    ld b, 0
    ld hl, w2s_banks
    add hl, bc
    ld a, [hl]
    ld [rROMB0], a
    ld hl, w2s_addrs
    add hl, bc
    add hl, bc
    ld a, [hl+]
    ldh [hSpBase + 0], a
    ld a, [hl]
    ldh [hSpBase + 1], a

    xor a                           ; the DIM int16 accumulators, zeroed
    ld hl, wAcc
    ld b, DIM * 2 / 16
.zero
REPT 16
    ld [hl+], a
ENDR
    dec b
    jr nz, .zero

    ld hl, wSpList
.column
    ld a, [hl+]                     ; i, or the sentinel
    cp $FF
    ret z
    ld e, a
    ld a, [hl+]                     ; u
    ld c, a
    push hl                         ; the list walk, back after the column
    ld d, 0
    ldh a, [hSpBase + 0]
    ld l, a
    ldh a, [hSpBase + 1]
    ld h, a
    add hl, de
    add hl, de                      ; hl -> the column's table entry
    ld a, [hl+]
    ld e, a
    ld a, [hl]
    ld d, a
    add hl, de                      ; entry-relative offset -> the column
    ld d, HIGH(wAcc)
    SP_LIST SP_ADD, P
    SP_LIST SP_SUB, N
    pop hl
    jr .column
