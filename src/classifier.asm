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
hClsGrp:   db                       ; 8-input groups left in the output

SECTION "Cls code", ROM0

IF CLS_TERNARY

; --- the ternary classifier ------------------------------------------------
;
; The block kernel over all 512 outputs. Cls_BuildTables accumulates every
; logit as an int16 block sum into wClsTbl - the bank that used to hold the
; product tables holds the sums instead - and Cls_Argmax scans them. A
; no-repeat retry is a rescan of kept sums, not a recompute: the storage the
; register argmax deleted comes back because the sums are now cheap enough
; to keep. Same signed compare, same tie rule, same blocked list.

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

    ld a, LOW(wXb)
    ld [wMvXPtr + 0], a
    ld a, HIGH(wXb)
    ld [wMvXPtr + 1], a
    ld a, CLS_BLOCKS                ; the classifier's OWN block count: its
    ld [wMvIn], a                   ; codes are ternary threes even when the
    xor a                           ; model's rows are one-bit fours
    ldh [hClsPart], a
    ; One part of CLS_OUTPUTS_PER_PART outputs at a time - a part is what
    ; fits a bank, and what wMvGroups can count - each accumulating into its
    ; own stretch of the sum table. The manifest sits in ROM0, so it can be
    ; read whatever bank the previous part left mapped.
.part
    ldh a, [hClsPart]
    ld c, a
    ld b, 0
    ld hl, cls_banks
    add hl, bc
    ld a, [hl]
    ld [wMvBank], a
    ld hl, cls_addrs
    add hl, bc
    add hl, bc                      ; word entries
    ld a, [hl+]
    ld [wMvW + 0], a
    ld a, [hl]
    ld [wMvW + 1], a
    ld hl, CLS_OUTPUTS_PER_PART
    call Matvec_SetOut
    ld hl, wClsTbl
    ldh a, [hClsPart]
    or a
    jr z, .go
    ld de, CLS_OUTPUTS_PER_PART * 2
.advance
    add hl, de
    dec a
    jr nz, .advance
.go
    call Matvec3_RunAccumHL
    ldh a, [hClsPart]
    inc a
    ldh [hClsPart], a
    cp CLS_PARTS
    jr nz, .part
    ret

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
