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
; The logotype is 12 x 5 tiles from the splash tile set, which shares its VRAM
; range with the main screen's set; leaving the splash loads the other one.
; The blink is a palette, not a redraw: PRESS START's cells switch between the
; text palette and one whose four colours are all the background.
; The screen is 20 columns, so the two long lines are each set on two rows.
; Leaving wipes the screen down, a row a frame, and the main screen follows.
; The moment of leaving also picks the first world scene (see .go).
;
; Cost: nothing in ROM0; about 620 bytes of the UI bank, 3 bytes of WRAM0, and
; the splash art.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"
INCLUDE "rei_world_art.inc"

DEF LOGO_X  EQU (CON_VIS_W - REI_LOGO_W) / 2
DEF LOGO_Y  EQU 0
DEF START_X EQU 4
DEF START_Y EQU 10
DEF START_W EQU 11
DEF MENU_X  EQU 6                   ; the items; the arrow is two to the left
DEF MENU_Y  EQU 9
DEF STAT_X  EQU 5
DEF STAT_Y  EQU 12

SECTION "Rei splash state", WRAM0
wReiMenu:     db                    ; 1 = a save was found: the menu, not PRESS START
wReiMenuPick: db                    ; 0 = continue, 1 = new friend
wReiSplashT:  db                    ; frames on this screen, wrapping

SECTION "Rei splash", ROMX, BANK[REI_BANK]

sSplashA: db "a being", 0
sSplashB: db "in a cartridge", 0
sSplashStart: db "PRESS START", 0
sSplashC: db "ChatGBC engine", 0
sSplashD: db "v1.0.0", 0
sMenuContinue: db "continue", 0
sMenuNew:      db "new friend", 0
sMenuVisits:   db "visits", 0
sMenuLines:    db "lines", 0
sMenuForget:   db "forget everything?", 0
sMenuYesNo:    db "A yes    B no", 0

; hl = a 16-bit counter, b = column, c = row: its decimal, into the shadow.
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
    ld c, 6
    call Rei_Print
    ld hl, sSplashB
    ld b, 3
    ld c, 7
    call Rei_Print

    xor a
    ld [wReiMenuPick], a
    call ReiSave_Check
    ld a, 0
    jr nc, :+
    inc a
:   ld [wReiMenu], a
    ld c, 13                        ; the engine's two rows sit lower under a menu
    or a
    jr z, .pressStart
    call ReiSave_Load
    call ReiSplash_Items
    ld hl, sMenuVisits
    ld b, STAT_X
    ld c, STAT_Y
    call Rei_Print
    ld hl, wReiVisits
    ld b, STAT_X + 7
    ld c, STAT_Y
    call ReiSplash_Number
    ld hl, sMenuLines
    ld b, STAT_X
    ld c, STAT_Y + 1
    call Rei_Print
    ld hl, wReiLines
    ld b, STAT_X + 7
    ld c, STAT_Y + 1
    call ReiSplash_Number
    ld c, 15
    jr .engine
.pressStart
    push bc
    ld hl, sSplashStart
    ld b, START_X
    ld c, START_Y
    call Rei_Print
    pop bc
.engine
    push bc
    ld hl, sSplashC
    ld b, 3
    call Rei_Print
    pop bc
    inc c
    ld hl, sSplashD
    ld b, 7
    call Rei_Print
    call ReiScr_LcdOn

    xor a
    ld [wReiBlinkT], a
.wait
    call Console_WaitVBlank
    ld hl, wReiSplashT              ; frames on the splash, for the first scene
    inc [hl]
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
    ; The first world of this session: the moment of the press, which only
    ; the player's hand decides - the frames spent on this screen, plus the
    ; divider, which runs through its 256 values in under a frame. Their sum's
    ; remainder by three picks the scene the first visit brings, and the
    ; visits rotate from there.
    ldh a, [rDIV]
    ld hl, wReiSplashT
    add a, [hl]
    ld b, 0
    jr nc, .third
    inc b                           ; the carry out: 256, which is 1 more mod 3
.third
    cp WORLD_SCENES
    jr c, .carry
    sub WORLD_SCENES
    jr .third
.carry
    add a, b
    cp WORLD_SCENES
    jr c, .seeded
    sub WORLD_SCENES
.seeded
    ld [wWorldTurn], a
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
    jp ReiScr_Main

ENDC
