; What the player says to Rei: the bottom half of the screen.
;
; Two ways in, SELECT switches between them:
;   the list      three prompts from a pool of nine. UP/DOWN pick, LEFT/RIGHT
;                 turn the page, A sends.
;   the keyboard  four rows of nine keys at a two-tile pitch. The d-pad moves,
;                 A types, B deletes; the last key is OK, and A on it sends.
;                 Nothing typed, nothing sent.
; The prompt row above always shows what would be sent: the chosen prompt, or
; the tail of what has been typed with a caret after it.
;
; Her earlier replies are always a step away: UP off the top of the list (or
; the top row of keys) pages her pane to the reply before, DOWN off the bottom
; to the one after (src/app/rei_history.asm). START opens the conversation log
; (src/app/rei_log.asm) and comes back to this screen as it was.
;
; The cursor is a palette, not a tile: the cell (or the list row) under it gets
; PAL_PICK in the attribute map. A redraw is two VBlanks - the keys' rectangle,
; then the prompt row and the attributes - and every change just redraws.
;
; Cost: nothing in ROM0; about 960 bytes of the UI bank, 50 bytes of WRAM0.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

DEF IN_COLS   EQU 9
DEF IN_ROWS   EQU 4
DEF IN_CELLS  EQU IN_COLS * IN_ROWS
DEF IN_KEY_X  EQU KEYS_X + 1        ; the first key's column; two apart after
DEF IN_POOL   EQU 9
DEF IN_PER    EQU 3                 ; prompts a page
DEF IN_PAGES  EQU IN_POOL / IN_PER
DEF IN_LIST_X EQU KEYS_X + 1        ; the prompts, right of the arrow

SECTION "Rei input state", WRAM0
wReiMode::    db                    ; 0 = the list, 1 = the keyboard
wReiPage::    db                    ; which three prompts
wReiPick::    db                    ; which of the three
wReiKey::     db                    ; the keyboard cursor, row * 9 + column
wReiTextLen:: db
wReiText::    ds REI_TEXT_MAX       ; what has been typed
wReiCaret:    db                    ; the prompt row shows a caret

SECTION "Rei input", ROMX, BANK[REI_BANK]

; The pool. Lower case and inside the training distribution, every one - which
; is why the questions carry no question mark: the player's lines in her
; training text never do, and with one she mistakes the turn for her own and
; writes a player's line back. py/tests/test_rei_ui.py checks that each prompt
; encodes with no unknown piece and draws a reply in her own voice.
ReiPrompts:
    dw .p0, .p1, .p2, .p3, .p4, .p5, .p6, .p7, .p8
.p0: db "hello", 0
.p1: db "what is your name", 0
.p2: db "my name is tom", 0
.p3: db "what is my name", 0
.p4: db "i like chess", 0
.p5: db "what do i like", 0
.p6: db "how are you", 0
.p7: db "do you dream", 0
.p8: db "bye", 0

ReiKeys:
    db "abcdefghi"
    db "jklmnopqr"
    db "stuvwxyz "
    db ".,!?'-;: "                   ; the last cell is the OK key, not a character

sReiHintSay:   db "A:say", 0
sReiHintMore:  db T_ARROW_L + FONT_FIRST, T_ARROW_R + FONT_FIRST, "more", 0
sReiListTitle: db "SAY", 0
sReiKeysTitle: db "KEYS", 0
sReiToKeys:    db "SEL:keys", 0
sReiToList:    db "SEL:list", 0
sReiToLog:     db "START:log", 0

; hl = the chosen prompt's text.
ReiIn_Prompt:
    ld a, [wReiPage]
    ld b, a
    add a, a
    add a, b                        ; page * IN_PER
    ld hl, wReiPick
    add a, [hl]
    add a, a
    ld e, a
    ld d, 0
    ld hl, ReiPrompts
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
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
    jr nz, .typed
    call ReiIn_Prompt
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

; The keys' interior, into the shadow: the list or the keyboard.
ReiIn_DrawKeys:
    call ReiIn_FrameEdges
    xor a
    ld b, KEYS_X
    ld c, KEYS_Y
    ld d, KEYS_W
    ld e, KEYS_H
    call Rei_Fill
    ld a, [wReiMode]
    or a
    jr nz, .keyboard

    ld hl, sReiListTitle
    ld b, KEYS_FX + 2
    ld c, KEYS_FY
    call Rei_Print
    ld a, [wReiPick]                ; remember it: the rows below count in wReiPick
    push af
    xor a
.prompt
    ld [wReiPick], a
    call ReiIn_Prompt
    ld a, [wReiPick]
    add a, KEYS_Y
    ld c, a
    ld b, IN_LIST_X
    call Rei_Print
    ld a, [wReiPick]
    inc a
    cp IN_PER
    jr c, .prompt
    pop af
    ld [wReiPick], a
    add a, KEYS_Y                   ; the arrow beside the chosen one
    ld c, a
    ld b, KEYS_X
    call Rei_CellAddr
    ld [hl], T_ARROW_R
    ld hl, sReiToKeys
    ld b, KEYS_FX + KEYS_FW - 10
    ld c, KEYS_FY
    call Rei_Print
    ld hl, sReiHintSay
    ld b, KEYS_X
    ld c, KEYS_Y + IN_PER
    call Rei_Print
    ld hl, sReiHintMore
    ld b, KEYS_X + KEYS_W - 6
    ld c, KEYS_Y + IN_PER
    jp Rei_Print

.keyboard
    ld hl, sReiKeysTitle
    ld b, KEYS_FX + 2
    ld c, KEYS_FY
    call Rei_Print
    ld hl, sReiToList
    ld b, KEYS_FX + KEYS_FW - 10
    ld c, KEYS_FY
    call Rei_Print
    ld b, IN_KEY_X
    ld c, KEYS_Y
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
    ld c, KEYS_Y + IN_ROWS - 1
    call Rei_CellAddr
    ld [hl], T_OK
    ret

; The keys frame's top and bottom edges, plain, and START's hint: the titles
; are laid over them.
ReiIn_FrameEdges:
    ld a, T_FR_T
    ld b, KEYS_FX + 1
    ld c, KEYS_FY
    ld d, KEYS_FW - 2
    ld e, 1
    call Rei_Fill
    ld a, T_FR_B
    ld b, KEYS_FX + 1
    ld c, KEYS_FY + KEYS_FH - 1
    ld d, KEYS_FW - 2
    ld e, 1
    call Rei_Fill
    ld hl, sReiToLog
    ld b, KEYS_FX + KEYS_FW - 11
    ld c, KEYS_FY + KEYS_FH - 1
    jp Rei_Print

; The cursor's palette: everything inside the frame plain, then the pick.
; a = 0 to leave nothing picked. Must run inside VBlank.
ReiIn_Attrs:
    push af
    ld a, PAL_GREEN
    ld b, KEYS_X
    ld c, KEYS_Y
    ld d, KEYS_W
    ld e, KEYS_H
    call Rei_Attr
    pop af
    or a
    ret z
    ld a, [wReiMode]
    or a
    jr nz, .key
    ld a, [wReiPick]
    add a, KEYS_Y
    ld c, a
    ld b, KEYS_X
    ld d, KEYS_W
    ld e, 1
    ld a, PAL_PICK
    jp Rei_Attr
.key
    ld a, [wReiKey]
    ld c, KEYS_Y
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
    ld e, 1
    ld a, PAL_PICK
    jp Rei_Attr

; Shadow -> screen for everything this file draws. a = 0 hides the cursor.
ReiIn_Refresh::
    push af
    call ReiIn_DrawSay
    call ReiIn_DrawKeys
    call Console_WaitVBlank
    ld hl, KEYS_FY * CON_W + KEYS_FX
    ld b, KEYS_FH
    ld c, KEYS_FW
    call Rei_Blit
    call Console_WaitVBlank
    ld hl, SAY_Y * CON_W + SAY_X
    ld b, 1
    ld c, SAY_W
    call Rei_Blit
    pop af
    jp ReiIn_Attrs

; The INPUT state. Returns with the message in wPromptText / wPromptLen, still
; showing on the prompt row, and already in the log.
ReiUi_Input::
    xor a
    ld [wReiTextLen], a
    inc a
    ld [wReiCaret], a
.redraw
    ld a, 1
    call ReiIn_Refresh
.loop
    call Rei_IdleFrame
    or a
    jr z, .loop
    ld b, a
    and KB_START
    jr z, :+
    call ReiLog_Run                 ; comes back on SELECT, this screen untouched
    jr .loop
:   ld a, b
    and KB_SELECT
    jr z, :+
    ld a, [wReiMode]
    xor 1
    ld [wReiMode], a
    jr .redraw
:   ld a, [wReiMode]
    or a
    jr nz, .keyboard

    ; --- the list ---
    ld a, b
    and KB_A
    jr nz, .sendPrompt
    ld a, b
    and KB_LEFT | KB_RIGHT
    jr nz, .turn
    ld a, b
    and KB_UP
    jr z, .listDown
    ld a, [wReiPick]
    or a
    jr z, .older                    ; off the top: her reply before this one
    dec a
    jr .picked
.listDown
    ld a, b
    and KB_DOWN
    jr z, .loop
    ld a, [wReiPick]
    cp IN_PER - 1
    jr z, .newer                    ; off the bottom: the one after
    inc a
.picked
    ld [wReiPick], a
    jr .redraw
.turn                               ; the pages go round
    ld a, b
    and KB_LEFT
    ld a, [wReiPage]
    jr z, .turnOn
    or a
    jr nz, :+
    ld a, IN_PAGES
:   dec a
    jr .turned
.turnOn
    inc a
    cp IN_PAGES
    jr c, .turned
    xor a
.turned
    ld [wReiPage], a
    jr .redraw

.older
    call ReiHist_Older
    jr .loop
.newer
    call ReiHist_Newer
    jr .loop

.sendPrompt
    call ReiIn_Prompt
    ld de, wPromptText
    ld c, 0
.copyPrompt
    ld a, [hl+]
    or a
    jp z, .staged
    ld [de], a
    inc de
    inc c
    jr .copyPrompt

    ; --- the keyboard ---
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
    jr z, .keyUp
    ld a, c
    cp IN_CELLS - IN_COLS
    jr nc, .newer                   ; off the bottom row
    ld e, IN_COLS
    jr .move
.keyUp
    ld a, b
    and KB_UP
    jp z, .loop
    ld a, c
    cp IN_COLS
    jr c, .older                    ; off the top row
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

ENDC
