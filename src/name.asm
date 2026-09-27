; The name opcodes: the model decides when, the engine keeps the text.
;
; The model has no context window, only its state, and cannot spell back a
; name it was told - it holds that one was told, not the letters. So Rei's
; tokenizer carries two pieces the keyboard can never produce, <SN> and <N>
; (py/export5.py finds them; without both, as in the story build, none of this
; is assembled), and the engine acts on them in PrintToken:
;
;   <SN>  store: the last word of the player's line of this turn goes into the
;         name slot, and nothing is printed. The word is the last run of
;         letters in wPromptText, lowercased, its first NAME_MAX letters; a
;         line with no letter leaves the slot as it was. The line is the one
;         Chat_Stage staged ("(nl)> text(nl)"): the marker and the newlines are
;         not letters, so it captures what the player typed.
;   <N>   say: the slot's letters go out through Type_PutChar like any piece,
;         so her pane, its wrap, the mood scan, the history and the log all see
;         the real name. An empty slot prints nothing.
;
; Both are her tokens like any other: they are recorded in wOutTokens, the
; no-repeat rule sees them, and the state is fed them. Only the printing is
; the engine's. golden5.capture_name and golden5.speak are the twin's side.
;
; The slot is part of the conversation: cleared when a conversation starts
; (Generate), kept in the battery save (src/app/rei_save.asm) and the world's
; snapshot (src/app/rei_world.asm), emptied by "new friend".
;
; wNameForce is a test hook: the harness plants up to NAME_FORCE_MAX tokens,
; and Generate takes them as her next picks instead of the classifier's (the
; model still runs each step), which is how the suite makes a model say <SN>
; and <N> when it wants to (py/tests/test_rei_name.py; golden5.chat_turn's
; `force`). Zero cost while it is empty: one test a model-chosen token.
;
; Cost: about 110 bytes of ROM0, 32 bytes of WRAM0.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

IF DEF(NAME_OPS)

DEF NAME_FORCE_MAX EQU 8

SECTION "Name state", WRAM0
wName::         ds NAME_MAX         ; the letters, zero-padded
wNameForceN::   db                  ; test hook: forced picks still to come,
wNameForceI::   db                  ; the next one's index,
wNameForceBuf:: ds NAME_FORCE_MAX * 2   ; and the tokens

SECTION "Name code", ROM0

; <SN>: the last word of wPromptText into the slot.
Name_Store::
    ld a, [wPromptLen]
    or a
    ret z
    ld c, a                         ; c = characters up to and including hl
    ld e, a
    ld d, 0
    ld hl, wPromptText
    add hl, de
.skip                               ; back over everything that is not a letter
    dec hl
    ld a, [hl]
    call Name_Letter
    jr c, .last
    dec c
    jr nz, .skip
    ret                             ; no letter at all: the slot stays
.last
    ld b, 1                         ; b = the word's letters so far
.back
    dec c
    jr z, .copy                     ; hl is the first character of the line
    dec hl
    ld a, [hl]
    call Name_Letter
    jr c, :+
    inc hl                          ; the word starts after this one
    jr .copy
:   inc b
    jr .back
.copy
    ld a, b
    cp NAME_MAX + 1
    jr c, :+
    ld b, NAME_MAX                  ; the first NAME_MAX letters
:   call Name_Clear                 ; keeps hl and b
    ld de, wName
.letter
    ld a, [hl+]
    or $20                          ; a letter: A-Z to a-z, a-z as it is
    ld [de], a
    inc de
    dec b
    jr nz, .letter
    ret

; Carry set if a is an ASCII letter. Clobbers a.
Name_Letter:
    or $20
    sub 'a'
    cp 26
    ret

; An empty slot. Keeps hl and bc.
Name_Clear::
    push hl
    ld hl, wName
    ld e, NAME_MAX
    xor a
.zero
    ld [hl+], a
    dec e
    jr nz, .zero
    pop hl
    ret

; <N>: the slot's letters, printed as a piece's would be.
Name_Say::
    ld hl, wName
    ld b, NAME_MAX
.char
    ld a, [hl+]
    or a
    ret z
    push hl
    push bc
    call Type_PutChar
    pop bc
    pop hl
    dec b
    jr nz, .char
    ret

; The test hook, for a model-chosen step: the next planted token replaces the
; classifier's pick in wBestTok, if one is left.
Name_Forced::
    ld a, [wNameForceN]
    or a
    ret z
    dec a
    ld [wNameForceN], a
    ld a, [wNameForceI]
    ld e, a
    inc a
    ld [wNameForceI], a
    ld d, 0
    ld hl, wNameForceBuf
    add hl, de
    add hl, de
    ld a, [hl+]
    ld [wBestTok + 0], a
    ld a, [hl]
    ld [wBestTok + 1], a
    ret

ASSERT HIGH(TOK_SN) == HIGH(TOK_N), "PrintToken compares the high byte once"
ASSERT NAME_MAX >= 1 && NAME_MAX <= 255 && PROMPT_MAX < 256, "byte counts"

ENDC
