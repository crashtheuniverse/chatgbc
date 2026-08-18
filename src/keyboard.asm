; On-screen keyboard: d-pad picks a character, A adds it, SELECT flips case,
; START generates. Laid out like the Pokemon name-entry screen - letters spaced
; two columns apart so the cursor has room to read as a highlight - and set
; inside a framed screen drawn by src/ui.asm.
;
; The cursor is drawn with CGB background attributes rather than a second font:
; moving it is two byte writes to VRAM bank 1 (clear the old cell, set the new),
; with palette 1 defined as the inverse of palette 0. The tilemap never changes
; as the cursor moves, so there is no extra GDMA and no shadow buffer.
;
; Exactly one attribute cell is ever set, tracked by wKbPrev. Anything that
; leaves the screen has to clear it, or an inverted cell is stranded in VRAM and
; shows up as a black block over whatever is drawn there next.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; Writing a 0 to a select bit enables that half of the button matrix.
DEF P1F_GET_DPAD EQU 1 << B_JOYP_GET_BUTTONS
DEF P1F_GET_BTN  EQU 1 << B_JOYP_GET_CTRL_PAD
DEF P1F_GET_NONE EQU (1 << B_JOYP_GET_BUTTONS) | (1 << B_JOYP_GET_CTRL_PAD)

DEF KB_COLS  EQU 9
DEF KB_ROWS  EQU 4
DEF KB_STEP  EQU 2                  ; columns between characters
DEF KB_STEP_Y EQU 2                 ; and rows between them, so descenders on
                                    ; j/p/q/y do not run into the row below
DEF KB_CELLS EQU KB_COLS * KB_ROWS
DEF KB_PROMPTS EQU 8

; Screen rows, top to bottom: title border, prompt, rule, grid, rule, hints,
; bottom border. KB_COL0 is the left margin everything inside the box lines up
; to, and the grid's 9 cells at KB_STEP apart end one column short of the wall.
DEF KB_COL0    EQU 2
DEF KB_PROMPT  EQU 2                ; prompt occupies rows 2..4
DEF KB_SEP_A   EQU 5
DEF KB_TOP     EQU 6                ; grid on rows 6, 8, 10, 12
DEF KB_SEP_B   EQU 13
DEF KB_HELP    EQU 14

SECTION "Keyboard state", WRAM0
wKbCursor:: db
wKbPrev::   db                      ; the one cell currently holding attribute 1
wKbCase::   db                      ; 0 = lower, 1 = upper
wJoyHeld:   db
wJoyNew::   db
wKbSeen::   db                      ; nonzero once the opening prompt has been shown
wRng::      db

SECTION "Keyboard code", ROM0

; The last cell of the third row is a real space - the prompt is a sentence, so
; a keyboard without one can only ever type a single word. Kb_Draw shows it as
; an underscore, since a blank cell would look like a hole in the grid.
KbLower:
    db "abcdefghi"
    db "jklmnopqr"
    db "stuvwxyz "
    db ".,!?'-;:\""
KbUpper:
    db "ABCDEFGHI"
    db "JKLMNOPQR"
    db "STUVWXYZ "
    db ".,!?'-;:\""

; Reads the pad and leaves newly-pressed buttons in wJoyNew.
Joy_Read::
    ld a, P1F_GET_DPAD
    ldh [rJOYP], a
REPT 6
    ldh a, [rJOYP]                  ; the matrix needs a moment to settle
ENDR
    cpl
    and $0F
    swap a
    ld b, a
    ld a, P1F_GET_BTN
    ldh [rJOYP], a
REPT 6
    ldh a, [rJOYP]
ENDR
    cpl
    and $0F
    or b
    ld b, a
    ld a, [wJoyHeld]
    xor b
    and b                           ; pressed now and not before
    ld [wJoyNew], a
    ld a, b
    ld [wJoyHeld], a
    ld a, P1F_GET_NONE
    ldh [rJOYP], a
    ret

; hl = the active layout table.
Kb_Layout:
    ld a, [wKbCase]
    or a
    ld hl, KbLower
    ret z
    ld hl, KbUpper
    ret

; hl = VRAM address of grid cell a.
Kb_CellAddr:
    ld c, KB_TOP
.rows
    cp KB_COLS
    jr c, .haveRow
    sub a, KB_COLS
    inc c
    inc c                           ; KB_STEP_Y
    jr .rows
.haveRow
    add a, a                        ; column = KB_COL0 + index * KB_STEP
    add a, KB_COL0
    ld b, a
    ld a, c
    ld l, a
    ld h, 0
REPT 5
    add hl, hl                      ; row * 32
ENDR
    ld a, b
    add a, l
    ld l, a
    jr nc, :+
    inc h
:   ld de, TILEMAP0
    add hl, de
    ret

; Writes attribute a to grid cell b. Must run inside VBlank.
Kb_SetAttr:
    push af
    ld a, b
    call Kb_CellAddr
    ld a, 1
    ldh [rVBK], a
    pop af
    ld [hl], a
    xor a
    ldh [rVBK], a
    ret

; Clears the stranded attribute cell. Every exit from this screen calls it.
Kb_ClearCursor::
    call Console_WaitVBlank
    ld a, [wKbPrev]
    ld b, a
    xor a
    jp Kb_SetAttr

Kb_DrawCursor:
    call Console_WaitVBlank
    ld a, [wKbPrev]                 ; un-highlight wherever it was
    ld b, a
    xor a
    call Kb_SetAttr
    ld a, [wKbCursor]
    ld b, a
    ld a, 1                         ; palette 1 = inverted
    call Kb_SetAttr
    ld a, [wKbCursor]
    ld [wKbPrev], a
    ret

; Redraws the entry screen from wPromptText. Touches the tilemap only, so the
; cursor attribute survives and must not be forgotten by the caller.
Kb_Draw::
    call Console_Clear
    call Ui_Frame
    ld c, KB_SEP_A                  ; the prompt and the grid are separate things
    ld d, CH_LT
    ld e, CH_RT
    call Ui_Rule
    ld c, KB_SEP_B                  ; and so are the grid and the button hints
    ld d, CH_LT
    ld e, CH_RT
    call Ui_Rule

    ld hl, wPromptText              ; the prompt, wrapped inside the box
    ld b, KB_COL0
    ld c, KB_PROMPT
    ld a, [wPromptLen]
    ld e, a
    or a
    jr z, .caret
.text
    ld a, [hl+]
    call Kb_PutWrapped
    dec e
    jr nz, .text
.caret
    ld a, '_'                       ; shows where the next letter lands
    call Kb_PutWrapped

    call Kb_Layout                  ; the grid, spaced KB_STEP apart
    ld c, KB_TOP
.row
    ld b, KB_COL0
    ld d, KB_COLS
.cell
    ld a, [hl+]
    cp ' '
    jr nz, :+
    ld a, '_'                       ; the space key needs something to look at
:   call Ui_PutCell
    inc b
    inc b
    dec d
    jr nz, .cell
    inc c
    inc c                           ; KB_STEP_Y
    ld a, c
    cp KB_TOP + KB_ROWS * KB_STEP_Y
    jr c, .row

    ld hl, sKbHelp
    ld b, KB_COL0
    ld c, KB_HELP
    jp Ui_PrintAt

; a = character, b = column, c = row. Draws it and steps right, wrapping at the
; box wall rather than at the screen edge.
Kb_PutWrapped:
    call Ui_PutCell
    inc b
    ld a, b
    cp BOX_R
    ret c
    ld b, KB_COL0
    inc c
    ret

; Runs the entry screen until START, leaving text in wPromptText/wPromptLen.
Keyboard_Run::
    call Kb_PickPrompt              ; opens with a prompt rather than a blank line
    ld de, wPromptText
    ld b, 0
.fill
    ld a, [hl+]
    or a
    jr z, .filled
    ld [de], a
    inc de
    inc b
    jr .fill
.filled
    ld a, b
    ld [wPromptLen], a
    xor a
    ld [wKbCursor], a
    ld [wKbPrev], a
    ld [wKbCase], a
    ld [wJoyHeld], a
    call Kb_Draw
    call Console_Flush
    call Kb_DrawCursor

.loop
    call Console_WaitVBlank
    call Joy_Read
    ld a, [wJoyNew]
    or a
    jp z, .loop

    ld b, a
    and KB_START
    jr z, :+
    call Kb_ClearCursor             ; never leave an inverted cell behind
    ret
:
    ld a, b
    and KB_SELECT
    jr nz, .flipCase
    ld a, b
    and KB_A
    jr nz, .add
    ld a, b
    and KB_B
    jr nz, .del

    ld a, [wKbCursor]               ; movement
    ld c, a
    ld a, b
    and KB_RIGHT
    jr z, :+
    ld a, c
    inc a
    cp KB_CELLS
    jr c, .move
    xor a
    jr .move
:   ld a, b
    and KB_LEFT
    jr z, :+
    ld a, c
    or a
    jr nz, .decCursor
    ld a, KB_CELLS
.decCursor
    dec a
    jr .move
:   ld a, b
    and KB_UP
    jr z, :+
    ld a, c
    sub a, KB_COLS
    jr nc, .move
    add a, KB_CELLS
    jr .move
:   ld a, b
    and KB_DOWN
    jp z, .loop
    ld a, c
    add a, KB_COLS
    cp KB_CELLS
    jr c, .move
    sub a, KB_CELLS
.move
    ld [wKbCursor], a
    call Kb_DrawCursor
    jp .loop

.flipCase
    ld a, [wKbCase]
    xor 1
    ld [wKbCase], a
    jr .redraw
.add
    ld a, [wPromptLen]
    cp PROMPT_MAX
    jp nc, .loop
    ld c, a
    ld b, 0
    ld hl, wPromptText
    add hl, bc
    push hl
    call Kb_Layout
    ld a, [wKbCursor]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    pop hl
    ld [hl], a
    ld a, [wPromptLen]
    inc a
    ld [wPromptLen], a
    jr .redraw
.del
    ld a, [wPromptLen]
    or a
    jp z, .loop
    dec a
    ld [wPromptLen], a
.redraw
    call Kb_Draw
    call Console_Flush
    call Kb_DrawCursor              ; wKbPrev still names the stale cell
    jp .loop

; hl = one of the starter prompts, so a tester has something new to try.
;
; The first one is always the same, deliberately. A fixed opening prompt is what
; lets the golden-token test assert on an exact sequence and what makes a
; screenshot reproducible. Every later visit is stirred by rDIV, which by then
; carries however long the player spent on the previous screen - genuinely
; unpredictable, unlike rDIV at boot, which reads the same on every run. There
; is no save RAM and no clock, so that is as much entropy as this cartridge has.
Kb_PickPrompt:
    ld a, [wKbSeen]
    or a
    jr nz, .roll
    inc a
    ld [wKbSeen], a
    xor a
    jr .fetch
.roll
    call Kb_Rand
    and KB_PROMPTS - 1
.fetch
    add a, a
    ld l, a
    ld h, 0
    ld de, KbPrompts
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ret

; An 8-bit linear congruential step, stirred with the divider.
Kb_Rand:
    ld a, [wRng]
    ld b, a
    add a, a
    add a, a
    add a, b                        ; 5x
    inc a
    ld b, a
    ldh a, [rDIV]
    xor b
    ld [wRng], a
    ret

KbPrompts:
    dw sP0, sP1, sP2, sP3, sP4, sP5, sP6, sP7
sP0: db "Once upon a time", 0
sP1: db "The little dog", 0
sP2: db "Lily and Tom went", 0
sP3: db "One day a boy", 0
sP4: db "In the big forest", 0
sP5: db "The cat saw a", 0
sP6: db "Anna wanted to", 0
sP7: db "There was a tiny", 0
sKbHelp:    db "SELECT abc/ABC", $0A, "A ADD    B DEL", $0A, "START GENERATE", 0
