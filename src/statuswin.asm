; A two-line status bar, drawn on the window layer.
;
; The window is a second tilemap the PPU paints over the background, starting at
; (WX - 7, WY). Nothing about it touches the console's shadow buffer, which is
; the whole reason for using it here: generation cannot stop to redraw a status
; line, so the status line has to live somewhere generation never writes. The
; text scrolls underneath and the bar stays put.
;
; It is drawn in palette 1 - the inverse of palette 0, and the same attribute
; trick the keyboard cursor uses. Two palettes is all this ROM has ever needed.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"

; Three rows, and the top one is deliberately blank. The font has no padding
; above a capital, so text on the first row of the bar sits flush against its
; edge and reads as clipped. One empty inverted row turns it into a panel.
DEF WIN_ROWS  EQU 3
DEF WIN_Y     EQU (CON_H - WIN_ROWS) * 8
DEF WIN_CELLS EQU WIN_ROWS * CON_VIS_W

SECTION "Status window buffer", WRAM0
wWinBuf: ds WIN_CELLS

SECTION "Status window code", ROM0

; Shows the bar and hands it the bottom rows of the screen. The console has to
; be told to stop above it, or text scrolls into cells the window is covering
; and is never seen.
StatusWin_Show::
    ld a, CON_H - WIN_ROWS - 1
    ld [wConBottom], a

    call Console_WaitVBlank
    ld a, 1                         ; palette 1 across the bar, in VRAM bank 1
    ldh [rVBK], a
    ld hl, TILEMAP1
    ld c, WIN_ROWS
.attrRow
    ld b, CON_VIS_W
    push hl
.attrCell
    ld [hl], 1
    inc hl
    dec b
    jr nz, .attrCell
    pop hl
    ld de, 32
    add hl, de
    dec c
    jr nz, .attrRow
    xor a
    ldh [rVBK], a

    ld a, WIN_Y
    ldh [rWY], a
    ld a, 7                         ; WX is offset by 7; 7 means the left edge
    ldh [rWX], a
    call StatusWin_Set
    call StatusWin_Flush
    ldh a, [rLCDC]
    or LCDC_WIN_9C00 | LCDC_WIN_ON
    ldh [rLCDC], a
    ret

StatusWin_Hide::
    ldh a, [rLCDC]
    and ~LCDC_WINDOW
    ldh [rLCDC], a
    ld a, CON_H - 1
    ld [wConBottom], a              ; the console gets the whole screen back
    ret

StatusWin_Update::
    call StatusWin_Set
    ; fall through

; Pushes the two lines to the window tilemap. Small enough to write directly in
; VBlank without a DMA.
StatusWin_Flush::
    call Console_WaitVBlank
    ld hl, wWinBuf
    ld de, TILEMAP1
    ld c, WIN_ROWS
.row
    ld b, CON_VIS_W
.cell
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .cell
    ld a, e                         ; step to the next tilemap row
    add a, 32 - CON_VIS_W
    ld e, a
    jr nc, :+
    inc d
:   dec c
    jr nz, .row
    ret

; Rebuilds both lines from the generator's state.
StatusWin_Set::
    ld hl, wWinBuf
    ld b, WIN_CELLS
    ld a, ' ' - FONT_FIRST
.blank
    ld [hl+], a
    dec b
    jr nz, .blank

    ld hl, sWinCyc
    ld b, CON_VIS_W
    call Win_PutStr
    ld hl, wTokCycles
    ld b, CON_VIS_W + 8
    call Win_PutDec32

    ld hl, sWinTok
    ld b, CON_VIS_W * 2
    call Win_PutStr
    ld a, [wGenCount]
    ld [wNum + 0], a
    xor a
    ld [wNum + 1], a
    ld [wNum + 2], a
    ld [wNum + 3], a
    ld b, CON_VIS_W * 2 + 4
    call Win_PutDec32Num

    ld hl, sWinBack
    ld b, CON_VIS_W * 2 + 10
    jp Win_PutStr

; hl = $00-terminated string, b = cell index into wWinBuf.
Win_PutStr:
    ld a, [hl+]
    or a
    ret z
    push hl
    sub FONT_FIRST
    ld l, b
    ld h, 0
    ld de, wWinBuf
    add hl, de
    ld [hl], a
    pop hl
    inc b
    jr Win_PutStr

; hl = pointer to a 4-byte little-endian value, b = cell index.
Win_PutDec32:
    ld de, wNum
    ld c, 4
.copy
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .copy
    ; fall through

; wNum, rendered at cell index b.
Win_PutDec32Num:
    push bc
    call Dec32_Render
    pop bc
    ld hl, wDigits
    ld a, [wDigitLen]
    ld c, a
.out
    ld a, [hl+]
    push hl
    sub FONT_FIRST
    ld l, b
    ld h, 0
    push de
    ld de, wWinBuf
    add hl, de
    pop de
    ld [hl], a
    pop hl
    inc b
    dec c
    jr nz, .out
    ret

sWinCyc:  db "CYC/TOK", 0
sWinTok:  db "TOK", 0
sWinBack: db "START=MENU", 0
