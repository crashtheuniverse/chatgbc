; Greedy decode loop and detokenizer.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

DEF TOK_BOS EQU 1
DEF TOK_EOS EQU 2

SECTION "Generate state", WRAM0
wPrev::      dw                     ; previous token, for the BOS space rule
wGenSteps::  db
wTokCycles:: ds 4                   ; cycles for the most recent forward pass
wGenCount::  db                     ; tokens emitted so far
; Every token the model emits, so tests can check the model rather than the
; screen. Once the console scrolls, scraping the display stops being a faithful
; record of what was generated.
DEF OUT_MAX EQU 128
wOutTokens:: ds OUT_MAX * 2

SECTION "Generate code", ROM0

; Prints one token's text. llama2.c strips the space that follows BOS.
PrintToken::
    ld a, [wToken + 0]              ; offset table is indexed by token * 2
    ld l, a
    ld a, [wToken + 1]
    ld h, a
    add hl, hl
    ld de, vocab_off
    add hl, de
    ld a, [hl+]
    ld e, a
    ld a, [hl]
    ld d, a

    ld a, BANK(vocab_data)
    ld [rROMB0], a
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
    ld [wPos], a
    ld [wAbsPos], a
    ld [wGenCount], a
    ld [wPrev + 0], a
    ld [wPrev + 1], a

    ld a, [prompt + 0]              ; the prompt's first token starts the run
    ld [wToken + 0], a
    ld a, [prompt + 1]
    ld [wToken + 1], a

.step
    ; Only the first token is profiled. Leaving the timer running for the whole
    ; generation is measurably expensive under emulation, and one forward pass
    ; is all the s/token figure needs.
    ld a, [wGenCount]
    or a
    jr nz, .noProf
    call Prof_Start
.noProf
    call Forward
    ld a, [wGenCount]
    or a
    jr nz, .skipStop
    call Prof_Stop
    ld hl, wProfCycles
    ld de, wTokCycles
    ld b, 4
    call CopyN
.skipStop

    ; Prompt tokens are forced; after that the model's own argmax continues.
    ld a, [wAbsPos]
    inc a
    cp PROMPT_LEN
    jr nc, .useModel
    ld c, a
    ld b, 0
    ld hl, prompt
    add hl, bc
    add hl, bc
    ld a, [hl+]
    ld [wBestTok + 0], a
    ld a, [hl]
    ld [wBestTok + 1], a
.useModel

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

    ld a, [wGenCount]
    inc a
    ld [wGenCount], a
    ld b, a
    ld a, [wGenSteps]
    cp b
    ret z

    ; Advance the true position, then clamp the attended-slot bound. The cache
    ; rings, so once SEQ_LEN slots are live every step attends all of them.
    ld a, [wAbsPos]
    inc a
    ld [wAbsPos], a
    ret z                           ; wrapped past 255: the RoPE table ends there
    cp SEQ_LEN
    jr c, .withinWindow
    ld a, SEQ_LEN - 1
.withinWindow
    ld [wPos], a
    jp .step

; hl -> de, b bytes.
CopyN::
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, CopyN
    ret
