; Rei's main screen: the tiles, the palettes, the four frames, and the small
; drawing routines the rest of the UI bank uses.
;
; Everything is drawn into the console shadow (wConsole, tile numbers at the
; BG map's 32-byte stride) and reaches VRAM one of two ways: the whole map by
; GDMA while the LCD is off (the splash and the first draw of this screen), or
; a rectangle by Rei_Blit inside VBlank. Palettes are per region, through the
; CGB attribute map, written straight to VRAM bank 1 under the same rule.
;
; Cost: nothing in ROM0. About 2.6 KB of the UI bank, nearly all of it art.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"

SECTION "Rei screen", ROMX, BANK[REI_BANK]

DEF REI_ART_DATA EQU 1
INCLUDE "rei_art.inc"

ReiFrameTop: db T_FR_TL, T_FR_T, T_FR_TR
ReiFrameMid: db T_FR_L, 0, T_FR_R
ReiFrameBot: db T_FR_BL, T_FR_B, T_FR_BR

sReiTitleOut: db "REI", 0
sReiTitleSay: db "YOU", 0

; Switches the LCD off, at the start of VBlank as the hardware requires.
ReiScr_LcdOff::
    ldh a, [rLCDC]
    bit B_LCDC_ENABLE, a
    ret z
    call Console_WaitVBlank
    xor a
    ldh [rLCDC], a
    ret

; Pushes the whole shadow and switches the LCD on. LCD off on entry.
ReiScr_LcdOn::
    call Console_FlushNow
    ld a, REI_LCDC
    ldh [rLCDC], a
    ret

; hl = tile data, bc = bytes. Loads a tile set at REI_TILE_BASE. LCD off.
ReiScr_LoadTiles::
    ld de, TILEBLOCK0 + REI_TILE_BASE * 16
    jp CopyBytes

; hl = eight palettes. LCD off, or inside VBlank.
ReiScr_LoadPals::
    ld a, BGPI_AUTOINC
    ldh [rBCPS], a
    ld b, 8 * 8
.loop
    ld a, [hl+]
    ldh [rBCPD], a
    dec b
    jr nz, .loop
    ret

; The shadow, all blank.
ReiScr_Clear::
    ld hl, wConsole
    ld bc, CON_SIZE
.loop
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .loop
    ret

; b = column, c = row -> hl = the shadow cell. Changes a, de, hl.
Rei_CellAddr::
    ld l, c
    ld h, 0
REPT 5
    add hl, hl
ENDR
    ld a, b
    or l
    ld l, a
    ld de, wConsole
    add hl, de
    ret

; hl = $00-terminated text, b = column, c = row. A byte is a tile number plus
; FONT_FIRST, so ASCII prints as itself and T_x + FONT_FIRST is a piece of art.
Rei_Print::
    push hl
    call Rei_CellAddr
    ld d, h
    ld e, l
    pop hl
.loop
    ld a, [hl+]
    or a
    ret z
    sub FONT_FIRST
    ld [de], a
    inc de
    jr .loop

; a = tile, b = column, c = row, d = width, e = height.
Rei_Fill::
    push af
    push de
    call Rei_CellAddr
    pop de
    pop af
.row
    push hl
    ld b, d
.cell
    ld [hl+], a
    dec b
    jr nz, .cell
    pop hl
    ld bc, CON_W
    add hl, bc
    dec e
    jr nz, .row
    ret

; b = column, c = row, d = width, e = height: a one-tile frame, blank inside.
Rei_Frame::
    push de
    call Rei_CellAddr
    pop de
    ld bc, ReiFrameTop
    call .row
    dec e
    dec e
.mid
    ld bc, ReiFrameMid
    call .row
    dec e
    jr nz, .mid
    ld bc, ReiFrameBot
.row
    push hl
    push de
    ld a, [bc]
    ld [hl+], a
    inc bc
    dec d
    dec d
    ld a, [bc]
.fill
    ld [hl+], a
    dec d
    jr nz, .fill
    inc bc
    ld a, [bc]
    ld [hl], a
    pop de
    pop hl
    ld bc, CON_W
    add hl, bc
    ret

; hl = tile numbers, row-major; b = column, c = row, d = width, e = height.
Rei_DrawMap::
    push hl
    push de
    call Rei_CellAddr
    pop de
    ld b, h
    ld c, l
    pop hl
.row
    push bc
    push de
.cell
    ld a, [hl+]
    ld [bc], a
    inc bc
    dec d
    jr nz, .cell
    pop de
    pop bc
    ld a, c
    add a, CON_W
    ld c, a
    jr nc, :+
    inc b
:   dec e
    jr nz, .row
    ret

; a = attribute (a palette number), b = column, c = row, d = width,
; e = height. Straight into VRAM bank 1: LCD off, or inside VBlank and small.
Rei_Attr::
    push af
    ld l, c
    ld h, 0
REPT 5
    add hl, hl
ENDR
    ld a, b
    or l
    ld l, a
    ld bc, TILEMAP0
    add hl, bc
    ld a, 1
    ldh [rVBK], a
    pop af
.row
    push hl
    ld b, d
.cell
    ld [hl+], a
    dec b
    jr nz, .cell
    pop hl
    ld bc, CON_W
    add hl, bc
    dec e
    jr nz, .row
    xor a
    ldh [rVBK], a
    ret

; The pane's shadow blank and its cursor home. No VRAM.
Rei_PaneClear::
    xor a
    ld [wReiCol], a
    ld [wReiRow], a
    ld [wReiReplyLen], a
    ld b, PANE_X
    ld c, PANE_Y
    ld d, PANE_W
    ld e, PANE_H
    jp Rei_Fill                     ; a = 0, the blank

; One idle frame for the UI's loops: waits for VBlank, keeps her blinking,
; reads the pad. Returns a = the buttons newly pressed.
Rei_IdleFrame::
    call Console_WaitVBlank
    ld a, [wReiFaceDirty]
    or a
    jr z, :+
    xor a
    ld [wReiFaceDirty], a
    call Rei_FaceBlit
:   call Rei_BlinkTick
    call Joy_Read
    ld a, [wJoyNew]
    ret

; Draws the whole main screen, LCD off, and switches it on. Once, after the
; splash: from then on the screen is only ever touched a rectangle at a time.
ReiScr_Main::
    call ReiScr_LcdOff
    ld hl, ReiTilesMain
    ld bc, REI_MAIN_TILES * 16
    call ReiScr_LoadTiles
    ld hl, ReiPalMain
    call ReiScr_LoadPals
    call ReiScr_Clear

    xor a                           ; PAL_INK everywhere first
    ld b, a
    ld c, a
    ld d, CON_W
    ld e, CON_H
    call Rei_Attr

    ld b, FACE_FX
    ld c, FACE_FY
    ld d, FACE_FW
    ld e, FACE_FH
    call Rei_Frame
    ld a, PAL_FACE
    ld b, FACE_X
    ld c, FACE_Y
    ld d, FACE_W
    ld e, FACE_H
    call Rei_Attr

    ld b, OUT_FX
    ld c, OUT_FY
    ld d, OUT_FW
    ld e, OUT_FH
    call Rei_Frame
    ld a, PAL_RED
    ld b, OUT_FX
    ld c, OUT_FY
    ld d, OUT_FW
    ld e, OUT_FH
    call Rei_Attr
    ld hl, sReiTitleOut
    ld b, OUT_FX + 2
    ld c, OUT_FY
    call Rei_Print

    ld b, SAY_FX
    ld c, SAY_FY
    ld d, SAY_FW
    ld e, SAY_FH
    call Rei_Frame
    ld a, PAL_BLUE
    ld b, SAY_FX
    ld c, SAY_FY
    ld d, SAY_FW
    ld e, SAY_FH
    call Rei_Attr
    ld hl, sReiTitleSay
    ld b, SAY_FX + 2
    ld c, SAY_FY
    call Rei_Print

    ld b, KEYS_FX
    ld c, KEYS_FY
    ld d, KEYS_FW
    ld e, KEYS_FH
    call Rei_Frame
    ld a, PAL_GREEN
    ld b, KEYS_FX
    ld c, KEYS_FY
    ld d, KEYS_FW
    ld e, KEYS_FH
    call Rei_Attr

    xor a                           ; she has not spoken: calm, and an empty pane
    ld [wReiMood], a
    call ReiFace_Set
    call ReiFace_DrawMood
    call ReiFace_MoodAttr
    call Console_FlushNow
    call Rei_FaceBlit               ; after the flush, which knows no face
    ld a, REI_LCDC
    ldh [rLCDC], a
    ret

ENDC
