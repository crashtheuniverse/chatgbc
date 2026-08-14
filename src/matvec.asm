; Matvec4 - the kernel every other cost in this project is measured against.
;
;   acc[i] = sum over j of  (x[j] * codebook[w[j][i]] + MV_BIAS)
;
; Weights are 4-bit codebook indices stored input-major: for input j, MV_M
; contiguous bytes, one per output. Export pre-doubles each index so it can be
; used as a table offset with no shifting here.
;
; Three design points worth knowing before reading the inner loop:
;
; * The product table lives in HRAM. The loop needs three pointers -
;   accumulators, weights, table - and the SM83 has only hl/de/bc. `ldh a, [c]`
;   addresses HRAM with a single 8-bit register, which frees hl for the
;   accumulators and their `ld [hl+], a` auto-increment.
;
; * The table is biased by MV_BIAS so every entry is unsigned. A signed product
;   would have to be sign-extended into the third accumulator byte and there is
;   no register left to hold it; unsigned makes that byte a plain `adc a, 0`.
;   The result carries n * MV_BIAS, removed once per matvec, not once per MAC.
;
; * The carry chain runs straight through the fetch of the high byte. `inc c` is
;   an 8-bit increment, and on SM83 those touch Z/N/H but leave C alone, so the
;   carry out of the low add survives until the `adc` that needs it.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

DEF ACC_BYTES EQU 3                 ; int24 accumulators
DEF WEIGHT_BANK EQU 1

; Pinned: exported weight bytes are complete HRAM offsets into this table
; (index * 2 + HLUT_BASE), so the inner loop does no address arithmetic.
SECTION "Matvec HRAM", HRAM[$FF00 + HLUT_BASE]
hLut:: ds CB_LEVELS * 2             ; product table, unsigned 16-bit, low byte first

SECTION "Matvec state", WRAM0, ALIGN[4]
wAcc::      ds MV_M * ACC_BYTES
wX::        ds MV_N
wCodebook:: ds CB_LEVELS
wWeightPtr: dw                      ; walking pointer through the weight rows
wMulA:      db
wSkipLut:   db
wMulB:      db

SECTION "Matvec weights", ROMX, BANK[WEIGHT_BANK]
Weights: INCBIN "build/mv_weights.bin"

SECTION "Matvec data", ROM0
XData:  INCBIN "build/mv_x.bin"
CbData: INCBIN "build/mv_cb.bin"

SECTION "Matvec code", ROM0

; Copies the exported activation vector and codebook into WRAM.
Matvec_Load::
    ld hl, XData
    ld de, wX
    ld bc, MV_N
    call CopyBytes
    ld hl, CbData
    ld de, wCodebook
    ld bc, CB_LEVELS
    ; fall through

CopyBytes::
    ld a, [hl+]
    ld [de], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, CopyBytes
    ret

Matvec_Zero::
    ld hl, wAcc
    ld bc, MV_M * ACC_BYTES
.loop
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .loop
    ret

; Signed 8x8 -> 16, wMulA * wMulB into de. Plain shift-and-add over magnitudes
; with the sign applied at the end.
;
; This is the only real multiply left in the matvec path. It runs CB_LEVELS times
; per input and is amortized over MV_M outputs - which is precisely why the
; weights are 4-bit: an 8-bit codebook would need a 256-entry table here.
Mul8x8::
    ld a, [wMulA]
    ld c, 0                         ; c counts negative operands
    bit 7, a
    jr z, :+
    cpl
    inc a
    inc c
:   ld d, a                         ; d = |A|, the multiplier

    ld a, [wMulB]
    bit 7, a
    jr z, :+
    cpl
    inc a
    inc c
:   ld e, a
    push bc                         ; bc becomes the multiplicand, so save the sign count
    ld b, 0
    ld c, e                         ; bc = |B|

    ld hl, 0
    ld e, 8
.shift
    add hl, hl
    bit 7, d
    jr z, :+
    add hl, bc
:   sla d
    dec e
    jr nz, .shift

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
    ld [wMulB], a
    ld hl, wCodebook
    ld c, HLUT_BASE
    ld b, CB_LEVELS
.entry
    ld a, [hl+]
    ld [wMulA], a
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

; acc[i] += hLut[w[i]] for every output. 26 M-cycles per MAC.
Matvec_AddRow::
    ld hl, wAcc
    ld a, [wWeightPtr + 0]
    ld e, a
    ld a, [wWeightPtr + 1]
    ld d, a
    ld b, MV_M
.output
    ld a, [de]                      ; 2  weight index, pre-doubled by the exporter
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
    jr nz, .output                  ; 3
    ld a, e
    ld [wWeightPtr + 0], a
    ld a, d
    ld [wWeightPtr + 1], a
    ret

; The full matvec: MV_N inputs against MV_M outputs.
Matvec_Run::
    ld a, WEIGHT_BANK
    ld [rROMB0], a
    call Matvec_Zero
    ld a, LOW(Weights)
    ld [wWeightPtr + 0], a
    ld a, HIGH(Weights)
    ld [wWeightPtr + 1], a

    ld hl, wX
    ld b, MV_N
.input
    ld a, [hl+]
    push hl
    push bc
    ld c, a
    ld a, [wSkipLut]
    or a
    ld a, c
    call z, Matvec_BuildLut
    call Matvec_AddRow
    pop bc
    pop hl
    dec b
    jr nz, .input
    ret

; The same sweep with the table build skipped, so the two costs can be measured
; apart rather than inferred. The accumulators it leaves are meaningless.
Matvec_RunNoLut::
    ld a, 1
    ld [wSkipLut], a
    call Matvec_Run
    xor a
    ld [wSkipLut], a
    ret
