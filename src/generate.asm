; Greedy decode loop and detokenizer.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"




SECTION "Generate state", WRAM0
wPrev::      dw                     ; previous token, for the BOS space rule
; Position at which this run's wTokBuf[0] is consumed. Zero for a fresh run; a
; chat continuation starts mid-stream, and the prompt-forcing index below is
; relative to the run, not to the conversation.
wRunStart::  db
wFromModel:  db                     ; this step's token came from argmax, not the prompt
wGenSteps::  db
wTokCycles:: ds 4                   ; cycles for the most recent forward pass
; Attention is O(T), so the most recent pass is not representative of any other
; one: the first token attends a single position and the last attends the whole
; window. The honest per-token figure is this total over wGenCount.
wGenTotal::  ds 4
wGenCount::  db                     ; tokens emitted so far
; Every token the model emits, so tests can check the model rather than the
; screen. Once the console scrolls, scraping the display stops being a faithful
; record of what was generated.
wOutTokens:: ds OUT_MAX * 2

SECTION "Generate code", ROM0

; Prints one token's text. llama2.c strips the space that follows BOS.
PrintToken::
    ld a, BANK(vocab_data)          ; offsets and pieces share the bank
    ld [rROMB0], a
    ld a, [wToken + 0]              ; offset table is indexed by token * 2
    ld l, a
    ld a, [wToken + 1]
    ld h, a
    add hl, hl
    ld de, vocab_data
    add hl, de
    ld a, [hl+]
    ld e, a
    ld a, [hl]
    ld d, a                         ; de = offset from vocab_data
    ld hl, vocab_data
    add hl, de
    ld a, [hl+]
    ld b, a                         ; length
    or a
    ret z

    ld a, [wPrev + 1]               ; skip a leading space right after BOS
    or a
    jr nz, .emit
    ld a, [wPrev + 0]
    cp TOK_BOS
    jr nz, .emit
    ld a, [hl]
    cp ' '
    jr nz, .emit
    inc hl
    dec b
    ret z
.emit
    ld a, [hl+]
    push hl
    push bc
    call Console_PutChar
    pop bc
    pop hl
    dec b
    jr nz, .emit
    ret

; Runs the model until wGenSteps tokens have been produced or EOS appears.
Generate::
    xor a
    ld [wRunStart], a
    ld [wAbsPos], a

    ld hl, wH                       ; a fresh conversation starts with an empty
    ld bc, N_LAYERS * DIM           ; mind: the recurrent state is the memory,
.zeroState                          ; and zero is its honest blank
    xor a                           ; a is clobbered by the counter test below,
    ld [hl+], a                     ; so it must be re-zeroed every iteration
    dec bc
    ld a, b
    or c
    jr nz, .zeroState
    xor a
    ld [wGenCount], a
    ld [wGenTotal + 0], a
    ld [wGenTotal + 1], a
    ld [wGenTotal + 2], a
    ld [wGenTotal + 3], a
    ld [wPrev + 0], a
    ld [wPrev + 1], a

    ld a, [wTokBuf + 0]             ; the prompt's first token starts the run
    ld [wToken + 0], a
    ld a, [wTokBuf + 1]
    ld [wToken + 1], a

.step
    ; Every token is profiled, not just the first. The ISR costs ~0.15%, and in
    ; exchange the status bar shows a live figure - which also makes the ring
    ; visible, since the cost climbs with the number of attended positions until
    ; the cache is full and then holds flat.
    call Prof_Start
    call Forward
    call Prof_Stop
    ld hl, wProfCycles
    ld de, wTokCycles
    ld b, 4
    call CopyN

    ; Prompt tokens are forced; after that the model's own argmax continues.
    ; The index is relative to this run: a continuation's buffer starts at
    ; wRunStart, not at position zero.
    ld a, [wRunStart]
    ld b, a
    ld a, [wAbsPos]
    inc a
    sub b
    ld hl, wTokCount
    cp [hl]
    jr nc, .useModel                ; prompt exhausted: the model takes over
    xor a
    ld [wFromModel], a
    ld a, [wRunStart]
    ld b, a
    ld a, [wAbsPos]
    inc a
    sub b
    ld c, a
    ld b, 0
    ld hl, wTokBuf
    add hl, bc
    add hl, bc
    ld a, [hl+]
    ld [wBestTok + 0], a
    ld a, [hl]
    ld [wBestTok + 1], a
    jr .picked
.useModel
    ld a, 1
    ld [wFromModel], a
.picked

    ld a, [wBestTok + 1]            ; stop at EOS
    or a
    jr nz, .notEos
    ld a, [wBestTok + 0]
    cp TOK_EOS
    ret z
.notEos

    ld a, [wToken + 0]              ; the token just consumed becomes "previous"
    ld [wPrev + 0], a
    ld a, [wToken + 1]
    ld [wPrev + 1], a
    ld a, [wBestTok + 0]
    ld [wToken + 0], a
    ld a, [wBestTok + 1]
    ld [wToken + 1], a

    ld a, [wGenCount]               ; record it before printing
    cp OUT_MAX
    jr nc, .noRecord
    ld l, a
    ld h, 0
    add hl, hl
    ld de, wOutTokens
    add hl, de
    ld a, [wToken + 0]
    ld [hl+], a
    ld a, [wToken + 1]
    ld [hl], a
.noRecord

    call PrintToken
    call Console_Flush

    ld hl, wTokCycles               ; running total, for a truthful average
    ld de, wGenTotal
    ld c, 4
    or a                            ; clear carry before the chain
.total
    ld a, [de]
    adc a, [hl]
    ld [de], a
    inc hl
    inc de
    dec c
    jr nz, .total

    ld a, [wGenCount]
    inc a
    ld [wGenCount], a

    call StatusWin_Update           ; cycles and count, both current
    call Joy_Read
    ld a, [wJoyNew]
    and KB_SELECT
    ret nz                          ; the player asked to go back - SELECT is
                                    ; "back" everywhere now, START only sends

    ld a, [wGenCount]
    ld b, a
    ld a, [wGenSteps]
    cp b
    ret z

IF TOK_NL >= 0
    ; Any model-chosen id at or below TOK_NL ends the turn. In the compact
    ; layout those four ids are exactly unk, BOS, EOS and the newline - none is
    ; ever part of a reply. The newline is the ordinary case: pip's line is
    ; over. BOS is the subtle one: training concatenates conversations with a
    ; BOS between them, so a model that considers the exchange complete
    ; predicts BOS and then starts writing the player's next line itself - the
    ; stray "> ..." lines the observer caught. Both mean the same thing: pip
    ; has nothing more to say. Only a *model-chosen* token ends the turn; the
    ; prompt's forced newlines must not, and once did.
    ;
    ; The stop token is printed but not yet consumed - Generate_Cont feeds it
    ; back as the first token of the next run, so the stream stays the
    ; training distribution: reply, separator, "> ", the player's words.
    ld a, [wFromModel]
    or a
    jr z, .notTurnEnd
    ld a, [wToken + 1]
    or a
    jr nz, .notTurnEnd
    ld a, [wToken + 0]
    cp TOK_NL + 1
    ret c
.notTurnEnd
ENDC

    ; A plain step counter now - it exists only to index the forced prompt
    ; relative to wRunStart, and that subtraction is modular, so the byte may
    ; wrap freely. The state has no table to fall off: no cap, no ring, no
    ; session limit. The conversation ends when the player ends it.
    ld hl, wAbsPos
    inc [hl]
    jp .step

IF TOK_NL >= 0
; Continues the conversation in the same stream: the state keeps everything it
; carried, the step counter keeps counting, and the new turn's tokens are
; forced from wTokBuf. The gate does the forgetting - what the being retains
; is whatever its training taught it to hold.
Generate_Cont::
    ld a, [wAbsPos]
    inc a                           ; the step the stop left unconsumed
    ld [wAbsPos], a
    ld [wRunStart], a

    xor a                           ; per-exchange stats and no-repeat history
    ld [wGenCount], a
    ld [wGenTotal + 0], a
    ld [wGenTotal + 1], a
    ld [wGenTotal + 2], a
    ld [wGenTotal + 3], a
    ld [wPrev + 0], a
    ld [wPrev + 1], a

    ld a, [wTokBuf + 0]             ; the newline the stop left behind
    ld [wToken + 0], a
    ld a, [wTokBuf + 1]
    ld [wToken + 1], a
    jp Generate.step
ENDC

; hl -> de, b bytes.
CopyN::
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, CopyN
    ret
