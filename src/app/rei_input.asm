; What the player says to Rei: the bottom third of the screen.
;
; Row 12 is a solid bar, the title and the buttons of whatever is under it, in
; tiny capitals drawn as tiles (py/gen_rei_art.py: forty columns of text in
; twenty tiles); rows 13-17 are five full-width rows with no frame. Three states:
;   topics     ten names in a grid of two by five (src/rei_topics.inc). The
;              d-pad moves, wrapping; A opens the topic. The prompt row is
;              empty: nothing is chosen yet.
;   sentences  the topic's lines, five to a page. UP/DOWN pick (wrapping in the
;              page), LEFT/RIGHT turn the page when there is another, A sends,
;              B goes back up to the topics with the cursor where it was.
;   keyboard   four rows of nine keys at a two-tile pitch. The d-pad moves
;              (wrapping), A types, B deletes; the last key is OK, and A on it
;              sends. Nothing typed, nothing sent.
; SELECT goes between the list (whichever of its two states it was in) and the
; keyboard; the keyboard's bar says which (SEL:LIST or SEL:TOPICS). START opens
; the conversation log (src/app/rei_log.asm) and comes back to this screen as
; it was. The prompt row above always shows what would be sent: the sentence
; under the cursor, or the tail of what has been typed with a caret after it.
;
; After a reply the screen comes back in the state the message was sent from -
; the same topic, page and cursor - so a follow-up is one press. Unless she
; asked something (her reply ends in "?", ReiUi_Asked): then the keyboard is
; up, empty, the cursor on its first key, and SELECT leads to the topics.
;
; Left alone for twenty seconds she wanders off to the world by herself
; (src/app/rei_world.asm) - the only way there. Any button brings this screen
; back as it was, typed text and all.
;
; The cursor is a palette, not only a tile: the cell or the row under it gets
; PAL_CURSOR in the attribute map (the bar is always PAL_PICK). A redraw is
; two VBlanks - the six rows, then the prompt row and the attributes - and
; every change just redraws.
;
; Cost: nothing in ROM0; about 1.1 KB of the UI bank and 1.5 KB of topics,
; 56 bytes of WRAM0.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

DEF IN_COLS    EQU 9
DEF IN_ROWS    EQU 4
DEF IN_CELLS   EQU IN_COLS * IN_ROWS
DEF IN_KEY_X   EQU 1                ; the first key's column; two apart after: 1..17
DEF GRID_ROWS  EQU 5                ; the topics: two columns of five
DEF GRID_X0    EQU 1                ; a column's text; its arrow is one to the left
DEF GRID_X1    EQU 11
DEF GRID_W     EQU 10               ; a column's highlight

DEF MODE_TOPICS EQU 0
DEF MODE_LINES  EQU 1
DEF MODE_KEYS   EQU 2

SECTION "Rei input state", WRAM0
wReiMode::    db                    ; MODE_*
wReiList:     db                    ; the list state SELECT returns to from the keys
wReiTopic::   db                    ; 0..9: column * 5 + row
wReiPage::    db                    ; of the topic's sentences
wReiPick::    db                    ; the row on that page
wReiKey::     db                    ; the keyboard cursor, row * 9 + column
wReiTextLen:: db
wReiText::    ds REI_TEXT_MAX       ; what has been typed
wReiCaret:    db                    ; the prompt row shows a caret
wReiGoWorld:: db                    ; ReiUi_Input returned for the world, not to send
wReiIdle::    dw                    ; frames since a button was last down

SECTION "Rei input", ROMX, BANK[REI_BANK]

INCLUDE "rei_topics.inc"

ReiKeys:
    db "abcdefghi"
    db "jklmnopqr"
    db "stuvwxyz "
    db ".,!?'-;: "                   ; the last cell is the OK key, not a character

; a = how many sentences the topic has.
ReiIn_Count:
    ld a, [wReiTopic]
    ld e, a
    ld d, 0
    ld hl, ReiTopicCounts
    add hl, de
    ld a, [hl]
    ret

; a = how many of them are on the page showing, b = how many pages.
ReiIn_OnPage:
    call ReiIn_Count
    ld b, 1
    cp TOPIC_PAGE + 1
    jr c, :+
    inc b
:   ld c, a
    ld a, [wReiPage]
    or a
    ld a, c
    jr z, :+
    sub TOPIC_PAGE
:   cp TOPIC_PAGE
    ret c
    ld a, TOPIC_PAGE
    ret

; a = sentence number in the topic -> hl = its text.
ReiIn_Line:
    ld b, a
    ld a, [wReiTopic]
    add a, a
    ld e, a
    ld d, 0
    ld hl, ReiTopicLists
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    inc b
    jr .next
.skip
    ld a, [hl+]
    or a
    jr nz, .skip
.next
    dec b
    jr nz, .skip
    ret

; a = the first sentence number of the page showing.
ReiIn_PageBase:
    ld a, [wReiPage]
    or a
    ret z
    ld a, TOPIC_PAGE
    ret

; The prompt row, into the shadow.
ReiIn_DrawSay:
    xor a
    ld b, SAY_X
    ld c, SAY_Y
    ld d, SAY_W
    ld e, 1
    call Rei_Fill
    ld a, [wReiMode]
    or a
    ret z                           ; the topics: nothing chosen, nothing shown
    cp MODE_KEYS
    jr z, .typed
    call ReiIn_PageBase
    ld hl, wReiPick
    add a, [hl]
    call ReiIn_Line
    ld b, SAY_X
    ld c, SAY_Y
    jp Rei_Print
.typed
    ; The tail that fits: SAY_W characters, one fewer beside the caret.
    ld a, [wReiCaret]
    ld b, a
    ld a, SAY_W
    sub b
    ld c, a                         ; c = room for text
    ld a, [wReiTextLen]
    ld d, 0                         ; d = first character shown
    cp c
    jr c, .fits
    jr z, .fits
    sub c
    ld d, a
.fits
    push de
    ld b, SAY_X
    ld c, SAY_Y
    call Rei_CellAddr               ; hl = the row in the shadow
    pop de
    ld a, [wReiTextLen]
    sub d
    ld c, a                         ; c = characters to draw
    push hl
    ld hl, wReiText
    ld e, d
    ld d, 0
    add hl, de
    ld d, h
    ld e, l                         ; de = the first of them
    pop hl
    inc c
    jr .next
.char
    ld a, [de]
    inc de
    sub FONT_FIRST
    ld [hl+], a
.next
    dec c
    jr nz, .char
    ld a, [wReiCaret]
    or a
    ret z
    ld [hl], '_' - FONT_FIRST
    ret

; The bar and the five rows, into the shadow: whichever state it is.
ReiIn_Draw:
    xor a
    ld b, LIST_X
    ld c, BAR_Y
    ld d, LIST_W
    ld e, LIST_H + 1
    call Rei_Fill
    ld a, [wReiMode]
    cp MODE_LINES
    jr z, .lines
    jp nc, .keys

    ; --- the topics ---
    ld hl, ReiBarTopics
    call ReiIn_Bar
    ld hl, ReiTopicNames
    ld b, GRID_X0
.column
    ld c, LIST_Y
.name
    push bc
    push hl
    call Rei_CellAddr
    ld d, h
    ld e, l
    pop hl
    ld b, TOPIC_W
.letter
    ld a, [hl+]
    sub FONT_FIRST
    ld [de], a
    inc de
    dec b
    jr nz, .letter
    pop bc
    inc c
    ld a, c
    cp LIST_Y + GRID_ROWS
    jr c, .name
    ld a, b
    cp GRID_X1
    ld b, GRID_X1
    jr c, .column
    call ReiIn_TopicCell            ; the arrow, left of the chosen name
    dec b
    jr .arrow

    ; --- a topic's sentences ---
.lines
    ld hl, ReiBarLines
    call ReiIn_Bar
    call ReiIn_OnPage
    dec b
    jr z, .onePage
    ld hl, ReiBarPages              ; "<>:PAGE 1/2", or 2/2: there is another page
    ld a, [wReiPage]
    or a
    jr z, :+
    ld hl, ReiBarPages + BAR_PAGE_W
:   ld b, LIST_X + BAR_PAGE_X
    ld c, BAR_Y
    ld d, BAR_PAGE_W
    ld e, 1
    call Rei_DrawMap
.onePage
    call ReiIn_OnPage
    push af
    call ReiIn_PageBase
    call ReiIn_Line
    pop af
    ld c, LIST_Y
.line
    push af
    ld b, LIST_X + 1
    call Rei_Print                  ; leaves hl at the next sentence
    inc c
    pop af
    dec a
    jr nz, .line
    ld a, [wReiPick]
    add a, LIST_Y
    ld c, a
    ld b, LIST_X
.arrow
    call Rei_CellAddr
    ld [hl], T_ARROW_R
    ret

    ; --- the keyboard ---
.keys
    ld hl, ReiBarKeys               ; "SEL:LIST": back to a topic's sentences,
    ld a, [wReiList]                ; or "SEL:TOPICS": to the grid
    cp MODE_TOPICS
    jr nz, :+
    ld hl, ReiBarKeysTopics
:   call ReiIn_Bar
    ld b, IN_KEY_X
    ld c, LIST_Y
    call Rei_CellAddr
    ld de, ReiKeys
    ld c, IN_ROWS
.row
    ld b, IN_COLS
    push hl
.key
    ld a, [de]
    inc de
    cp ' '
    jr nz, :+
    ld a, '_'                       ; the space key needs something to look at
:   sub FONT_FIRST
    ld [hl+], a
    inc hl
    dec b
    jr nz, .key
    pop hl
    push bc
    ld bc, CON_W
    add hl, bc
    pop bc
    dec c
    jr nz, .row
    ld b, IN_KEY_X + (IN_COLS - 1) * 2      ; the last key sends
    ld c, LIST_Y + IN_ROWS - 1
    call Rei_CellAddr
    ld [hl], T_OK
    ret

; hl = a bar from src/rei_art.inc: twenty tiles of tiny capitals, into row 12.
ReiIn_Bar:
    ld b, LIST_X
    ld c, BAR_Y
    ld d, LIST_W
    ld e, 1
    jp Rei_DrawMap

; b = column, c = row of the chosen topic's name.
ReiIn_TopicCell:
    ld a, [wReiTopic]
    ld b, GRID_X0
    cp GRID_ROWS
    jr c, :+
    sub GRID_ROWS
    ld b, GRID_X1
:   add a, LIST_Y
    ld c, a
    ret

; The cursor's palette: the five rows plain, then the pick. a = 0 to leave
; nothing picked. Must run inside VBlank.
ReiIn_Attrs:
    push af
    ld a, PAL_GREEN
    ld b, LIST_X
    ld c, LIST_Y
    ld d, LIST_W
    ld e, LIST_H
    call Rei_Attr
    pop af
    or a
    ret z
    ld a, [wReiMode]
    or a
    jr nz, :+
    call ReiIn_TopicCell            ; a topic: its half of the row
    dec b
    ld d, GRID_W
    jr .pick
:   cp MODE_KEYS
    jr z, .key
    ld a, [wReiPick]                ; a sentence: the whole row
    add a, LIST_Y
    ld c, a
    ld b, LIST_X
    ld d, LIST_W
    jr .pick
.key
    ld a, [wReiKey]
    ld c, LIST_Y
.rows
    cp IN_COLS
    jr c, .col
    sub IN_COLS
    inc c
    jr .rows
.col
    add a, a
    add a, IN_KEY_X
    ld b, a
    ld d, 1
.pick
    ld e, 1
    ld a, PAL_CURSOR
    jp Rei_Attr

; Shadow -> screen for everything this file draws. a = 0 hides the cursor.
ReiIn_Refresh::
    push af
    call ReiIn_DrawSay
    call ReiIn_Draw
    call Console_WaitVBlank
    ld hl, BAR_Y * CON_W + LIST_X
    ld b, LIST_H + 1
    ld c, LIST_W
    call Rei_Blit
    call Console_WaitVBlank
    ld hl, SAY_Y * CON_W + SAY_X
    ld b, 1
    ld c, SAY_W
    call Rei_Blit
    pop af
    jp ReiIn_Attrs

; Her reply is complete. If it is a question - its last character that is not
; a space is a "?" - the answer is the player's own words: the keyboard comes
; up with nothing typed and the cursor on its first key, and SELECT from it
; goes to the topics with the first one chosen, not back to the list the
; question answered. Any other reply leaves the state it was sent from.
; wReiReply is the text as kept (no newline; the first REI_REPLY_MAX
; characters).
ReiUi_Asked::
    ld a, [wReiReplyLen]
    ld c, a
    ld b, 0
    ld hl, wReiReply
    add hl, bc
.back
    ld a, c
    or a
    ret z                           ; nothing but spaces: no question
    dec hl
    dec c
    ld a, [hl]
    cp ' '
    jr z, .back
    cp '?'
    ret nz
    ld a, MODE_KEYS
    ld [wReiMode], a
    xor a                           ; MODE_TOPICS
    ld [wReiList], a
    ld [wReiTopic], a
    ld [wReiKey], a
    ret

; Back from the world: the screen is as it was left, so nothing is redrawn and
; nothing typed is lost.
ReiUi_Resume::
    jp ReiUi_Input.resume

; The INPUT state. Returns with the message in wPromptText / wPromptLen, still
; showing on the prompt row, and already in the log - or with wReiGoWorld set.
ReiUi_Input::
    xor a
    ld [wReiTextLen], a
    inc a
    ld [wReiCaret], a
.redraw
    ld a, 1
    call ReiIn_Refresh
.resume
    xor a
    ld [wReiGoWorld], a
.awake
    xor a
    ld [wReiIdle + 0], a
    ld [wReiIdle + 1], a
.loop
    call Rei_IdleFrame
    or a
    jr nz, .pressed
    ld a, [wJoyHeld]
    or a
    jr nz, .awake
    ld hl, wReiIdle                 ; nobody there: after a while she wanders off
    inc [hl]
    jr nz, :+
    inc hl
    inc [hl]
:   ld a, [wReiIdle + 0]
    cp LOW(REI_WANDERS)
    jr nz, .loop
    ld a, [wReiIdle + 1]
    cp HIGH(REI_WANDERS)
    jr nz, .loop
    ld a, 1
    ld [wReiGoWorld], a
    ret
.pressed
    ld b, a
    xor a
    ld [wReiIdle + 0], a
    ld [wReiIdle + 1], a
    ld a, b
    and KB_START
    jr z, :+
    call ReiLog_Run                 ; comes back on SELECT, this screen untouched
    jr .awake
:   ld a, [wReiMode]
    ld c, a                         ; c = the state, b = the buttons
    ld a, b
    and KB_SELECT
    jr z, .notSelect
    ld a, c                         ; the list <-> the keyboard
    cp MODE_KEYS
    ld a, [wReiList]
    jr z, :+
    ld a, c
    ld [wReiList], a
    ld a, MODE_KEYS
:   ld [wReiMode], a
    jr .redraw
.notSelect
    ld a, c
    cp MODE_LINES
    jp z, .lines
    jp nc, .keyboard

    ; --- the topics: a grid of two by five ---
    ld a, b
    and KB_A
    jr z, :+
    xor a
    ld [wReiPage], a
    ld [wReiPick], a
    inc a
    ld [wReiMode], a                ; MODE_LINES
    jp .redraw
:   ld a, [wReiTopic]
    ld c, a
    ld a, b
    and KB_LEFT | KB_RIGHT
    jr z, :+
    ld a, c                         ; the other column, the same row
    add a, GRID_ROWS
    cp TOPIC_COUNT
    jr c, .topic
    sub TOPIC_COUNT
    jr .topic
:   ld a, c                         ; e = the column's first topic, a = the row
    ld e, 0
    cp GRID_ROWS
    jr c, :+
    sub GRID_ROWS
    ld e, GRID_ROWS
:   ld d, GRID_ROWS
    call .upDown
    jp z, .loop
    add a, e
.topic
    ld [wReiTopic], a
    jp .redraw

; a = a row, d = how many rows, b = the buttons: a = the row after UP or DOWN,
; wrapping. Z set if neither was pressed.
.upDown
    ld c, a
    ld a, b
    and KB_UP
    jr z, :+
    ld a, c
    or a
    jr nz, .up
    ld a, d
.up
    dec a
    jr .moved
:   ld a, b
    and KB_DOWN
    ret z
    ld a, c
    inc a
    cp d
    jr c, .moved
    xor a
.moved
    ld c, a
    or 1                            ; Z clear
    ld a, c
    ret

    ; --- a topic's sentences ---
.lines
    ld a, b
    and KB_B
    jr z, :+
    xor a
    ld [wReiMode], a                ; back up, the cursor on the topic it came from
    jp .redraw
:   ld a, b
    and KB_A
    jr nz, .sendLine
    ld a, b
    and KB_LEFT | KB_RIGHT
    jr z, :+
    push bc
    call ReiIn_OnPage
    pop de
    dec b
    jp z, .loop                     ; one page: nothing to turn
    ld a, [wReiPage]
    xor 1
    ld [wReiPage], a
    call ReiIn_OnPage               ; the new page may be shorter
    ld hl, wReiPick
    dec a
    cp [hl]
    jp nc, .redraw
    ld [hl], a
    jp .redraw
:   push bc
    call ReiIn_OnPage
    pop bc
    ld d, a
    ld a, [wReiPick]
    call .upDown
    jp z, .loop
    ld [wReiPick], a
    jp .redraw

.sendLine
    call ReiIn_PageBase
    ld hl, wReiPick
    add a, [hl]
    call ReiIn_Line
    ld de, wPromptText
    ld c, 0
.copyLine
    ld a, [hl+]
    or a
    jp z, .staged
    ld [de], a
    inc de
    inc c
    jr .copyLine

    ; --- the keyboard: four rows of nine ---
.keyboard
    ld a, b
    and KB_A
    jr nz, .add
    ld a, b
    and KB_B
    jr nz, .del
    ld a, [wReiKey]                 ; left and right: a ring of 36
    ld c, a
    ld a, b
    and KB_RIGHT
    ld e, 1
    jr nz, .move
    ld a, b
    and KB_LEFT
    ld e, IN_CELLS - 1
    jr nz, .move
    ld a, b
    and KB_DOWN
    ld e, IN_COLS
    jr nz, .move
    ld a, b
    and KB_UP
    jp z, .loop
    ld e, IN_CELLS - IN_COLS
.move
    ld a, c
    add a, e
    cp IN_CELLS
    jr c, :+
    sub IN_CELLS
:   ld [wReiKey], a
    jp .redraw

.add
    ld a, [wReiKey]
    cp IN_CELLS - 1
    jr z, .sendText                 ; the OK key
    ld c, a
    ld a, [wReiTextLen]
    cp REI_TEXT_MAX
    jp nc, .loop
    ld e, a
    ld d, 0
    ld b, d
    ld hl, ReiKeys
    add hl, bc
    ld a, [hl]
    ld hl, wReiText
    add hl, de
    ld [hl], a
    ld a, e
    inc a
    ld [wReiTextLen], a
    jp .redraw
.del
    ld a, [wReiTextLen]
    or a
    jp z, .loop
    dec a
    ld [wReiTextLen], a
    jp .redraw

.sendText
    ld a, [wReiTextLen]
    or a
    jp z, .loop                     ; an empty turn is not a turn
    ld c, a
    ld b, a
    ld hl, wReiText
    ld de, wPromptText
.copyText
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .copyText
.staged
    ld a, c
    ld [wPromptLen], a
    xor a
    ld [wReady], a                  ; a new exchange: not ready until she has answered
    ld [wReiCaret], a               ; the row keeps the words, without the caret
    ld hl, wPromptText              ; the player's side of the log
    ld b, 1
    call ReiLog_Add
    xor a                           ; and the cursor goes
    jp ReiIn_Refresh

ASSERT REI_TEXT_MAX + 4 <= PROMPT_MAX, "Chat_Stage adds a newline, the marker and a newline"
ASSERT TOPIC_COUNT == 2 * GRID_ROWS && TOPIC_PAGE == LIST_H
ASSERT MODE_TOPICS == 0, "ReiUi_Asked clears the list state with the topic"

ENDC
