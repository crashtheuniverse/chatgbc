; The ternary classifier, output-major: sixteen block tables, the sum in a
; register pair, the argmax fused, nothing stored.
;
; What it computes: logit[t] = sum_i w[t,i] * xb[i] over the 64 int8 activations
; of the final norm, w ternary, and then the two largest logits in the twin's
; stable order (quant.pick_token: argsort of -logits, kind="stable", so ties
; keep the lower token). Greedy decode needs only that, and the old path paid
; for far more: 2 KB of int16 sums zeroed, thirteen block-of-five planes each
; added into all 1024 sums with a read-modify-write per lookup, then a rescan
; of the sums for the argmax - 423,808 cycles a token on the census.
;
; Why it is exact: TERNARY_ACC_SHIFT = 0 (py/twin5.py), so Q.matvec_blocks
; rounds nothing - every block sum is exact and the row's logit is their plain
; sum, the same integer whatever the blocking. The table for block k holds the
; 81 exact sums c_0 x_{4k} + .. + c_3 x_{4k+3} a ternary block can produce, as
; int16; the scan adds sixteen of them in de, mod 2^16, which is the same int16
; the twin asserts |logit| <= 32767 for. The compare is signed via the flipped
; high byte, strictly greater in token order, so the first of equal logits
; stays: the stable argsort's rule.
;
; Layout: block k's table is page k of WRAM bank CLS_TBL_BANK, entry code at
; offset 2 * code (lo, hi), code = sum((c_i + 1) * 3^i) in 0..80. The exporter
; (export5.ternary_row_blob) ships each token as sixteen bytes, byte k already
; 2 * code for block k - the low address byte of its entry - so the weight
; byte IS the table index and the page register walks with the block. 1024
; rows of 16 bytes fill one ROM bank; the token is recovered from the stream
; pointer, (ptr - $4010) >> 4, only for the two rows that win.
;
; Retries: the no-repeat rule (NoRepeat_Ok in forward.asm) may turn the best
; token down, and pick_token then takes order[k] on the k-th reject. The scan
; keeps the top TWO in stable order, so the first two rejects cost a slot read
; each; the third and later cost a rescan that skips the rejected tokens,
; which yields the next two in order. Measured on 15,500 free-generation
; tokens (FACTS.md): 3.55% of tokens retry once, 0.23% more than once, so the
; rescan runs about once in 440 tokens.
;
; Cycles, counted here per token (CGB double speed):
;   build   16 blocks x 1,114 (Cls4_Build below, call included) + 16 x 14 loop
;           + 24 = ~18.1K
;   scan    1024 outputs x 221 (CLS4_ROW below: 11 + 14 x 13 + 12 + 13 + 3)
;           + ~21 equal-high-byte compares x 7 + ~14 takes x ~70 (Cls4_Take:
;           87 for a new best, 53 for a new runner-up) + ~70 setup = ~227.5K
;   glue    two token conversions ~130, the probe record ~20
;   total   ~245.7K before NoRepeat_Ok, against the old path's 423.8K;
;           the census (8 tokens) measures 246,712 for the whole stage.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

IF CLS_TERNARY

IF CLS_BLOCKS4 != 16
    FAIL "cls4: the scan is unrolled over 16 blocks = one WRAM bank of tables"
ENDC
IF CLS_OUTPUTS_PER_PART * 16 != $4000
    FAIL "cls4: a part must fill its bank - the scan stops at $8000"
ENDC

SECTION "Cls4 HRAM", HRAM
hBestHi: db                         ; slot 0, the best so far: high byte sign-flipped
hBestLo: db
hThrHi:  db                         ; slot 1, the runner-up: the scan's threshold
hThrLo:  db
hClsX:   ds 4                       ; the block being built: its four activations

SECTION "Cls4 state", WRAM0
; Each slot: the weight-stream pointer just past the token's row, then the part.
wBestPtr:  dw
wBestPart: db
wSecPtr:   dw
wSecPart:  db
wClsPage:  db                       ; the table page being built
wCls4Part: db                       ; the part being scanned
; Candidates the no-repeat rule turned down this step, (ptr lo, ptr hi, part)
; each - the same shape as a slot, compared on the take path of a rescan.
wClsBlocked: ds NOREPEAT_TRIES * 3
; The first pass's argmax and runner-up as tokens, before any retry: what the
; lab test reads.
wClsArg::  dw
wClsArg2:: dw

; --- the build ---------------------------------------------------------------
;
; One block's 81 sums as a direct sum: entry 0 is -(x0 + x1 + x2 + x3), every
; coefficient -1; then for digit k (3^k = n) the entries [n, 2n) are entries
; [0, n) plus x_k and [2n, 3n) are [0, n) plus 2x_k. Every entry is one 16-bit
; add from an earlier one, and the entries are written in order, so the write
; pointer never moves except forward. Fully unrolled: 80 entries x 8 bytes; it
; reads WRAM0 and writes the table bank only, so it lives in a ROM bank and the
; caller maps it. Its bank is mapped by Cls4_Tables, not left mapped.
;
; Cycles: ld de 3; sum 4 x 15 = 60; save hl, page, entry 0 = 18; four digits
; x (7 load + 2 + 4 + 2) = 60; 80 entries x 12 = 960; pop, ret 7 -> 1,108
; + call 6 = 1,114.
SECTION "Cls4 build", ROMX

; hl -> the block's four activations; on return hl is past them.
Cls4_Build:
    ld de, 0                        ; de = minus the sum of the four
FOR k, 0, 4
    ld a, [hl+]                     ; 2
    ldh [hClsX + k], a              ; 3
    ld c, a                         ; 1
    add a, a                        ; 1
    sbc a, a                        ; 1  sign extension
    ld b, a                         ; 1
    ld a, e                         ; 1
    sub c                           ; 1
    ld e, a                         ; 1
    ld a, d                         ; 1
    sbc a, b                        ; 1
    ld d, a                         ; 1
ENDR
    push hl                         ; 4
    ld a, [wClsPage]                ; 4
    ld b, a                         ; 1  b:c reads entries [0, n)
    ld h, a                         ; 1  h:l writes, in order, from entry 0
    ld l, 0                         ; 2
    ld a, e                         ; 1
    ld [hl+], a                     ; 2
    ld a, d                         ; 1
    ld [hl+], a                     ; 2  entry 0
FOR k, 0, 4
    DEF n = 3 ** k
    ldh a, [hClsX + k]              ; 3  de = x_k, sign-extended
    ld e, a                         ; 1
    add a, a                        ; 1
    sbc a, a                        ; 1
    ld d, a                         ; 1
    ld c, 0                         ; 2
REPT n
    ld a, [bc]                      ; 2  entries [n, 2n) = [0, n) + x_k
    add a, e                        ; 1
    ld [hl+], a                     ; 2
    inc c                           ; 1
    ld a, [bc]                      ; 2
    adc a, d                        ; 1
    ld [hl+], a                     ; 2
    inc c                           ; 1
ENDR
    sla e                           ; 2  de = 2 x_k
    rl d                            ; 2
    ld c, 0                         ; 2
REPT n
    ld a, [bc]                      ; 2  entries [2n, 3n) = [0, n) + 2 x_k
    add a, e                        ; 1
    ld [hl+], a                     ; 2
    inc c                           ; 1
    ld a, [bc]                      ; 2
    adc a, d                        ; 1
    ld [hl+], a                     ; 2
    inc c                           ; 1
ENDR
ENDR
    pop hl                          ; 3
    ret                             ; 4

; --- the scan ----------------------------------------------------------------
SECTION "Cls4 code", ROM0

; Builds the sixteen tables from wXb. Maps the table bank and the build's ROM
; bank; the scan maps the codes' bank after.
Cls4_Tables:
    ld a, CLS_TBL_BANK
    ldh [rSVBK], a
    ld a, BANK(Cls4_Build)
    ld [rROMB0], a
    ld hl, wXb
    ld a, HIGH(wClsTbl)
    ld [wClsPage], a
.block
    call Cls4_Build                 ; 6, and hl walks the activations
    ld a, [wClsPage]                ; 4
    inc a                           ; 1
    ld [wClsPage], a                ; 4
    cp HIGH(wClsTbl) + CLS_BLOCKS4  ; 2
    jr nz, .block                   ; 3
    ret

; One token's row: sixteen lookups summed in de, then the compare against the
; threshold (slot 1). hl = the weight stream, b = the table page, walking up
; (\1 = 1) on an even token and down (\1 = -1) on the odd one that follows -
; the exporter reversed the odd rows' block order for exactly this, so b is
; already right when the next row starts and there is no page reset. The
; first lookup loads instead of adding.
MACRO CLS4_ROW
    ld a, [hl+]                     ; 2  block: the code byte
    ld c, a                         ; 1
    ld a, [bc]                      ; 2
    ld e, a                         ; 1
    inc c                           ; 1
    ld a, [bc]                      ; 2
    ld d, a                         ; 1
    IF \1 > 0
    inc b                           ; 1  -> 11
    ELSE
    dec b
    ENDC
REPT 14
    ld a, [hl+]                     ; 2
    ld c, a                         ; 1
    ld a, [bc]                      ; 2
    add a, e                        ; 1
    ld e, a                         ; 1
    inc c                           ; 1
    ld a, [bc]                      ; 2
    adc a, d                        ; 1
    ld d, a                         ; 1
    IF \1 > 0
    inc b                           ; 1  -> 13
    ELSE
    dec b
    ENDC
ENDR
    ld a, [hl+]                     ; 2  the last block leaves b on its page
    ld c, a                         ; 1
    ld a, [bc]                      ; 2
    add a, e                        ; 1
    ld e, a                         ; 1
    inc c                           ; 1
    ld a, [bc]                      ; 2
    adc a, d                        ; 1
    ld d, a                         ; 1  -> 12
    ; Signed compare via the flipped sign bit: unsigned order is then signed
    ; order. Strictly greater than the runner-up enters the list, so the
    ; earlier of two equal logits keeps its place.
    ld a, d                         ; 1
    xor $80                         ; 2
    ld c, a                         ; 1
    ldh a, [hThrHi]                 ; 3
    cp c                            ; 1
    jr c, .take\@                   ; 2/3
    jr nz, .next\@                  ; 3/2  -> 13 typical
    ldh a, [hThrLo]                 ; 3   equal high bytes: +7
    cp e                            ; 1
    jr nc, .next\@                  ; 3/2
.take\@
    call Cls4_Take                  ; ~14 a token, c:e = the logit flipped
.next\@
ENDM

; Every part, every token: slots 0 and 1 hold the two best in stable order,
; skipping the tokens on wClsBlocked. Leaves the table bank and the last
; part's ROM bank mapped.
Cls4_Scan:
    ld a, CLS_TBL_BANK              ; insurance; the build set it
    ldh [rSVBK], a
    xor a                           ; both slots at -32768, flipped: any
    ldh [hBestHi], a                ; logit enters (the twin asserts > -32768)
    ldh [hBestLo], a
    ldh [hThrHi], a
    ldh [hThrLo], a
    ld [wCls4Part], a
.part
    ld a, [wCls4Part]
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
    ld h, [hl]
    ld l, a                         ; hl = the part's rows, at $4000
    ld b, HIGH(wClsTbl)
.pair
    CLS4_ROW 1
    CLS4_ROW -1
    bit 7, h                        ; 2  the bank ends at $8000
    jp z, .pair                     ; 4  -> 3 an output
    ld a, [wCls4Part]
    inc a
    ld [wCls4Part], a
    cp CLS_PARTS
    jp nz, .part
    ret

; The candidate c:e (flipped) at hl (past its row) beat the runner-up. Rare
; (about H(1024) x 2 = 14 a token), so it is a call. Preserves b and hl.
Cls4_Take:
    ld a, [wBlockedN]
    or a
    jr z, .insert
    ; A rescan: candidates the no-repeat rule turned down never enter.
    push hl
    push de
    push bc
    ld d, h
    ld e, l
    ld b, a
    ld hl, wClsBlocked
.blocked
    ld a, [hl+]
    cp e
    jr nz, .miss2
    ld a, [hl+]
    cp d
    jr nz, .miss1
    ld a, [wCls4Part]
    cp [hl]
    jr z, .hit
    inc hl
    jr .nextBlocked
.miss2
    inc hl
.miss1
    inc hl
.nextBlocked
    dec b
    jr nz, .blocked
    pop bc
    pop de
    pop hl
.insert
    ldh a, [hBestHi]                ; above the best too? then it shifts down
    cp c
    jr c, .newBest
    jr nz, .second
    ldh a, [hBestLo]
    cp e
    jr nc, .second
.newBest
    ldh a, [hBestHi]
    ldh [hThrHi], a
    ldh a, [hBestLo]
    ldh [hThrLo], a
    ld a, [wBestPtr + 0]
    ld [wSecPtr + 0], a
    ld a, [wBestPtr + 1]
    ld [wSecPtr + 1], a
    ld a, [wBestPart]
    ld [wSecPart], a
    ld a, c
    ldh [hBestHi], a
    ld a, e
    ldh [hBestLo], a
    ld a, l
    ld [wBestPtr + 0], a
    ld a, h
    ld [wBestPtr + 1], a
    ld a, [wCls4Part]
    ld [wBestPart], a
    ret
.second
    ld a, c
    ldh [hThrHi], a
    ld a, e
    ldh [hThrLo], a
    ld a, l
    ld [wSecPtr + 0], a
    ld a, h
    ld [wSecPtr + 1], a
    ld a, [wCls4Part]
    ld [wSecPart], a
    ret
.hit
    pop bc
    pop de
    pop hl
    ret

; --- tokens from pointers -----------------------------------------------------

; A part's rows start at $4000 (it fills the bank), so a slot's pointer, which
; is past the row, gives token = ((ptr - $4010) >> 4) + part * 1024.
ASSERT cls_w_p0 == $4000, "cls4: the classifier rows must start the bank"
IF CLS_OUTPUTS_PER_PART != 1024
    FAIL "cls4: Cls4_SlotTok forms part * 1024 with two adds"
ENDC

; hl -> a slot (ptr lo, ptr hi, part) -> wBestTok.
Cls4_SlotTok:
    ld a, [hl+]
    ld e, a
    ld a, [hl+]
    ld d, a
    ld c, [hl]
    ld h, d
    ld l, e
    ld de, -$4010
    add hl, de                      ; hl = token * 16
REPT 4
    srl h
    rr l
ENDR
    ld a, c
    add a, a
    add a, a
    add a, h
    ld h, a
    ld a, l
    ld [wBestTok + 0], a
    ld a, h
    ld [wBestTok + 1], a
    ret

; hl -> a slot: appended to wClsBlocked, counted as a reject and a retry.
Cls4_Block:
    ld a, [wBlockedN]
    ld c, a
    add a, a
    add a, c                        ; 3 bytes an entry
    ld c, a
    ld b, 0
    push hl
    ld hl, wClsBlocked
    add hl, bc
    ld d, h
    ld e, l                         ; de -> the free entry
    pop hl
    ld a, [hl+]
    ld [de], a
    inc de
    ld a, [hl+]
    ld [de], a
    inc de
    ld a, [hl]
    ld [de], a
    ld hl, wBlockedN
    inc [hl]
    ld hl, wRetries                 ; telemetry: a third reject rescans, so
    inc [hl]                        ; the rate matters
    ret nz
    ld hl, wRetries + 1
    inc [hl]
    ret

; --- the classifier ------------------------------------------------------------

; Tables and one scan over wXb, no retry: the top two as tokens into wClsArg
; and wClsArg2 (the runner-up first, so wBestTok is left holding the best).
; The lab's LAB_GO_CLS entry calls this on a vector the harness planted.
Cls4_Probe::
    call Cls4_Tables
    xor a
    ld [wBlockedN], a
    call Cls4_Scan
    ld hl, wSecPtr
    call Cls4_SlotTok
    ld a, [wBestTok + 0]
    ld [wClsArg2 + 0], a
    ld a, [wBestTok + 1]
    ld [wClsArg2 + 1], a
    ld hl, wBestPtr
    call Cls4_SlotTok
    ld a, [wBestTok + 0]
    ld [wClsArg + 0], a
    ld a, [wBestTok + 1]
    ld [wClsArg + 1], a
    ret

; wXb -> the token to emit in wBestTok, after the no-repeat rule: order[k] on
; the k-th reject, order[NOREPEAT_TRIES] after that many, as pick_token.
Cls4_Classify::
    call Cls4_Probe                 ; wBestTok = slot 0
.tryBest
    call NoRepeat_Ok
    ret nz                          ; nothing repeated: take it
    ld a, [wBlockedN]
    cp NOREPEAT_TRIES
    ret nc                          ; out of patience: keep the best on offer
    ld hl, wBestPtr
    call Cls4_Block
    ld hl, wSecPtr                  ; the runner-up is order[k + 1] already
    call Cls4_SlotTok
    call NoRepeat_Ok
    ret nz
    ld a, [wBlockedN]
    cp NOREPEAT_TRIES
    ret nc
    ld hl, wSecPtr
    call Cls4_Block
    call Cls4_Scan                  ; the next two, in order, past the blocked
    ld hl, wBestPtr
    call Cls4_SlotTok
    jr .tryBest

ENDC                                ; CLS_TERNARY
