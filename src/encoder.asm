; BPE encoder: prompt text -> token IDs.
;
; A transcription of llama2.c's encode, which is what the model was trained
; with. Start from one token per byte, then repeatedly merge the adjacent pair
; whose combined piece scores highest, until nothing merges.
;
; Scores ship as *ranks* (0 = best), so the comparison is an unsigned 16-bit
; "less than" instead of a float compare. Ranks are unique, so the first pair at
; a given rank wins - matching Python's strictly-greater test.
;
; The vocabulary lookup is a linear scan of 512 entries. That sounds expensive
; until you notice the longest piece is 7 bytes: any candidate longer than that
; cannot exist, and every entry whose length differs is rejected on one compare.
; A 16-character prompt encodes in well under a second.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

DEF ENC_MAX_PIECE EQU 7             ; longest piece in the vocabulary
DEF TOK_MAX       EQU 64            ; tokens after encoding

SECTION "Encoder state", WRAM0
wPromptText:: ds PROMPT_MAX
wPromptLen::  db
wTokBuf::     ds TOK_MAX * 2        ; token IDs, little-endian
wTokCount::   db
wEncCand:     ds ENC_MAX_PIECE * 2  ; candidate merged piece
wEncCandLen:  db
wEncBestRank: dw
wEncBestTok:  dw
wEncBestIdx:  db
wEncFound:    db
wEncIdx:      dw                    ; scan cursor
wEncPtr:      dw
wEncPair:     db
wEncAny:      db
wEncChar:     db

SECTION "Encoder code", ROM0

; hl = token index. Returns de = pointer to that piece's [len][bytes] in ROM.
; The caller must already have selected BANK(enc_vocab).
Enc_Piece:
    add hl, hl
    ld de, enc_all + ENC_OFF_AT
    add hl, de
    ld a, [hl+]
    ld e, a
    ld a, [hl]
    ld d, a
    ld hl, enc_all + ENC_VOCAB_AT
    add hl, de
    ld d, h
    ld e, l
    ret

; Searches the vocabulary for wEncCand (length wEncCandLen).
; Returns carry set with hl = token id, or carry clear if absent.
Enc_Find::
    ld a, [wEncCandLen]
    cp ENC_MAX_PIECE + 1
    jr nc, .none                    ; longer than any piece: cannot exist
    xor a
    ld [wEncIdx + 0], a
    ld [wEncIdx + 1], a
.entry
    ld a, [wEncIdx + 0]
    ld l, a
    ld a, [wEncIdx + 1]
    ld h, a
    push hl
    call Enc_Piece                  ; de -> [len][bytes]
    ld a, [de]
    ld hl, wEncCandLen
    cp [hl]
    jr nz, .miss                    ; length differs: rejected on one compare
    inc de
    ld hl, wEncCand
    ld b, a
    or a
    jr z, .hit
.bytes
    ld a, [de]
    cp [hl]
    jr nz, .miss
    inc de
    inc hl
    dec b
    jr nz, .bytes
.hit
    pop hl
    scf
    ret
.miss
    pop hl
    inc hl
    ld a, l
    ld [wEncIdx + 0], a
    ld a, h
    ld [wEncIdx + 1], a
    cp HIGH(VOCAB)
    jr nz, .entry
    ld a, l
    cp LOW(VOCAB)
    jr nz, .entry
.none
    or a                            ; clear carry
    ret

; As Enc_Find, but keeps the hit only if it outranks the best pair so far.
; Ranks are unique, so the first pair at a given rank wins - which is what
; Python's strictly-greater score test does.
Enc_Lookup:
    call Enc_Find
    ret nc
    push hl
    add hl, hl
    ld de, enc_all + ENC_RANK_AT
    add hl, de
    ld a, [hl+]
    ld c, a
    ld a, [hl]
    ld b, a                         ; bc = rank, lower is better
    ld a, [wEncBestRank + 1]
    cp b
    jr c, .worse
    jr nz, .better
    ld a, [wEncBestRank + 0]
    cp c
    jr c, .worse
    jr z, .worse
.better
    ld a, c
    ld [wEncBestRank + 0], a
    ld a, b
    ld [wEncBestRank + 1], a
    pop hl
    ld a, l
    ld [wEncBestTok + 0], a
    ld a, h
    ld [wEncBestTok + 1], a
    ld a, 1
    ld [wEncFound], a
    ret
.worse
    pop hl
    ret

; Appends the piece for token hl to wEncCand.
Enc_AppendPiece:
    call Enc_Piece
    ld a, [de]
    or a
    ret z
    ld c, a                         ; piece length; b is not safe here because
    inc de                          ; `ld bc, wEncCand` below would clobber it
    ld a, [wEncCandLen]
    ld l, a
    ld h, 0
    add a, c
    ld [wEncCandLen], a
    ld b, 0
    push bc
    ld bc, wEncCand
    add hl, bc                      ; hl = &wEncCand[old length]
    pop bc
.copy
    ld a, [de]
    ld [hl+], a
    inc de
    dec c
    jr nz, .copy
    ret

; wPromptText/wPromptLen -> wTokBuf/wTokCount.
Encode::
    ld a, BANK(enc_all)
    ld [rROMB0], a

    ld hl, wTokBuf                  ; BOS
    ld a, TOK_BOS
    ld [hl+], a
    xor a
    ld [hl+], a
    ld a, 1
    ld [wTokCount], a

    ld a, [wPromptLen]
    or a
    jr z, .merge

    ld a, LOW(TOK_SPACE)            ; llama2.c's dummy prefix
    ld [hl+], a
    ld a, HIGH(TOK_SPACE)
    ld [hl+], a
    ld a, 2
    ld [wTokCount], a

    ld de, wPromptText
    ld a, [wPromptLen]
    ld b, a
.chars
    ld a, [de]
    ld [wEncChar], a
    inc de
    push de
    push bc
    push hl
    ; The single character usually exists as its own piece; byte+3 is only a
    ; fallback. Taking the fallback unconditionally yields "<0x4F>"-style pieces
    ; that can never merge, so the whole BPE pass would do nothing.
    ld [wEncCand], a
    ld a, 1
    ld [wEncCandLen], a
    call Enc_Find
    jr c, .haveTok
    ld a, [wEncChar]
    add a, 3
    ld l, a
    ld h, 0
.haveTok
    ld d, h
    ld e, l
    pop hl
    ld a, e
    ld [hl+], a
    ld a, d
    ld [hl+], a
    ld a, [wTokCount]
    inc a
    ld [wTokCount], a
    pop bc
    pop de
    dec b
    jr nz, .chars

.merge
    call Enc_MergeOnce
    ld a, [wEncFound]
    or a
    jr nz, .merge
    ret

; One merge pass: find the best-scoring adjacent pair and merge it.
; Leaves wEncFound non-zero if anything merged.
Enc_MergeOnce:
    xor a
    ld [wEncAny], a
    ld [wEncFound], a               ; every exit path must report "nothing merged"
    ld a, $FF                       ; rank 0 is best, so start at the worst
    ld [wEncBestRank + 0], a
    ld [wEncBestRank + 1], a

    ld a, [wTokCount]
    dec a
    ret z                           ; fewer than two tokens: nothing to merge
    ld b, a                         ; pairs to consider
    xor a
    ld [wEncPair], a
.pair
    push bc
    xor a
    ld [wEncCandLen], a
    ld [wEncFound], a

    ld a, [wEncPair]                ; piece(tok[i]) then piece(tok[i+1])
    call Enc_TokenAt
    call Enc_AppendPiece
    ld a, [wEncPair]
    inc a
    call Enc_TokenAt
    call Enc_AppendPiece
    call Enc_Lookup

    ld a, [wEncFound]
    or a
    jr z, .nextPair
    ld a, [wEncPair]                ; this pair improved on the best so far
    ld [wEncBestIdx], a
    ld a, 1
    ld [wEncAny], a
.nextPair
    ld a, [wEncPair]
    inc a
    ld [wEncPair], a
    pop bc
    dec b
    jr nz, .pair

    ld a, [wEncAny]
    ld [wEncFound], a
    or a
    ret z

    ; Replace tokens[best] with the merged id and delete tokens[best+1].
    ld a, [wEncBestIdx]
    call Enc_SlotAt
    ld a, [wEncBestTok + 0]
    ld [hl+], a
    ld a, [wEncBestTok + 1]
    ld [hl+], a                     ; hl now points at tokens[best+1]
    ld d, h
    ld e, l
    inc hl
    inc hl
    ld a, [wTokCount]
    ld b, a
    ld a, [wEncBestIdx]
    inc a
    inc a
    ld c, a
    ld a, b
    sub a, c                        ; tokens after the deleted one
    jr z, .shrink
    ld b, a
.shift
    ld a, [hl+]
    ld [de], a
    inc de
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .shift
.shrink
    ld a, [wTokCount]
    dec a
    ld [wTokCount], a
    ret

; a = index. Returns hl = &wTokBuf[index].
Enc_SlotAt::
    ld l, a
    ld h, 0
    add hl, hl
    ld de, wTokBuf
    add hl, de
    ret

; a = index. Returns hl = tokens[index].
Enc_TokenAt:
    call Enc_SlotAt
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ret

; Loads a fixed prompt and encodes it, so the encoder can be checked against
; py/reference.py without a keyboard in the way.
Encode_TestPrompt::
    ld hl, sTestPrompt
    ld de, wPromptText
    ld b, 0
.copy
    ld a, [hl+]
    or a
    jr z, .done
    ld [de], a
    inc de
    inc b
    jr .copy
.done
    ld a, b
    ld [wPromptLen], a
    jp Encode

sTestPrompt: db "Once upon a time", 0
