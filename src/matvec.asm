; Matvec4 - the kernel every other cost in this project is measured against.
;
;   acc[i] = sum over j of  (x[j] * codebook[w[j][i]] + MV_BIAS)
;
; Weights are 4-bit codebook indices stored input-major: for input j, nOut
; contiguous bytes, one per output. Export turns each index into a complete HRAM
; offset (index * 2 + HLUT_BASE) so the inner loop does no address arithmetic.
;
; Three SM83 details make the inner loop work:
;
; * The product table lives in HRAM. The loop needs three pointers -
;   accumulators, weights, table - and there are only hl/de/bc. `ldh a, [c]`
;   reaches HRAM with one 8-bit register, freeing hl for the accumulators and
;   their `ld [hl+], a` auto-increment.
;
; * Table entries are signed and pre-halved, so the accumulator fits signed
;   16-bit and there is no third byte and no bias to unwind. Two's-complement
;   add works identically for signed and unsigned, so the loop is unchanged
;   apart from being shorter.
;
; * The carry from the low add survives the high-byte fetch, because `inc c` is
;   an 8-bit increment and those leave C alone on SM83.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; Pinned so exported weight bytes are complete HRAM offsets into this table.
SECTION "Matvec HRAM", HRAM[$FF00 + HLUT_BASE]
hLut:: ds CB_LEVELS * 2             ; unsigned 16-bit products, low byte first

SECTION "Matvec state", WRAM0
wMvW::      dw                      ; weight base, set once per matvec
wMvWCur:    dw                      ; working copy that walks forward through the rows
wMvBank::   db                      ; ROM bank holding those weights
wMvIn::     db                      ; number of inputs
wMvOut::    dw                      ; number of outputs
wMvGroups:: db                      ; the same count in groups of four
wMvXPtr::   dw                      ; input activation vector
wMvLutBank:: db                     ; ROM bank of this matrix's product tables
wMvLutAddr:: dw                     ; base of the 256 precomputed tables


SECTION "Matvec code", ROM0

; hl = source, de = dest, bc = count.
CopyBytes::
    ld a, [hl+]
    ld [de], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, CopyBytes
    ret

; hl = number of outputs. The inner loop runs four outputs per iteration, so it
; counts groups of four - and every count the model uses (32, 64, 172, 512) is a
; multiple of four, which also keeps the group count inside a single 8-bit
; register and leaves c free for the HRAM table index.
Matvec_SetOut::
    ld a, l
    ld [wMvOut + 0], a
    ld a, h
    ld [wMvOut + 1], a
    srl h
    rr l
    srl h
    rr l                            ; hl = outputs / 4
    ld a, l
    ld [wMvGroups], a
    ret

Matvec_Zero::
    ld a, [wMvOut + 0]
    ld l, a
    ld a, [wMvOut + 1]
    ld h, a
    add hl, hl                      ; hl = outputs * ACC_BYTES
    ld b, h
    ld c, l
    ld hl, wAcc
.loop
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .loop
    ret

; Loads hLut with the product table for the activation in a.
;
; Every table this could ever need is already in ROM - the operands are the
; activation and the matrix's codebook, both known at export time - so this is a
; 32-byte copy instead of sixteen shift-add multiplies. That trade is the whole
; point: ROM is abundant here and cycles are not. ~190 cycles against ~3,200.
Matvec_BuildLut::
    add a, 128                      ; signed activation -> unsigned table index
    ld l, a
    ld h, 0
REPT 5
    add hl, hl                      ; * CB_LEVELS * 2 bytes per table
ENDR
    ld a, [wMvLutAddr + 0]
    ld e, a
    ld a, [wMvLutAddr + 1]
    ld d, a
    add hl, de

    ld a, [wMvLutBank]
    ld [rROMB0], a
    ld c, HLUT_BASE
REPT CB_LEVELS * 2
    ld a, [hl+]
    ldh [c], a
    inc c
ENDR
    ld a, [wMvBank]                 ; back to the weights
    ld [rROMB0], a
    ret

; One pass over every output for a single input: acc[i] += hLut[w[i]].
;
; 19 M-cycles per MAC. Four outputs per iteration so `dec b` / `jr nz` costs one
; cycle per MAC instead of four; every output count in the model is a multiple
; of four, so no remainder path is needed.
Matvec_AddRow:
    ld hl, wAcc
    ld a, [wMvWCur + 0]
    ld e, a
    ld a, [wMvWCur + 1]
    ld d, a
    ld a, [wMvGroups]
    ld b, a
.group
REPT 4
    ld a, [de]                      ; 2  weight index, already an HRAM offset
    inc de                          ; 2
    ld c, a                         ; 1
    ldh a, [c]                      ; 2  product low byte
    add a, [hl]                     ; 2
    ld [hl+], a                     ; 2
    inc c                           ; 1  8-bit inc: leaves carry intact
    ldh a, [c]                      ; 2  product high byte
    adc a, [hl]                     ; 2
    ld [hl+], a                     ; 2
ENDR
    dec b                           ; 1
    jr nz, .group                   ; 3

    ld a, e
    ld [wMvWCur + 0], a
    ld a, d
    ld [wMvWCur + 1], a
    ret

; Runs the configured matvec, leaving biased int24 accumulators in wAcc.
;
; Two entry points rather than a mode flag. A flag would be persistent state
; that is read before anything writes it, and WRAM boots to garbage on real
; hardware - accumulators would then never be cleared and every matvec would
; pile onto the last one.
Matvec_Run::
    call Matvec_Zero
    jr Matvec_Body

; Continues accumulating into whatever wAcc already holds. Used to carry a
; matvec across a ROM bank boundary, where one group of inputs ends and the
; next continues into the same accumulators.
Matvec_RunAccum::
    ; fall through

Matvec_Body:
    ld a, [wMvBank]
    ld [rROMB0], a
    ld a, [wMvW + 0]
    ld [wMvWCur + 0], a
    ld a, [wMvW + 1]
    ld [wMvWCur + 1], a

    ld a, [wMvXPtr + 0]
    ld l, a
    ld a, [wMvXPtr + 1]
    ld h, a
    ld a, [wMvIn]
    ld b, a
.input
    ld a, [hl+]
    push hl
    push bc
    call Matvec_BuildLut
    call Matvec_AddRow
    pop bc
    pop hl
    dec b
    jr nz, .input
    ret
