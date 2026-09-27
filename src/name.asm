; The name opcodes: the model decides when, the engine keeps the text.
;
; The model has no context window, only its state, and cannot spell back a
; name it was told - it holds that one was told, not the letters. So Rei's
; tokenizer carries pieces the keyboard can never produce, <SN> and <N> and
; (v3) <W> (py/export5.py finds them; without <SN> and <N>, as in the story
; build, none of this is assembled), and the engine acts on them in PrintToken:
;
;   <SN>  store: the last word of the player's line of this turn goes into the
;         name slot, and nothing is printed. The word is the last run of
;         letters in wPromptText, lowercased, its first NAME_MAX letters; a
;         line with no letter leaves the slot as it was. The line is the one
;         Chat_Stage staged ("(nl)> text(nl)"): the marker and the newlines are
;         not letters, so it captures what the player typed.
;   <N>   say: the slot's letters go out through Type_PutChar like any piece,
;         so her pane, its wrap, the mood scan, the history and the log all see
;         the real name. An empty slot says "friend".
;   <W>   echo (a tokenizer with <W>, v3): the same last word of the player's
;         line, by the same rule (Name_LastWord), printed like <N> prints -
;         and the slot is not touched. A line with no letter prints nothing.
;         "> cats" -> "<W>! cats are soft." says "cats! cats are soft."
;
; All three are her tokens like any other: they are recorded in wOutTokens,
; the no-repeat rule sees them, and the state is fed them. Only the printing
; is the engine's. golden5.last_word and golden5.speak are the twin's side.
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
; The header (Name_Header, with a tokenizer that has <NK>): the model cannot
; hold "a name was given" in its state, so while the slot holds a name every
; player turn is fed with <NK> as its second token (py/header.py is the rule
; the corpus, the twin and this share).
;
; Cost, as the map measures it: 155 bytes of ROM0 here and 23 in PrintToken
; and Generate, 30 bytes of WRAM0; the header 45 more here and 3 at each of the
; cartridge's four encodes; <W> 18 more here and 5 in PrintToken.

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

; The last word of wPromptText, the capture rule <SN> and <W> share: the last
; run of letters, its first NAME_MAX. Carry set and hl = its first letter,
; b = its length (1..NAME_MAX); carry clear if the line has no letter.
Name_LastWord:
    ld a, [wPromptLen]
    or a
    ret z                           ; nc: an empty line
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
    ret                             ; nc: no letter at all
.last
    ld b, 1                         ; b = the word's letters so far
.back
    dec c
    jr z, .cap                      ; hl is the first character of the line
    dec hl
    ld a, [hl]
    call Name_Letter
    jr c, :+
    inc hl                          ; the word starts after this one
    jr .cap
:   inc b
    jr .back
.cap
    ld a, b
    cp NAME_MAX + 1
    ret c                           ; c: b letters
    ld b, NAME_MAX                  ; the first NAME_MAX letters
    scf
    ret

; <SN>: the last word of wPromptText into the slot.
Name_Store::
    call Name_LastWord
    ret nc                          ; no letter at all: the slot stays
    call Name_Clear                 ; keeps hl and b
    ld de, wName
.letter
    ld a, [hl+]
    or $20                          ; a letter: A-Z to a-z, a-z as it is
    ld [de], a
    inc de
    dec b
    jr nz, .letter
    ret

IF DEF(TOK_W)
; <W>: the same word, printed as a piece's would be - and the slot untouched.
; A line with no letter prints nothing.
Name_Echo::
    call Name_LastWord
    ret nc
.char
    ld a, [hl+]
    or $20                          ; lowercased, as <SN> stores it
    push hl
    push bc
    call Type_PutChar
    pop bc
    pop hl
    dec b
    jr nz, .char
    ret
ENDC

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

; <N>: the slot's letters, printed as a piece's would be - "friend" while the
; slot is empty (nobody has said who they are, and "thank you, . you are kind"
; reads worse than "thank you, friend.").
Name_Say::
    ld hl, wName
    ld a, [hl]
    or a
    jr nz, :+
    ld hl, sNameFriend
:   ld b, NAME_MAX
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

sNameFriend: db "friend", 0

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

IF DEF(TOK_NK)
; The header. She cannot hold "a name was given" across a conversation in her
; state, so the engine tells her every turn: while the slot holds a name,
; the player's turn starts with <NK>. It is the turn's second token - after
; BOS on a first turn, after the newline her last reply stopped on on a
; continuation - and right before the tokens of "> ", which is where her
; training corpus puts it (golden5.staged_ids, py/header.py). Called after
; the encoder: no piece joins BOS or the newline to anything, so the tokens
; either side are the ones a separate encode gives, and it is forced like
; every prompt token. An empty slot: no header, the turn as before.
Name_Header::
    ld a, [wName]
    or a
    ret z
    ld a, [wTokCount]               ; n >= 1: BOS or the newline is always there
    ld e, a
    ld d, 0
    ld hl, wTokBuf
    add hl, de
    add hl, de                      ; hl = one past the last token
    ld d, h
    ld e, l
    inc de
    inc de                          ; de = the same, a token further on
    dec a
    jr z, .put
    add a, a                        ; the n - 1 tokens after the first, moved
    ld c, a                         ; up one slot, back to front
.move
    dec hl
    dec de
    ld a, [hl]
    ld [de], a
    dec c
    jr nz, .move
.put
    ld hl, wTokBuf + 2
    ld a, LOW(TOK_NK)
    ld [hl+], a
    ld [hl], HIGH(TOK_NK)
    ld hl, wTokCount
    inc [hl]
    ret

ASSERT PROMPT_MAX + 3 <= TOK_MAX, "BOS, the dummy space, the line and the header fit wTokBuf"
ENDC

ASSERT HIGH(TOK_SN) == HIGH(TOK_N), "PrintToken compares the high byte once"
IF DEF(TOK_W)
ASSERT HIGH(TOK_W) == HIGH(TOK_SN), "PrintToken compares the high byte once"
ENDC
ASSERT NAME_MAX >= 6, "the fallback name fits the slot"
ASSERT NAME_MAX >= 1 && NAME_MAX <= 255 && PROMPT_MAX < 256, "byte counts"

ENDC
