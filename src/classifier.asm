; The classifier, output-major: argmax with nothing stored.
;
; Greedy decode needs one number - which logit is largest - and the old path
; paid for far more than that: 512 running sums zeroed, accumulated in WRAM
; with a read-modify-write on every MAC, then re-scanned through a shift
; machinery whose shift table is 512 zeros. All of it existed because the
; kernel was input-major, the order that amortizes one HRAM product-table
; build over every output.
;
; Output-major inverts the trade. Build all 64 input tables first - 4 KB, one
; WRAM bank, the same bytes the old path copied to HRAM piecemeal - and each
; output's dot product then lives its whole life in a register pair: summed,
; compared against the best so far, forgotten. No accumulator array, no
; zeroing pass, no scan.
;
; The exported weight bytes do all the addressing. Each is the complete low
; byte of its entry's address - the input's table base (j * 64) is folded in
; at export - and the high byte advances every four inputs, carried in b.
; The raw sums are directly comparable because the 8-bit classifier has one
; scale for every row; export asserts that, so a future per-row-scaled
; classifier fails loudly there instead of decoding garbage here.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; One WRAM bank holds every input's product table: input j's hi-nibble table
; at wClsTbl + j*64, its lo-nibble table 32 bytes above. v0.5 has no KV cache,
; so every switchable bank is free; 7 is kept for continuity with v0.4, where
; claiming a KV bank by mistake once cost an afternoon.
DEF CLS_TBL_BANK EQU 7
SECTION "Cls tables", WRAMX[$D000], BANK[CLS_TBL_BANK]
wClsTbl:: ds 4096

SECTION "Cls state", WRAM0
wClsBest:  dw                       ; best logit so far, high byte sign-flipped
wClsIdx:   dw                       ; token index of the output being summed

SECTION "Cls HRAM", HRAM
hClsOut:   db                       ; outputs left in the part
hClsPart:  db                       ; the part being accumulated (ternary)
hClsSrc:   dw                       ; one-bit: the block's first activation
hClsBlk:   db                       ; one-bit: the block being built
hClsGrp:   db                       ; 8-input groups left in the output

SECTION "Cls code", ROM0

IF CLS_TERNARY || CLS_BINARY

DEF wClsPlaneLo EQU wClsTbl + 2048          ; $D800, page-aligned
DEF wClsPlaneHi EQU wClsTbl + 2048 + 256    ; $D900

; One block's planes against CLS_OUTPUTS_PER_PART outputs: de = the weight
; stream, hl = the sums. b is the plane page, c the code; sixteen unrolled
; then a count, which costs a couple of percent against a full unroll and
; a kilobyte of ROM0 less.
Cls8_Rows:
    ld a, CLS_OUTPUTS_PER_PART / 16
    ldh [hClsOut], a
.chunk
    ld b, HIGH(wClsPlaneLo)
REPT 16
    ld a, [de]                      ; 2  the sign pattern
    inc de                          ; 2
    ld c, a                         ; 1
    ld a, [bc]                      ; 2  low plane
    add a, [hl]                     ; 2
    ld [hl+], a                     ; 2
    inc b                           ; 1
    ld a, [bc]                      ; 2  high plane
    adc a, [hl]                     ; 2
    ld [hl+], a                     ; 2
    dec b                           ; 1
ENDR
    ldh a, [hClsOut]
    dec a
    ldh [hClsOut], a
    jp nz, .chunk                   ; the unrolled body is past jr's reach
    ret

IF CLS_BINARY


; --- the one-bit classifier -------------------------------------------------
;
; Blocks of eight inputs against a 256-entry table of exact +-1 sums, held as
; two page-aligned planes in the sum bank so the weight byte IS the index:
; 3.08 cycles a MAC at 1024 outputs on the lab bench. The table is built by
; doubling in natural order - entry 0 is -(x0+..+x7), and every entry with
; bit k set is the entry without it plus 2x_k - so the exporter's code is
; the row's sign pattern itself, bit i set for +1 on input i. Blocks are
; the outer loop: a table is built once and serves every part.
; de = 2 * activation \1 of the block at hClsSrc, sign-extended.
MACRO CLS8_LOADK
    ldh a, [hClsSrc + 0]
    ld l, a
    ldh a, [hClsSrc + 1]
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

; Entries 2^k .. 2^(k+1)-1 = entries 0 .. 2^k-1 plus de. b:c reads, h:l
; writes, both on the low plane; the high plane is one page up.
MACRO CLS8_DOUBLE
    ld c, 0
    ld b, HIGH(wClsPlaneLo)
    ld h, b
    ld l, 1 << \1
.d\@
    ld a, [bc]
    add a, e
    ld [hl], a
    inc b
    inc h
    ld a, [bc]
    adc a, d
    ld [hl], a
    dec b
    dec h
    inc c
    inc l
    ld a, c
    cp 1 << \1
    jr nz, .d\@
ENDM

; Builds the planes for the eight activations at hl.
Cls8_Build:
    ld a, l
    ldh [hClsSrc + 0], a
    ld a, h
    ldh [hClsSrc + 1], a
    ld de, 0                        ; entry 0: minus the sum of the eight
    ld b, 8
.sum
    ld a, [hl+]
    ld c, a
    add a, a
    sbc a, a                        ; a = sign extension
    push hl
    ld h, a
    ld l, c                         ; hl = sign-extended activation
    add hl, de
    ld d, h
    ld e, l
    pop hl
    dec b
    jr nz, .sum
    xor a
    sub e
    ld [wClsPlaneLo], a
    ld a, 0
    sbc a, d
    ld [wClsPlaneHi], a
    CLS8_LOADK 0
    CLS8_DOUBLE 0
    CLS8_LOADK 1
    CLS8_DOUBLE 1
    CLS8_LOADK 2
    CLS8_DOUBLE 2
    CLS8_LOADK 3
    CLS8_DOUBLE 3
    CLS8_LOADK 4
    CLS8_DOUBLE 4
    CLS8_LOADK 5
    CLS8_DOUBLE 5
    CLS8_LOADK 6
    CLS8_DOUBLE 6
    CLS8_LOADK 7
    CLS8_DOUBLE 7
    ret

Cls_BuildTables::
    ld a, CLS_TBL_BANK
    ldh [rSVBK], a
    ld hl, wClsTbl
    ld bc, VOCAB * 2
.zero
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .zero

    xor a
    ldh [hClsBlk], a
.block
    ldh a, [hClsBlk]                ; hl = wXb + block * 8
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    add hl, hl
    ld de, wXb
    add hl, de
    call Cls8_Build
    xor a
    ldh [hClsPart], a
.part
    ldh a, [hClsPart]
    ld c, a
    ld b, 0
    ld hl, cls_banks
    add hl, bc
    ld a, [hl]
    ld [rROMB0], a
    ld hl, cls_addrs
    add hl, bc
    add hl, bc                      ; word entries
    ld a, [hl+]
    ld e, a
    ld a, [hl]
    ld d, a                         ; de = the part's codes
    ldh a, [hClsBlk]                ; + block * CLS_OUTPUTS_PER_PART bytes
    add a, a                        ; (512 a block: two pages)
    add a, d
    ld d, a
    ld hl, wClsTbl                  ; + part * CLS_OUTPUTS_PER_PART * 2
    ldh a, [hClsPart]
    or a
    jr z, .go
    ld a, HIGH(CLS_OUTPUTS_PER_PART * 2)
.advance
    add a, h
    ld h, a
    ldh a, [hClsPart]
    dec a
    jr z, .go
    ld a, HIGH(CLS_OUTPUTS_PER_PART * 2)
    jr .advance
.go
    call Cls8_Rows
    ldh a, [hClsPart]
    inc a
    ldh [hClsPart], a
    cp CLS_PARTS
    jr nz, .part
    ldh a, [hClsBlk]
    inc a
    ldh [hClsBlk], a
    cp CLS_BLOCKS8
    jr nz, .block
    ret

ELSE

; --- the ternary classifier, on planes -------------------------------------
;
; The same planes as the one-bit classifier, filled with the 243 sums a block
; of FIVE ternary inputs can produce (3^5 fits a byte of code), built by
; tripling in mixed-radix order: entry 0 is minus the sum of the five (every
; coefficient -1), and for input k the entries with digit k = 1 are the
; entries with digit 0 plus x_k, digit 2 plus 2x_k. The exporter's code is
; the digit string sum((c_i + 1) * 3^i), 0..242. A block past the end of the
; vector carries digit 1 (coefficient zero) for the inputs that are not
; there, so whatever lies past wXb never reaches a sum. Same rows as the
; one-bit classifier, five MACs a lookup instead of eight, no quality lost
; to a one-bit tied embedding.

; de = activation \1 of the block at hClsSrc, sign-extended (not doubled).
MACRO CLS5_LOADK
    ldh a, [hClsSrc + 0]
    ld l, a
    ldh a, [hClsSrc + 1]
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

; Entries \2 .. \2 + \1 - 1 = entries 0 .. \1 - 1 plus de. b:c reads, h:l
; writes, low plane; the high plane is one page up.
MACRO CLS5_SPREAD
    ld c, 0
    ld b, HIGH(wClsPlaneLo)
    ld h, b
    ld l, \2
.s\@
    ld a, [bc]
    add a, e
    ld [hl], a
    inc b
    inc h
    ld a, [bc]
    adc a, d
    ld [hl], a
    dec b
    dec h
    inc c
    inc l
    ld a, c
    cp \1
    jr nz, .s\@
ENDM

; Digit k: the entries with digit 1 (+x_k) and digit 2 (+2x_k), from the
; entries with digit 0. \1 = 3^k.
MACRO CLS5_TRIPLE
    CLS5_SPREAD \1, \1
    sla e
    rl d
    CLS5_SPREAD \1, 2 * \1
ENDM

; Builds the planes for the five activations at hl.
Cls5_Build:
    ld a, l
    ldh [hClsSrc + 0], a
    ld a, h
    ldh [hClsSrc + 1], a
    ld de, 0                        ; entry 0: minus the sum of the five
    ld b, 5
.sum
    ld a, [hl+]
    ld c, a
    add a, a
    sbc a, a
    push hl
    ld h, a
    ld l, c
    add hl, de
    ld d, h
    ld e, l
    pop hl
    dec b
    jr nz, .sum
    xor a
    sub e
    ld [wClsPlaneLo], a
    ld a, 0
    sbc a, d
    ld [wClsPlaneHi], a
    CLS5_LOADK 0
    CLS5_TRIPLE 1
    CLS5_LOADK 1
    CLS5_TRIPLE 3
    CLS5_LOADK 2
    CLS5_TRIPLE 9
    CLS5_LOADK 3
    CLS5_TRIPLE 27
    CLS5_LOADK 4
    CLS5_TRIPLE 81
    ret

Cls_BuildTables::
    ld a, CLS_TBL_BANK
    ldh [rSVBK], a
    ld hl, wClsTbl
    ld bc, VOCAB * 2
.zero
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .zero

    xor a
    ldh [hClsBlk], a
.block
    ldh a, [hClsBlk]                ; hl = wXb + block * 5
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    ld c, a
    ld b, 0
    add hl, bc
    ld de, wXb
    add hl, de
    call Cls5_Build
    xor a
    ldh [hClsPart], a
.part
    ldh a, [hClsPart]
    ld c, a
    ld b, 0
    ld hl, cls_banks
    add hl, bc
    ld a, [hl]
    ld [rROMB0], a
    ld hl, cls_addrs
    add hl, bc
    add hl, bc                      ; word entries
    ld a, [hl+]
    ld e, a
    ld a, [hl]
    ld d, a                         ; de = the part's codes
    ldh a, [hClsBlk]                ; + block * CLS_OUTPUTS_PER_PART bytes
    add a, a                        ; (512 a block: two pages)
    add a, d
    ld d, a
    ld hl, wClsTbl                  ; + part * CLS_OUTPUTS_PER_PART * 2
    ldh a, [hClsPart]
    or a
    jr z, .go
    ld a, HIGH(CLS_OUTPUTS_PER_PART * 2)
.advance
    add a, h
    ld h, a
    ldh a, [hClsPart]
    dec a
    jr z, .go
    ld a, HIGH(CLS_OUTPUTS_PER_PART * 2)
    jr .advance
.go
    call Cls8_Rows                  ; the planes do not care how they were filled
    ldh a, [hClsPart]
    inc a
    ldh [hClsPart], a
    cp CLS_PARTS
    jr nz, .part
    ldh a, [hClsBlk]
    inc a
    ldh [hClsBlk], a
    cp CLS_BLOCKS5
    jr nz, .block
    ret

ENDC                                ; CLS_BINARY / ternary build

Cls_Argmax::
    ld a, CLS_TBL_BANK
    ldh [rSVBK], a
    xor a
    ld [wClsBest + 0], a            ; -32768, high byte pre-flipped
    ld [wClsBest + 1], a
    ld [wClsIdx + 0], a
    ld [wClsIdx + 1], a
    ld [wBestTok + 0], a
    ld [wBestTok + 1], a
    ld hl, wClsTbl
.output
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld d, a                         ; de = this token's logit
    push hl

    ld a, [wBlockedN]               ; tokens the no-repeat rule turned down
    or a
    jr z, .compare
    ld b, a
    ld hl, wBlocked
.blocked
    ld a, [wClsIdx + 0]
    cp [hl]
    inc hl
    jr nz, .nextBlocked
    ld a, [wClsIdx + 1]
    cp [hl]
    jr z, .skip
.nextBlocked
    inc hl
    dec b
    jr nz, .blocked

.compare
    ld a, d                         ; signed compare via flipped sign bits;
    xor $80                         ; strictly greater takes, ties keep the
    ld c, a                         ; earlier token, exactly as argmax does
    ld a, [wClsBest + 1]
    cp c
    jr c, .take
    jr nz, .skip
    ld a, [wClsBest + 0]
    cp e
    jr nc, .skip
.take
    ld a, c
    ld [wClsBest + 1], a
    ld a, e
    ld [wClsBest + 0], a
    ld a, [wClsIdx + 0]
    ld [wBestTok + 0], a
    ld a, [wClsIdx + 1]
    ld [wBestTok + 1], a
.skip
    pop hl
    ld a, [wClsIdx + 0]
    add a, 1
    ld [wClsIdx + 0], a
    ld a, [wClsIdx + 1]
    adc a, 0
    ld [wClsIdx + 1], a
    cp HIGH(VOCAB)
    jr nz, .output
    ld a, [wClsIdx + 0]
    cp LOW(VOCAB)
    jr nz, .output
    ret

ELSE

; One input's two lookups into the running sum. bc = table entry, de = sum,
; hl = weight stream. 24 cycles per MAC, against the input-major kernel's 37 -
; the difference is almost entirely the accumulator staying in registers.
MACRO CLS_MAC
    ld a, [hl+]                     ; 2  hi-entry address low byte
    ld c, a                         ; 1
    ld a, [bc]                      ; 2
    add a, e                        ; 1
    ld e, a                         ; 1
    inc c                           ; 1
    ld a, [bc]                      ; 2
    adc a, d                        ; 1
    ld d, a                         ; 1
    ld a, [hl+]                     ; 2  lo-entry address low byte
    ld c, a                         ; 1
    ld a, [bc]                      ; 2
    add a, e                        ; 1
    ld e, a                         ; 1
    inc c                           ; 1
    ld a, [bc]                      ; 2
    adc a, d                        ; 1
    ld d, a                         ; 1
ENDM

; Copies every input's product tables into wClsTbl. Two passes, one ROM bank
; switch each: all the hi tables, then all the lo tables into the upper half
; of each 64-byte slot. The same bytes the input-major kernel copied to HRAM
; one activation at a time - moved once, kept for the whole token.
Cls_BuildTables::
    ld a, CLS_TBL_BANK
    ldh [rSVBK], a

    ld a, BANK(lut_cls_hi)
    ld [rROMB0], a
    ld de, wClsTbl
    ld hl, wXb
    ld c, DIM
.hi
    ld a, [hl+]
    push hl
    push bc
    add a, 128                      ; signed activation -> table index
    ld l, a
    ld h, 0
REPT 5
    add hl, hl                      ; * 32 bytes per activation
ENDR
    ld bc, lut_cls_hi
    add hl, bc
    ld b, 32
.copyHi
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .copyHi
    ld a, e                         ; skip this slot's lo half
    add a, 32
    ld e, a
    jr nc, :+
    inc d
:   pop bc
    pop hl
    dec c
    jr nz, .hi

    ld a, BANK(lut_cls_lo)
    ld [rROMB0], a
    ld de, wClsTbl + 32
    ld hl, wXb
    ld c, DIM
.lo
    ld a, [hl+]
    push hl
    push bc
    add a, 128
    ld l, a
    ld h, 0
REPT 5
    add hl, hl
ENDR
    ld bc, lut_cls_lo
    add hl, bc
    ld b, 32
.copyLo
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .copyLo
    ld a, e                         ; skip the next slot's hi half
    add a, 32
    ld e, a
    jr nc, :+
    inc d
:   pop bc
    pop hl
    dec c
    jr nz, .lo
    ret

; The full argmax: every part, every output, best token into wBestTok.
;
; Re-runnable: the no-repeat retry loop calls this again with more tokens on
; the blocked list. A retry costs a full pass where the old design re-scanned
; stored sums, but retries are rare - about six across a 160-token run - and
; the storage they read is what this kernel exists to delete.
Cls_Argmax::
    ld a, CLS_TBL_BANK              ; insurance; the build already set it
    ldh [rSVBK], a
    xor a
    ld [wClsBest + 0], a            ; -32768, high byte pre-flipped
    ld [wClsBest + 1], a
    ld [wClsIdx + 0], a
    ld [wClsIdx + 1], a
    ld [wBestTok + 0], a
    ld [wBestTok + 1], a
    ld [wClsPart], a
.part
    ld a, [wClsPart]
    ld l, a
    ld h, 0
    ld de, cls_banks
    add hl, de
    ld a, [hl]
    ld [rROMB0], a

    ld a, [wClsPart]
    add a, a
    ld l, a
    ld h, 0
    ld de, cls_addrs
    add hl, de
    ld a, [hl+]
    ld e, a
    ld d, [hl]
    ld h, d                         ; hl = weight stream for this part
    ld l, e

    ld a, CLS_OUTPUTS_PER_PART
    ldh [hClsOut], a
    call Cls_Part

    ld a, [wClsPart]
    inc a
    ld [wClsPart], a
    cp CLS_PARTS
    jr c, .part
    ret

Cls_Part:
.output
    ld de, 0                        ; the dot product
    ld b, HIGH(wClsTbl)             ; table page walks with the input
    ld a, DIM / 8
    ldh [hClsGrp], a
.group
REPT 4
    CLS_MAC
ENDR
    inc b                           ; four 64-byte tables per page
REPT 4
    CLS_MAC
ENDR
    inc b
    ldh a, [hClsGrp]
    dec a
    ldh [hClsGrp], a
    jp nz, .group

    ; The sum is complete. Tokens the no-repeat rule turned down are skipped
    ; here, so a retry is just this routine again with a longer list.
    ld a, [wBlockedN]
    or a
    jr z, .compare
    push hl
    ld b, a
    ld hl, wBlocked
.blocked
    ld a, [wClsIdx + 0]
    cp [hl]
    inc hl
    jr nz, .nextBlocked
    ld a, [wClsIdx + 1]
    cp [hl]
    jr z, .blockedHit
.nextBlocked
    inc hl
    dec b
    jr nz, .blocked
    pop hl
    jr .compare
.blockedHit
    pop hl
    jr .skip

.compare
    ; Signed 16-bit against the best: flip both sign bits and the unsigned
    ; order is the signed order. Strictly-greater takes, so ties keep the
    ; earlier token, exactly as argmax does.
    ld a, d
    xor $80
    ld c, a
    ld a, [wClsBest + 1]
    cp c
    jr c, .take
    jr nz, .skip
    ld a, [wClsBest + 0]
    cp e
    jr nc, .skip
.take
    ld a, c
    ld [wClsBest + 1], a
    ld a, e
    ld [wClsBest + 0], a
    ld a, [wClsIdx + 0]
    ld [wBestTok + 0], a
    ld a, [wClsIdx + 1]
    ld [wBestTok + 1], a
.skip
    ld a, [wClsIdx + 0]
    add a, 1
    ld [wClsIdx + 0], a
    ld a, [wClsIdx + 1]
    adc a, 0
    ld [wClsIdx + 1], a

    ldh a, [hClsOut]
    dec a
    ldh [hClsOut], a
    jp nz, .output
    ret

ENDC
