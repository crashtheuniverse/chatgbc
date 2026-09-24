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
; A piece is found by hash, not by scanning the vocabulary: the exporter lays
; the vocabulary out in an open-addressed table of token id + 1 (twice as many
; slots as pieces) under h = h * 33 + byte, linear probing, so a lookup hashes
; the candidate, probes a slot or two and compares one piece. The longest piece
; comes from the exporter too (ENC_PIECE_MAX: 11 bytes in both vocabularies).
; And the merge loop remembers each adjacent pair's result (Enc_Pairs): a merge
; changes only the pairs either side of it, so only those two are looked up
; again.
;
; Until v1.0 the lookup was a linear scan that stopped at 7-byte pieces, and
; every merge pass looked up every pair: the tokens drifted from Python's on
; lines that needed a longer piece (" favourite", " cartridge.", ...), and the
; story's opening prompt took 8.3 million cycles, four seconds, to encode. Now
; it is 55 thousand, and the tokens are Python's (py/tests/test_encoder.py,
; py/tests/test_encoder_rei.py).

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

DEF ENC_MAX_PIECE EQU ENC_PIECE_MAX ; longest piece in the vocabulary (the exporter's)

SECTION "Encoder state", WRAM0
wPromptText:: ds PROMPT_MAX
wPromptLen::  db
wTokBuf::     ds TOK_MAX * 2        ; token IDs, little-endian
wTokCount::   db
wEncCand:     ds ENC_MAX_PIECE * 2  ; candidate merged piece
wEncCandLen:  db
wEncBestTok:  dw
wEncBestIdx:  db
wEncPair:     db
wEncChar:     db
wEncNoBos:    db
wEncCycles::  ds 4                  ; the last encode, from the ROM's own counter
wEncHashN:    db                    ; bytes left to hash
wEncTokLast:  db                    ; pairs left after a merge

DEF ENC_PAIR_BANK EQU 4             ; a WRAM bank nothing else uses while encoding
SECTION "Encoder pairs", WRAMX[$D000], BANK[ENC_PAIR_BANK]
; Pair i is tokens i and i + 1: the rank of their merged piece ($FFFF when it is
; not a piece) and the piece's id, four bytes a pair.
wEncPairs:    ds TOK_MAX * 4

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

; Searches the vocabulary for wEncCand (length wEncCandLen), by hash.
; Returns carry set with hl = token id, or carry clear if absent.
Enc_Find::
    ld a, [wEncCandLen]
    cp ENC_MAX_PIECE + 1
    jr nc, .none                    ; longer than any piece: cannot exist
    ld [wEncHashN], a
    ld hl, 0
    ld de, wEncCand
.hash                               ; h = h * 33 + byte, sixteen bits
    push hl
REPT 5
    add hl, hl
ENDR
    pop bc
    add hl, bc
    ld a, [de]
    inc de
    add a, l
    ld l, a
    jr nc, :+
    inc h
:   ld a, [wEncHashN]
    dec a
    ld [wEncHashN], a
    jr nz, .hash
    ld a, h                         ; the slot: the hash's low bits, two bytes each
    and HIGH(ENC_HASH_SLOTS - 1)
    ld h, a
    add hl, hl
    ld de, enc_all + ENC_HASH_AT
    add hl, de
.probe
    ld a, [hl+]
    ld c, a
    ld a, [hl-]
    ld b, a
    or c
    jr z, .none                     ; an empty slot: the piece is not there
    dec bc                          ; the table holds id + 1
    push hl
    push bc
    ld h, b
    ld l, c
    call Enc_Piece                  ; de -> [len][bytes]
    ld a, [de]
    ld hl, wEncCandLen
    cp [hl]
    jr nz, .miss
    inc de
    ld hl, wEncCand
    ld b, a
.bytes
    ld a, [de]
    cp [hl]
    jr nz, .miss
    inc de
    inc hl
    dec b
    jr nz, .bytes
    pop hl                          ; the id
    pop bc
    scf
    ret
.miss
    pop bc
    pop hl
    inc hl                          ; the next slot, round the end of the table
    inc hl
    ld a, h
    cp HIGH(enc_all + ENC_HASH_AT + 2 * ENC_HASH_SLOTS)
    jr nz, .probe
    ld a, l
    cp LOW(enc_all + ENC_HASH_AT + 2 * ENC_HASH_SLOTS)
    jr nz, .probe
    ld hl, enc_all + ENC_HASH_AT
    jr .probe
.none
    or a                            ; clear carry
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

; Encode or EncodeCont (a = 0 or 1), timed into wEncCycles. The timer is the
; profiler's, so this leaves interrupts as Prof_Stop does: off.
Encode_Timed::
    push af
    call Prof_Start
    pop af
    or a
    jr nz, .cont
    call Encode
    jr .timed
.cont
    call EncodeCont
.timed
    call Prof_Stop
    ld de, wEncCycles
    jp SaveCycles

; wPromptText/wPromptLen -> wTokBuf/wTokCount.
Encode::
    xor a
    ld [wEncNoBos], a
    jr Enc_Body

; The same encoder for a turn that continues an existing stream: no BOS and no
; dummy prefix, because those belong to the start of a conversation, and a
; mid-stream turn that carried them would be a token sequence training never
; produced. The caller stages the newline as the first character of the text.
EncodeCont::
    ld a, 1
    ld [wEncNoBos], a
    ; fall through

Enc_Body:
    ld a, BANK(enc_all)
    ld [rROMB0], a

    ld hl, wTokBuf
    xor a
    ld [wTokCount], a
    ld a, [wEncNoBos]
    or a
    jr nz, .noBos

    ld a, TOK_BOS                   ; BOS
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
.noBos

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
    ; The single character exists as its own piece - py/tokenizer.py gives every
    ; key on this keyboard one, whether or not the corpus used it. Taking a
    ; fallback unconditionally would yield "<0x4F>"-style pieces that can never
    ; merge, so the whole BPE pass would do nothing.
    ;
    ; The miss path is UNK rather than byte+3. That offset only means anything
    ; under llama2.c's layout, where ids 3..258 are the bytes; a compact
    ; vocabulary spends those ids on merges, so byte+3 would silently encode a
    ; typed character as an unrelated word.
    ld [wEncCand], a
    ld a, 1
    ld [wEncCandLen], a
    call Enc_Find
    jr c, .haveTok
    ld hl, TOK_UNK
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
    jp Enc_Pairs

; The merge loop with every pair's result kept: look all pairs up once; then
; merge the best, and look up again only the two pairs the merge made. The
; best is the lowest rank, and the first of equals - Python's strictly-greater
; score test, pass for pass.
Enc_Pairs:
    ld a, ENC_PAIR_BANK
    ldh [rSVBK], a
    ld a, [wTokCount]
    sub 2
    jp c, .done                     ; fewer than two tokens: nothing to merge
    inc a
    ld b, a                         ; pairs
    xor a
.first
    push af
    push bc
    call Enc_PairAt
    pop bc
    pop af
    inc a
    dec b
    jr nz, .first

.pass
    ld a, [wTokCount]
    dec a
    jr z, .done
    ld b, a                         ; b = pairs
    ld c, 0                         ; c = this pair
    ld hl, wEncPairs
    ld de, $FFFF                    ; de = the best rank so far
.scan
    ld a, [hl+]
    push hl
    ld h, [hl]
    ld l, a                         ; hl = this pair's rank
    ld a, h
    cp d
    jr c, .better
    jr nz, .notBetter
    ld a, l
    cp e
    jr nc, .notBetter
.better
    ld d, h
    ld e, l
    ld a, c
    ld [wEncBestIdx], a
.notBetter
    pop hl
    inc hl
    inc hl
    inc hl
    inc c
    dec b
    jr nz, .scan
    ld a, d
    and e
    inc a
    jr z, .done                     ; $FFFF: no pair is a piece

    ld a, [wEncBestIdx]             ; tokens[best] = the merged piece
    call Enc_PairAddr
    inc hl
    inc hl
    ld a, [hl+]
    ld [wEncBestTok + 0], a
    ld a, [hl]
    ld [wEncBestTok + 1], a
    call Enc_MergeAt                ; ... and tokens[best + 1] gone
    ld a, [wEncBestIdx]             ; pair best + 1 goes, the rest move down
    call Enc_PairAddr
    ld d, h
    ld e, l
    ld bc, 4
    add hl, bc
    ld a, [wTokCount]               ; pairs left after it: count - best - 1
    ld b, a
    ld a, [wEncBestIdx]
    cpl
    add a, b                        ; count - best - 1
    jr z, .moved
    add a, a
    add a, a
    ld c, a
.move
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .move
.moved
    ld a, [wEncBestIdx]             ; the pair ending at the new token
    or a
    jr z, :+
    dec a
    call Enc_PairAt
:   ld a, [wEncTokLast]             ; and the pair starting at it, if there is one
    ld b, a
    ld a, [wEncBestIdx]
    cp b
    call c, Enc_PairAt
    jr .pass
.done
    ld a, 1
    ldh [rSVBK], a
    ret

; a = pair index -> hl = its four bytes. Changes a, bc, hl.
Enc_PairAddr:
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    ld bc, wEncPairs
    add hl, bc
    ret

; a = pair index: looks tokens a and a + 1 up as one piece, into its slot.
Enc_PairAt:
    ld [wEncPair], a
    xor a
    ld [wEncCandLen], a
    ld a, [wEncPair]
    call Enc_TokenAt
    call Enc_AppendPiece
    ld a, [wEncPair]
    inc a
    call Enc_TokenAt
    call Enc_AppendPiece
    call Enc_Find                   ; hl = the id, or carry clear
    ld bc, $FFFF
    jr nc, .store
    push hl
    add hl, hl
    ld de, enc_all + ENC_RANK_AT
    add hl, de
    ld a, [hl+]
    ld c, a
    ld b, [hl]
    pop hl
.store
    ld d, h
    ld e, l
    ld a, [wEncPair]
    push bc
    call Enc_PairAddr
    pop bc
    ld a, c
    ld [hl+], a
    ld a, b
    ld [hl+], a
    ld a, e
    ld [hl+], a
    ld [hl], d
    ret

; tokens[wEncBestIdx] = wEncBestTok, tokens[wEncBestIdx + 1] deleted; sets
; wEncTokLast to the number of pairs (count - 1) after the merge.
Enc_MergeAt:
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
    dec a
    ld [wEncTokLast], a             ; pairs left
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

ASSERT ENC_MAX_PIECE * 2 < 256 && ENC_HASH_SLOTS >= 256 && (ENC_HASH_SLOTS & (ENC_HASH_SLOTS - 1)) == 0, "the candidate and the hash table as the exporter built them"
ASSERT TOK_MAX * 4 <= $1000, "the pairs fit their bank"
