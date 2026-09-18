; Rei's text pane and her face: the part of the screen that changes while the
; model is thinking, and so the part that has to live in ROM0.
;
; The forward pass remaps ROM banks all the time, and the teletype's VBlank
; handler interrupts it wherever it happens to be. Everything the handler can
; reach is therefore here: the pane's character writer (wrap, scroll), the
; two copies into VRAM (pane, face) and the blink counter. Nothing here touches
; rROMB0, rSVBK or rVBK. Everything else about the screen is in the UI bank.
;
; The pane is a 12 x 7 window of the console shadow (wConsole, the same 32-wide
; map the story build uses). Writing a character only changes the shadow and
; raises wReiPaneDirty; Rei_PaneBlit copies the 84 cells to VRAM inside VBlank,
; about 1,050 cycles of the 2,280 a double-speed VBlank has. The face is 16
; cells, about 250. The handler does one of the two per frame, never both.
;
; Wrapping is by word: when a word runs into the right edge, the letters it has
; so far move down to the next row. A row never starts with a space. When the
; seventh row is full the pane scrolls up one row inside its frame.
;
; Cost: about 330 bytes of ROM0, 170 bytes of WRAM0.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"

SECTION "Rei pane state", WRAM0
wReiCol::       db                  ; where the next character lands
wReiRow::       db
wReiPaneDirty:: db                  ; the shadow pane is ahead of VRAM
wReiFaceDirty:: db                  ; wReiFaceSel is ahead of VRAM
wReiFaceSel::   db                  ; FSEL_*: which of wReiFaces to show
wReiTalking::   db                  ; characters move her mouth
wReiBlinkT::    db                  ; VBlanks, wrapping: a blink every 256
wReiReplyLen::  db
wReiReply::     ds REI_REPLY_MAX    ; the reply as text, for mood and history
wReiFaces::     ds 4 * FACE_CELLS   ; idle, blink, mouth shut, mouth open

SECTION "Rei pane code", ROM0

; hl = the shadow address of the start of the current pane row.
Rei_PaneRowAddr:
    ld a, [wReiRow]
    add a, PANE_Y
    ld l, a
    ld h, 0
REPT 5
    add hl, hl                      ; row * CON_W
ENDR
    ld de, wConsole + PANE_X
    add hl, de
    ret

; a = character. Writes it into the pane's shadow and keeps it as text. The
; newline that ends a turn is not drawn: the pane holds one reply.
Rei_PanePut::
    cp $0A
    ret z
    ld b, a

    ld a, [wReiReplyLen]            ; the text, as the model said it
    cp REI_REPLY_MAX
    jr nc, .kept
    ld e, a
    ld d, 0
    ld hl, wReiReply
    add hl, de
    ld [hl], b
    inc a
    ld [wReiReplyLen], a
.kept
    ld a, [wReiCol]
    or a
    jr nz, .inRow
    ld a, b                         ; a row does not start with a space
    cp ' '
    ret z
    jr .put
.inRow
    cp PANE_W
    jr c, .put
    ld a, b                         ; the row is full. A space there is the
    cp ' '                          ; line break itself: the word ended with
    jp z, Rei_PaneNewline           ; the row and nothing is carried down
    push bc
    call Rei_PaneWrap
    pop bc
.put
    call Rei_PaneRowAddr
    ld a, [wReiCol]
    ld e, a
    ld d, 0
    add hl, de
    ld a, b
    sub FONT_FIRST
    ld [hl], a
    ld a, e
    inc a
    ld [wReiCol], a
    ld a, 1
    ld [wReiPaneDirty], a

    ld a, [wReiTalking]             ; a letter moves her mouth, a space rests it
    or a
    ret z
    ld a, b
    cp ' '
    ret z
    ld a, [wReiFaceSel]
    cp FSEL_TALK_A
    ld a, FSEL_TALK_B
    jr z, :+
    ld a, FSEL_TALK_A
:   ld [wReiFaceSel], a
    ld a, 1
    ld [wReiFaceDirty], a
    ret

; The row is full and another letter is coming. Starts a new row and carries
; the unfinished word down to it, unless the word is the whole row.
Rei_PaneWrap:
    call Rei_PaneRowAddr
    ld de, PANE_W - 1
    add hl, de                      ; the last cell of the row
    ld c, 0                         ; c = letters after the last space
.scan
    ld a, [hl]
    or a                            ; tile 0 is the space
    jr z, .found
    dec hl
    inc c
    ld a, c
    cp PANE_W
    jr c, .scan
    ld c, 0                         ; no space at all: break where it is
.found
    push bc
    call Rei_PaneNewline
    pop bc
    ld a, c
    ld [wReiCol], a
    or a
    ret z
    call Rei_PaneRowAddr            ; hl = the new row; the old one is CON_W back
    ld d, h
    ld e, l
    ld a, PANE_W - CON_W
    sub c                           ; -(CON_W - PANE_W + c): the word's start
    ld l, a
    ld h, $FF
    add hl, de
.carry
    ld a, [hl]
    ld [de], a
    ld [hl], 0
    inc hl
    inc de
    dec c
    jr nz, .carry
    ret

; Column 0 of the next row; scrolls the shadow pane when there is none.
Rei_PaneNewline:
    xor a
    ld [wReiCol], a
    ld a, [wReiRow]
    inc a
    cp PANE_H
    jr nc, .scroll
    ld [wReiRow], a
    ret
.scroll
    ld hl, wConsole + PANE_OFF + CON_W
    ld de, wConsole + PANE_OFF
    ld b, PANE_H - 1
.row
    ld c, PANE_W
.cell
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .cell
    ld a, CON_W - PANE_W
    add a, l
    ld l, a
    jr nc, :+
    inc h
:   ld a, CON_W - PANE_W
    add a, e
    ld e, a
    jr nc, :+
    inc d
:   dec b
    jr nz, .row
    ld b, PANE_W                    ; de = the last row: blank it
    xor a
.blank
    ld [de], a
    inc de
    dec b
    jr nz, .blank
    ret

; Copies the pane from the shadow to the BG map. VBlank only.
Rei_PaneBlit::
    ld hl, PANE_OFF
    ld b, PANE_H
    ld c, PANE_W
    ; fall through

; hl = offset into the map, b = rows, c = columns: shadow -> VRAM. VBlank only,
; ten cycles a cell - keep a call under about 150 cells.
Rei_Blit::
    push hl
    ld de, wConsole
    add hl, de
    ld d, h
    ld e, l                         ; de = source
    pop hl
    push de
    ld de, TILEMAP0
    add hl, de                      ; hl = destination
    pop de
.row
    push bc
.cell
    ld a, [de]
    ld [hl+], a
    inc de
    dec c
    jr nz, .cell
    pop bc
    ld a, CON_W
    sub c                           ; to the same column of the next row
    push bc
    ld c, a
    ld b, 0
    add hl, bc
    add a, e
    ld e, a
    jr nc, :+
    inc d
:   pop bc
    dec b
    jr nz, .row
    ret

; Shows the picture wReiFaceSel names. VBlank only.
Rei_FaceBlit::
    ld a, [wReiFaceSel]
    swap a                          ; * FACE_CELLS
    ld e, a
    ld d, 0
    ld hl, wReiFaces
    add hl, de
    ld d, h
    ld e, l
    ld hl, TILEMAP0 + FACE_Y * CON_W + FACE_X
    ld b, FACE_H
.row
    ld c, FACE_W
.cell
    ld a, [de]
    ld [hl+], a
    inc de
    dec c
    jr nz, .cell
    ld a, CON_W - FACE_W
    add a, l
    ld l, a
    jr nc, :+
    inc h
:   dec b
    jr nz, .row
    ret

; Once per VBlank. Her eyes close for six frames every 256, unless she is
; talking - then the face belongs to her mouth.
Rei_BlinkTick::
    ld a, [wReiTalking]
    or a
    ret nz
    ld hl, wReiBlinkT
    inc [hl]
    ld a, [hl]
    or a
    ld b, FSEL_BLINK
    jr z, .show
    cp 6
    ret nz
    ld b, FSEL_IDLE
.show
    ld a, b
    ld [wReiFaceSel], a
    ld a, 1
    ld [wReiFaceDirty], a
    ret

ASSERT FACE_CELLS == 16, "Rei_FaceBlit multiplies by swap"

ENDC
