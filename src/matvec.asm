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
; * The table is biased so entries are unsigned. A signed product would need
;   sign extension into the third accumulator byte and there is no register left
;   to hold it; unsigned makes that byte a plain `adc a, 0`. The result carries
;   nIn * MV_BIAS, removed once per matvec by Requant rather than once per MAC.
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
wMvFull::   db                      ; the same count as 256-blocks ...
wMvRem::    db                      ; ... plus remainder, so the inner loop can
                                    ; use an 8-bit counter and leave c free
wMvXPtr::   dw                      ; input activation vector
wMvCb::     dw                      ; codebook (16 int8 values)


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

; Splits wMvOut into whole 256-blocks plus a remainder, so Matvec_Chunk can
; count with b alone and leave c free for the HRAM table index.
Matvec_SetOut::
    ld a, l
    ld [wMvOut + 0], a
    ld [wMvRem], a
    ld a, h
    ld [wMvOut + 1], a
    ld [wMvFull], a
    ret

Matvec_Zero::
    ld a, [wMvOut + 0]
    ld l, a
    ld a, [wMvOut + 1]
    ld h, a
    ld d, h
    ld e, l
    add hl, de
    add hl, de                      ; hl = outputs * ACC_BYTES
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

; Signed 8x8 -> 16, wMulA * wMulB into de. Shift-and-add over magnitudes with
; the sign applied at the end.
;
; This is the only real multiply left in the matvec path. It runs CB_LEVELS
; times per input and is amortized over the outputs - which is exactly why the
; weights are 4-bit. It is also the single biggest remaining cost in the whole
; model (measured at ~202 cycles per table entry), and Phase 3's first target.
Mul8x8::
    ld a, [wMulA8]
    ld c, 0                         ; counts negative operands
    bit 7, a
    jr z, :+
    cpl
    inc a
    inc c
:   ld d, a                         ; |A|, the multiplier

    ld a, [wMulB8]
    bit 7, a
    jr z, :+
    cpl
    inc a
    inc c
:   ld e, a
    push bc                         ; bc becomes the multiplicand; save the sign count
    ld b, 0
    ld c, e

    ld hl, 0
REPT 8
    add hl, hl
    sla d
    jr nc, :+
    add hl, bc
:
ENDR

    pop bc
    bit 0, c                        ; exactly one negative operand -> negate
    jr z, .done
    xor a
    sub a, l
    ld l, a
    ld a, 0
    sbc a, h
    ld h, a
.done
    ld d, h
    ld e, l
    ret

; Builds hLut for the activation in a: entry u = a * codebook[u] + MV_BIAS.
Matvec_BuildLut::
    ld [wMulB8], a
    ld a, [wMvCb + 0]
    ld l, a
    ld a, [wMvCb + 1]
    ld h, a
    ld c, HLUT_BASE
    ld b, CB_LEVELS
.entry
    ld a, [hl+]
    ld [wMulA8], a
    push hl
    push bc
    call Mul8x8
    pop bc
    pop hl

    ld a, e
    add a, LOW(MV_BIAS)
    ldh [c], a
    inc c
    ld a, d
    adc a, HIGH(MV_BIAS)
    ldh [c], a
    inc c

    dec b
    jr nz, .entry
    ret

; hl = accumulators, de = weights, b = outputs this chunk (0 means 256).
; 26 M-cycles per MAC.
Matvec_Chunk:
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
    ld a, [hl]                      ; 2
    adc a, 0                        ; 2  unsigned products, so no sign extension
    ld [hl+], a                     ; 2
    dec b                           ; 1
    jr nz, Matvec_Chunk             ; 3
    ret

; One pass over every output for a single input.
Matvec_AddRow:
    ld hl, wAcc
    ld a, [wMvWCur + 0]
    ld e, a
    ld a, [wMvWCur + 1]
    ld d, a

    ld a, [wMvFull]
    or a
    jr z, .remainder
    ld c, a
.block
    push bc
    ld b, 0                         ; 0 counts as 256
    call Matvec_Chunk
    pop bc
    dec c
    jr nz, .block
.remainder
    ld a, [wMvRem]
    or a
    jr z, .save
    ld b, a
    call Matvec_Chunk
.save
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
