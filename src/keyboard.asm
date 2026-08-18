; On-screen keyboard: d-pad picks a character, A adds it, START generates.
;
; The cursor is drawn with CGB background attributes rather than a second font:
; moving it is two byte writes to VRAM bank 1 (clear the old cell, set the new),
; with palette 1 defined as the inverse of palette 0. No shadow buffer and no
; extra GDMA - the tilemap itself never changes as the cursor moves.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

DEF KB_COLS  EQU 20
DEF KB_ROWS  EQU 3
DEF KB_TOP   EQU 5                  ; screen row the grid starts on
DEF KB_CELLS EQU KB_COLS * KB_ROWS

; Writing a 0 to a select bit enables that half of the matrix.
DEF P1F_GET_DPAD EQU 1 << B_JOYP_GET_BUTTONS
DEF P1F_GET_BTN  EQU 1 << B_JOYP_GET_CTRL_PAD
DEF P1F_GET_NONE EQU (1 << B_JOYP_GET_BUTTONS) | (1 << B_JOYP_GET_CTRL_PAD)


SECTION "Keyboard state", WRAM0
wKbCursor:: db
wKbPrev:    db                      ; cell the cursor attribute is currently on
wJoyHeld:   db
wJoyNew::   db

SECTION "Keyboard code", ROM0

KbLayout:
    db "abcdefghijklmnopqrst"
    db "uvwxyz ABCDEFGHIJKLM"
    db "NOPQRSTUVWXYZ.,!?'-;"

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

; hl = VRAM address of cell `a` in the grid.
Kb_CellAddr:
    ld c, KB_TOP
.rows
    cp KB_COLS
    jr c, .haveRow
    sub a, KB_COLS
    inc c
    jr .rows
.haveRow
    ld b, a                         ; b = column, c = screen row
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

; Writes attribute a to the grid cell in b. Call inside VBlank.
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

Kb_DrawCursor:
    ld a, [wKbPrev]                 ; un-highlight the old cell
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

; Redraws the whole entry screen from wPromptText.
Kb_Draw::
    call Console_Clear
    ld hl, sKbTitle
    call Console_PrintStr

    ld b, 0                         ; prompt text on row 2
    ld c, 2
    call Console_SetPos
    ld a, [wPromptLen]
    or a
    jr z, .noText
    ld b, a
    ld hl, wPromptText
.text
    ld a, [hl+]
    push hl
    push bc
    call Console_PutChar
    pop bc
    pop hl
    dec b
    jr nz, .text
.noText
    ld a, '_'                       ; caret shows where the next letter lands
    call Console_PutChar

    ld b, 0                         ; the grid
    ld c, KB_TOP
    call Console_SetPos
    ld hl, KbLayout
    ld b, KB_CELLS
.grid
    ld a, [hl+]
    push hl
    push bc
    call Console_PutChar
    pop bc
    pop hl
    dec b
    jr nz, .grid

    ld b, 0
    ld c, KB_TOP + KB_ROWS + 1
    call Console_SetPos
    ld hl, sKbHelp
    jp Console_PrintStr

; Runs the entry screen until START. Leaves the text in wPromptText/wPromptLen.
Keyboard_Run::
    ld hl, sKbDefault               ; opens with a prompt rather than a blank line
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
    ret nz

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

.add
    ld a, [wPromptLen]
    cp PROMPT_MAX
    jp nc, .loop
    ld c, a
    ld b, 0
    ld hl, wPromptText
    add hl, bc
    ld a, [wKbCursor]
    ld c, a
    ld b, 0
    push hl
    ld hl, KbLayout
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
    xor a                           ; the redraw wiped the attribute
    ld [wKbPrev], a
    call Kb_DrawCursor
    jp .loop

sKbDefault: db "Once upon a time", 0
sKbTitle: db "CHATGBC", $0A, $0A, 0
sKbHelp:  db "A ADD   B DEL", $0A, "START = GENERATE", 0
