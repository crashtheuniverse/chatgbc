; Screen furniture: a box frame, horizontal rules, and text placed by cell.
;
; Everything here writes straight into the console's shadow buffer rather than
; going through Console_PutChar. That is deliberate: PutChar advances a cursor
; and wraps at the screen edge, so drawing the bottom-right corner of a frame
; would scroll the whole screen out from under the frame being drawn.
;
; The box pieces are font tiles sitting just past the ASCII range (CH_* in
; chatgbc.inc), which costs eight glyphs and no second tileset.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "UI code", ROM0

; a = character, b = column, c = row. Preserves every register except a.
Ui_PutCell::
    push hl
    push bc
    push de
    push af
    ld l, c
    ld h, 0
REPT 5
    add hl, hl                      ; row * CON_W
ENDR
    ld c, b
    ld b, 0
    add hl, bc
    ld de, wConsole
    add hl, de
    pop af
    sub FONT_FIRST
    ld [hl], a
    pop de
    pop bc
    pop hl
    ret

; hl = $00-terminated string, b = column, c = row. $0A drops a row and returns
; to the starting column, so a block of text stays aligned inside a box.
Ui_PrintAt::
    ld d, b                         ; the column to come back to
.loop
    ld a, [hl+]
    or a
    ret z
    cp $0A
    jr nz, .put
    ld b, d
    inc c
    jr .loop
.put
    call Ui_PutCell
    inc b
    jr .loop

; c = row, d = left cap, e = right cap. Rules the full width of the box.
Ui_Rule::
    ld a, d
    ld b, 0
    call Ui_PutCell
    ld a, e
    ld b, BOX_R
    call Ui_PutCell
    ld b, 1
.fill
    ld a, CH_H
    call Ui_PutCell
    inc b
    ld a, b
    cp BOX_R
    jr c, .fill
    ret

; A full-screen box with the title set into its top edge.
Ui_Frame::
    ld c, 0
    ld d, CH_TL
    ld e, CH_TR
    call Ui_Rule
    ld c, BOX_B
    ld d, CH_BL
    ld e, CH_BR
    call Ui_Rule

    ld c, 1                         ; the two uprights
.side
    ld b, 0
    ld a, CH_V
    call Ui_PutCell
    ld b, BOX_R
    ld a, CH_V
    call Ui_PutCell
    inc c
    ld a, c
    cp BOX_B
    jr c, .side
    ; fall through, laying the title over the rule already drawn
    ld hl, sUiTitle
    ld b, TITLE_COL
    ld c, 0
    jp Ui_PrintAt

; Mixed case, on the handheld as everywhere else. It is a name, not a label.
IF CHAT_MODE
sUiTitle: db " Rei v0.1 ", 0
ELSE
sUiTitle: db " ChatGBC v0.9 ", 0
ENDC
