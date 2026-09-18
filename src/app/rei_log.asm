; The conversation log: both sides, in order, on a screen of its own.
;
; Every line said - the player's as it is sent, hers when her reply is whole -
; is wrapped by word to 18 columns and appended to a ring of 64 rows in the save
; image (WRAM bank 2), so the log is saved with everything else. A row is a who
; byte (0 hers, 1 the player's) and 18 tile numbers; the player's first row
; opens with "> ".
;
; START opens the log from the input screen. It is drawn into a shadow of its
; own and sent to the second BG map ($9C00) - tiles, then attributes, two GDMAs
; in one VBlank - and LCDC is pointed at that map. The main screen at $9800 is
; never touched, so SELECT returns to it exactly as it was by pointing LCDC
; back. UP and DOWN scroll a row at a time and repeat while held; the newest row
; is at the bottom when the log opens. The player's rows are in blue
; (PAL_YOURS), hers in ink; small arrows in the frame say there is more.
;
; Cost: nothing in ROM0; about 570 bytes of the UI bank, 8 bytes of WRAM0 and
; 1,152 of WRAM bank 2 for the shadow (the rows themselves are in the image).

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

DEF LOG_ROWS   EQU CON_H - 2        ; rows of text inside the frame
DEF LOG_FIRST  EQU 16               ; frames before a held button repeats
DEF LOG_REPEAT EQU 3                ; and between repeats

SECTION "Rei log state", WRAM0
wReiLogCount:: db                   ; rows in the ring, up to REI_LOG_LINES
wReiLogNext::  db                   ; the slot the next row goes in
wReiLogTop:    db                   ; the first row showing, counted from the oldest
wReiLogRow:    dw                   ; ReiLog_Add: the row being written (its tiles)
wReiLogCol:    db
wReiLogWho:    db
wReiLogHold:   db                   ; frames until a held button repeats

SECTION "Rei log shadow", WRAMX, BANK[REI_HIST_BANK], ALIGN[4]
wReiLogTiles: ds CON_SIZE           ; GDMA sources: 16-byte aligned
wReiLogAttrs: ds CON_SIZE

SECTION "Rei log", ROMX, BANK[REI_BANK]

sReiLogTitle: db "LOG", 0
sReiLogBack:  db "SEL:back", 0

; a = slot -> hl = its address in the ring.
ReiLog_Slot:
    ld hl, wReiLog
    and REI_LOG_LINES - 1
    ret z
    ld de, REI_LOG_SLOT
.next
    add hl, de
    dec a
    jr nz, .next
    ret

; A fresh row at the end of the ring: wReiLogRow, column 0.
ReiLog_NewRow:
    ld a, [wReiLogNext]
    call ReiLog_Slot
    ld a, [wReiLogWho]
    ld [hl+], a
    ld a, l
    ld [wReiLogRow + 0], a
    ld a, h
    ld [wReiLogRow + 1], a
    ld b, REI_LOG_COLS
    xor a
    ld [wReiLogCol], a
.blank
    ld [hl+], a
    dec b
    jr nz, .blank
    ld a, [wReiLogNext]
    inc a
    and REI_LOG_LINES - 1
    ld [wReiLogNext], a
    ld a, [wReiLogCount]
    cp REI_LOG_LINES
    ret nc
    inc a
    ld [wReiLogCount], a
    ret

; hl = the row being written.
ReiLog_RowAddr:
    ld a, [wReiLogRow + 0]
    ld l, a
    ld a, [wReiLogRow + 1]
    ld h, a
    ret

; a = character, into the row being written: the pane's wrap, 18 wide.
ReiLog_Put:
    sub FONT_FIRST
    ld b, a                         ; b = the tile; 0 is the space
    ld a, [wReiLogCol]
    or a
    jr nz, .inRow
    ld a, b                         ; a row does not start with a space
    or a
    ret z
    jr .store
.inRow
    cp REI_LOG_COLS
    jr c, .store
    ld a, b                         ; the row is full: a space is the break,
    or a
    jr z, ReiLog_NewRow
    call ReiLog_RowAddr             ; a letter takes its word down with it
    ld de, REI_LOG_COLS - 1
    add hl, de
    ld c, 0
.scan
    ld a, [hl]
    or a
    jr z, .found
    dec hl
    inc c
    ld a, c
    cp REI_LOG_COLS
    jr c, .scan
    ld c, 0
.found
    inc hl                          ; hl = the word's first letter
    push bc
    push hl
    call ReiLog_NewRow
    call ReiLog_RowAddr
    ld d, h
    ld e, l
    pop hl
    pop bc
    ld a, c
    ld [wReiLogCol], a
    or a
    jr z, .store
.carry
    ld a, [hl]
    ld [de], a
    ld [hl], 0
    inc hl
    inc de
    dec c
    jr nz, .carry
.store
    call ReiLog_RowAddr
    ld a, [wReiLogCol]
    ld e, a
    ld d, 0
    add hl, de
    ld [hl], b
    inc a
    ld [wReiLogCol], a
    ret

; hl = text, c = its length, b = who (0 hers, 1 the player's). Appends it.
ReiLog_Add::
    ld a, c
    or a
    ret z
    ld a, b
    ld [wReiLogWho], a
    ld a, REI_HIST_BANK
    ldh [rSVBK], a
    push hl
    push bc
    call ReiLog_NewRow
    ld a, [wReiLogWho]
    or a
    jr z, .text
    ld a, '>'
    call ReiLog_Put
    ld a, 2                         ; "> ": the space is already there
    ld [wReiLogCol], a
.text
    pop bc
    pop hl
.char
    ld a, [hl+]
    push hl
    push bc
    call ReiLog_Put
    pop bc
    pop hl
    dec c
    jr nz, .char
    ld a, 1
    ldh [rSVBK], a
    ret

; The rows from wReiLogTop, into the shadow, and the shadow to the second map.
ReiLog_Draw:
    xor a                           ; the text area blank and in ink
    ld b, 1
    ld c, 1
    ld d, REI_LOG_COLS
    ld e, LOG_ROWS
    call Rei_Fill
    ld hl, wReiLogAttrs + CON_W + 1
    ld c, LOG_ROWS
.inkRow
    ld b, REI_LOG_COLS
    xor a
.inkCell
    ld [hl+], a
    dec b
    jr nz, .inkCell
    ld de, CON_W - REI_LOG_COLS
    add hl, de
    dec c
    jr nz, .inkRow

    ld a, [wReiLogCount]            ; rows to draw: the count less the top, 16 at most
    ld hl, wReiLogTop
    sub [hl]
    cp LOG_ROWS
    jr c, :+
    ld a, LOG_ROWS
:   or a
    jr z, .marks
    ld c, a
    ld a, [wReiLogCount]            ; the first one's slot: next - count + top
    ld b, a
    ld a, [wReiLogNext]
    sub b
    add a, [hl]
    ld b, a                         ; b = slot (ReiLog_Slot masks it)
    ld de, wReiLogTiles + CON_W + 1
.row
    push bc
    push de
    ld a, b
    call ReiLog_Slot                ; hl = the row in the ring
    pop de
    ld a, [hl+]                     ; who
    or a
    jr z, :+
    ld a, PAL_YOURS
:   ld c, a
    ld b, REI_LOG_COLS
.cell
    ld a, [hl+]
    ld [de], a
    push de                         ; the same cell of the attribute shadow
    push hl
    ld hl, wReiLogAttrs - wReiLogTiles
    add hl, de
    ld [hl], c
    pop hl
    pop de
    inc de
    dec b
    jr nz, .cell
    ld a, CON_W - REI_LOG_COLS
    add a, e
    ld e, a
    jr nc, :+
    inc d
:   pop bc
    inc b
    dec c
    jr nz, .row

.marks                              ; more above, more below
    ld a, [wReiLogTop]
    or a
    ld a, T_FR_T
    jr z, :+
    ld a, T_ARROW_UP
:   ld [wReiLogTiles + BOX_R - 2], a
    call ReiLog_MaxTop
    ld hl, wReiLogTop
    cp [hl]
    ld a, T_FR_B
    jr z, :+
    ld a, T_ARROW_DN
:   ld [wReiLogTiles + BOX_B * CON_W + BOX_R - 2], a

    call Console_WaitVBlank
    ld hl, wReiLogTiles
    call .gdma
    ld a, 1
    ldh [rVBK], a
    ld hl, wReiLogAttrs
    call .gdma
    xor a
    ldh [rVBK], a
    ret
.gdma
    ld a, h
    ldh [rHDMA1], a
    ld a, l
    ldh [rHDMA2], a
    ld a, HIGH(TILEMAP1)
    ldh [rHDMA3], a
    xor a
    ldh [rHDMA4], a
    ld a, VDMA_LEN_MODE_GENERAL | ((CON_SIZE / 16) - 1)
    ldh [rHDMA5], a
    ret

; a = the largest wReiLogTop: the count less a screenful, or 0.
ReiLog_MaxTop:
    ld a, [wReiLogCount]
    sub LOG_ROWS
    ret nc
    xor a
    ret

; The log screen, until SELECT. Called from the input screen; returns to it.
ReiLog_Run::
    ld a, REI_HIST_BANK
    ldh [rSVBK], a
    ld a, LOW(wReiLogTiles)         ; Rei_Frame, Rei_Print and Rei_Fill draw
    ld [wReiShadow + 0], a          ; into the log's shadow for now
    ld a, HIGH(wReiLogTiles)
    ld [wReiShadow + 1], a
    ld hl, wReiLogAttrs             ; the whole screen in ink
    ld bc, CON_SIZE
.ink
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .ink
    ld b, 0
    ld c, 0
    ld d, CON_VIS_W
    ld e, CON_H
    call Rei_Frame
    ld hl, sReiLogTitle
    ld b, 2
    ld c, 0
    call Rei_Print
    ld hl, sReiLogBack
    ld b, 2
    ld c, BOX_B
    call Rei_Print

    call ReiLog_MaxTop              ; the newest row at the bottom
    ld [wReiLogTop], a
    call ReiLog_Draw
    ldh a, [rLCDC]
    or LCDC_BG_9C00
    ldh [rLCDC], a

.loop
    call Console_WaitVBlank
    call Joy_Read
    ld a, [wJoyNew]
    ld b, a
    and KB_SELECT
    jr nz, .leave
    ld a, b
    and KB_UP | KB_DOWN
    ld c, LOG_FIRST
    jr nz, .step
    ld a, [wJoyHeld]                ; held: count down to the next repeat
    and KB_UP | KB_DOWN
    jr z, .loop
    ld hl, wReiLogHold
    dec [hl]
    jr nz, .loop
    ld c, LOG_REPEAT
.step
    ld b, a                         ; b = which way
    ld a, c
    ld [wReiLogHold], a
    ld a, b
    and KB_UP
    ld a, [wReiLogTop]
    jr z, .down
    or a
    jr z, .loop
    dec a
    jr .moved
.down
    ld c, a
    call ReiLog_MaxTop
    cp c
    jr z, .loop
    ld a, c
    inc a
.moved
    ld [wReiLogTop], a
    call ReiLog_Draw
    jr .loop

.leave
    call Console_WaitVBlank
    ldh a, [rLCDC]
    and ~LCDC_BG_MAP
    ldh [rLCDC], a
    ld a, LOW(wConsole)
    ld [wReiShadow + 0], a
    ld a, HIGH(wConsole)
    ld [wReiShadow + 1], a
    ld a, 1
    ldh [rSVBK], a
    ret

ASSERT REI_LOG_LINES == 64, "slots are masked"

ENDC
