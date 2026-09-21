; The splash, which is also the main menu.
;
; The "Rei" logotype, two lines about what she is, the engine's name and
; version. Then it depends on the cartridge:
;   no save     PRESS START blinks; START begins a new conversation.
;   a save      "continue" and "new friend" (UP/DOWN, A or START chooses) over
;               how much there has been: visits and lines exchanged.
;               "continue" goes on with the conversation exactly as it was
;               left - the model's state, the log, her last reply in the pane.
;               "new friend" asks once (A yes, B no) and then forgets it all.
; The save is checked and loaded before the menu is drawn (the counters come
; from it); forgetting zeroes what was loaded.
;
; The title is a picture, 20 x 9 tiles from the splash tile set (REI cut on the
; diagonal, the red line behind it, the character for zero, the four small
; words); the set shares its VRAM range with the main screen's, and leaving
; the splash loads the other one. One palette does it all: night, red, white.
; Everything under the picture hangs from one column: the items, the counters
; under them (their numbers end where "new friend" ends), and the cursor two
; cells to the left.
; The blink is a palette, not a redraw: PRESS START's cells switch between the
; text palette and one whose four colours are all the background.
; Leaving wipes the screen down, a row a frame, and the main screen follows.
;
; Cost: nothing in ROM0; about 600 bytes of the UI bank, 2 bytes of WRAM0, and
; the splash art.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

DEF LOGO_X  EQU 0
DEF LOGO_Y  EQU 1
DEF START_X EQU 4
DEF START_Y EQU 11
DEF START_W EQU 11
DEF MENU_X  EQU 6                   ; the items; the arrow is two to the left
DEF MENU_Y  EQU 10
DEF MENU_END EQU MENU_X + 10        ; one past "new friend"
DEF STAT_X  EQU MENU_X
DEF STAT_Y  EQU 13
DEF ENGINE_Y EQU 16

SECTION "Rei splash state", WRAM0
wReiMenu:     db                    ; 1 = a save was found: the menu, not PRESS START
wReiMenuPick: db                    ; 0 = continue, 1 = new friend

SECTION "Rei splash", ROMX, BANK[REI_BANK]

sSplashStart: db "PRESS START", 0
sSplashC: db "ChatGBC engine", 0
sSplashD: db "v1.0.0", 0
sMenuContinue: db "continue", 0
sMenuNew:      db "new friend", 0
sMenuVisits:   db "visits", 0
sMenuLines:    db "lines", 0
sMenuForget:   db "forget everything?", 0
sMenuYesNo:    db "A yes    B no", 0

; hl = a 16-bit counter, c = row: its decimal into the shadow, ending at the
; column where the items end.
ReiSplash_Number:
    ld a, [hl+]
    ld [wNum + 0], a
    ld a, [hl]
    ld [wNum + 1], a
    xor a
    ld [wNum + 2], a
    ld [wNum + 3], a
    push bc
    call Dec32_Render
    pop bc
    ld a, [wDigitLen]
    ld b, a
    ld a, MENU_END
    sub b
    ld b, a
    call Rei_CellAddr
    ld de, wDigits
    ld a, [wDigitLen]
    ld c, a
.digit
    ld a, [de]
    inc de
    sub FONT_FIRST
    ld [hl+], a
    dec c
    jr nz, .digit
    ret

; Rows MENU_Y and MENU_Y + 1 of the shadow: the two items and the arrow.
ReiSplash_Items:
    call ReiSplash_BlankItems
    ld hl, sMenuContinue
    ld b, MENU_X
    ld c, MENU_Y
    call Rei_Print
    ld hl, sMenuNew
    ld b, MENU_X
    ld c, MENU_Y + 1
    call Rei_Print
    ld a, [wReiMenuPick]
    add a, MENU_Y
    ld c, a
    ld b, MENU_X - 2
    call Rei_CellAddr
    ld [hl], T_S_ARROW
    ret

ReiSplash_BlankItems:
    xor a
    ld b, 0
    ld c, MENU_Y
    ld d, CON_VIS_W
    ld e, 2
    jp Rei_Fill

; The same two rows, shadow -> screen.
ReiSplash_PushItems:
    call Console_WaitVBlank
    ld hl, MENU_Y * CON_W
    ld b, 2
    ld c, CON_VIS_W
    jp Rei_Blit

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
    xor a
    ld [wReiMenuPick], a
    call ReiSave_Check
    ld a, 0
    jr nc, :+
    inc a
:   ld [wReiMenu], a
    or a
    jr z, .pressStart
    call ReiSave_Load
    call ReiSplash_Items
    ld hl, sMenuVisits
    ld b, STAT_X
    ld c, STAT_Y
    call Rei_Print
    ld hl, wReiVisits
    ld c, STAT_Y
    call ReiSplash_Number
    ld hl, sMenuLines
    ld b, STAT_X
    ld c, STAT_Y + 1
    call Rei_Print
    ld hl, wReiLines
    ld c, STAT_Y + 1
    call ReiSplash_Number
    jr .engine
.pressStart
    ld hl, sSplashStart
    ld b, START_X
    ld c, START_Y
    call Rei_Print
.engine
    ld hl, sSplashC
    ld b, 3
    ld c, ENGINE_Y
    call Rei_Print
    ld hl, sSplashD
    ld b, 7
    ld c, ENGINE_Y + 1
    call Rei_Print
    call ReiScr_LcdOn

    xor a
    ld [wReiBlinkT], a
.wait
    call Console_WaitVBlank
    ld a, [wReiMenu]
    or a
    jr nz, .menu

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
    jr .go

.menu
    call Joy_Read
    ld a, [wJoyNew]
    ld b, a
    and KB_UP | KB_DOWN
    jr z, :+
    ld a, [wReiMenuPick]
    xor 1
    ld [wReiMenuPick], a
    call ReiSplash_Items
    call ReiSplash_PushItems
    jr .wait
:   ld a, b
    and KB_A | KB_START
    jr z, .wait
    ld a, [wReiMenuPick]
    or a
    jr z, .go                       ; continue: everything is loaded already

    call ReiSplash_BlankItems       ; new friend: ask once
    ld hl, sMenuForget
    ld b, 1
    ld c, MENU_Y
    call Rei_Print
    ld hl, sMenuYesNo
    ld b, 4
    ld c, MENU_Y + 1
    call Rei_Print
    call ReiSplash_PushItems
.ask
    call Console_WaitVBlank
    call Joy_Read
    ld a, [wJoyNew]
    ld b, a
    and KB_B
    jr z, :+
    call ReiSplash_Items            ; no: the menu again
    call ReiSplash_PushItems
    jp .wait
:   ld a, b
    and KB_A
    jr z, .ask
    call ReiSave_Forget

.go
    ld hl, TILEMAP0                 ; a wipe: the night comes down a row a frame
    ld c, CON_H
.wipe
    call Console_WaitVBlank
    ld b, CON_VIS_W
    xor a
.wipeCell
    ld [hl+], a
    dec b
    jr nz, .wipeCell
    ld de, CON_W - CON_VIS_W
    add hl, de
    dec c
    jr nz, .wipe
    jp ReiScr_LcdOff                ; the main loop loads the world's art, then ReiScr_Main

ENDC
