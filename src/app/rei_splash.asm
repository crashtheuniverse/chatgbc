; The splash: the "Rei" logotype, two lines about what she is, the engine's
; name and version, and PRESS START blinking until it is pressed.
;
; The logotype is 12 x 5 tiles from the splash tile set, which shares its VRAM
; range with the main screen's set; leaving the splash loads the other one.
; The blink is a palette, not a redraw: PRESS START's cells switch between the
; text palette and one whose four colours are all the background.
; The screen is 20 columns, so the two long lines are each set on two rows.
;
; Cost: nothing in ROM0; about 200 bytes of the UI bank and the splash art.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

DEF LOGO_X  EQU (CON_VIS_W - REI_LOGO_W) / 2
DEF LOGO_Y  EQU 1
DEF START_X EQU 4
DEF START_Y EQU 11
DEF START_W EQU 11

SECTION "Rei splash", ROMX, BANK[REI_BANK]

sSplashA: db "a being", 0
sSplashB: db "in a cartridge", 0
sSplashStart: db "PRESS START", 0
sSplashC: db "ChatGBC engine", 0
sSplashD: db "v1.0.0", 0

ReiUi_Splash::
    call ReiScr_LcdOff
    ld hl, ReiTilesSplash
    ld bc, REI_SPLASH_TILES * 16
    call ReiScr_LoadTiles
    ld hl, ReiPalSplash
    call ReiScr_LoadPals
    call ReiScr_Clear
    xor a                           ; PAL_S_TEXT everywhere
    ld b, a
    ld c, a
    ld d, CON_W
    ld e, CON_H
    call Rei_Attr

    ld hl, ReiLogoMap
    ld b, LOGO_X
    ld c, LOGO_Y
    ld d, REI_LOGO_W
    ld e, REI_LOGO_H
    call Rei_DrawMap
    ld hl, ReiLogoAttr              ; the logotype's palettes, tile by tile
    ld de, TILEMAP0 + LOGO_Y * CON_W + LOGO_X
    ld a, 1
    ldh [rVBK], a
    ld c, REI_LOGO_H
.attrRow
    ld b, REI_LOGO_W
.attrCell
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .attrCell
    ld a, e
    add a, CON_W - REI_LOGO_W
    ld e, a
    jr nc, :+
    inc d
:   dec c
    jr nz, .attrRow
    xor a
    ldh [rVBK], a

    ld hl, sSplashA
    ld b, 6
    ld c, 7
    call Rei_Print
    ld hl, sSplashB
    ld b, 3
    ld c, 8
    call Rei_Print
    ld hl, sSplashStart
    ld b, START_X
    ld c, START_Y
    call Rei_Print
    ld hl, sSplashC
    ld b, 3
    ld c, 14
    call Rei_Print
    ld hl, sSplashD
    ld b, 7
    ld c, 15
    call Rei_Print
    call ReiScr_LcdOn

    xor a
    ld [wReiBlinkT], a
.wait
    call Console_WaitVBlank
    ld hl, wReiBlinkT               ; borrowed: her face is not up yet
    inc [hl]
    ld a, [hl]
    and $1F
    jr nz, .pad
    ld a, [hl]                      ; every 32 frames: shown, hidden, shown...
    and $20
    ld a, PAL_S_TEXT
    jr z, :+
    ld a, PAL_S_DIM
:   ld b, START_X
    ld c, START_Y
    ld d, START_W
    ld e, 1
    call Rei_Attr
.pad
    call Joy_Read
    ld a, [wJoyNew]
    and KB_START
    jr z, .wait
    jp ReiScr_Main

ENDC
