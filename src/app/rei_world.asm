; The world: a riverside at sunset, Rei walking along it, and what she thinks.
;
; Leave the chat alone for twenty seconds - there is no button for it, it is
; hers to do - and the dialogue bars are gone. The top twelve rows are the
; picture (py/art/world_sunset.png less its top 48 lines of sky: 32 x 12 tiles
; on the BG layer, scrolled sideways by the camera), and she is a sprite 48
; pixels tall on the promenade, in front of the railing. She walks, turns round
; at the ends, and now and then stops with her back to us to look at the sun
; going down. The bottom six rows are a plain black panel on the window layer,
; with no frame: her thoughts appear on it in white, like subtitles, and go.
; Any button goes back to the chat exactly as it was: the chat is BG map $9800
; and tiles at $8000 in VRAM bank 0 and the world touches neither, so going
; back is eight palettes and LCDC in one VBlank.
;
; VRAM, all of it loaded once with the LCD off (ReiWorld_Load):
;     bank 1  $8800-$97FF  the scene's 256 tiles (the world clears LCDC.4)
;     bank 1  $8000-$87FF  her eight frames, 120 tiles: nothing is streamed
;     bank 0  $9000-$97FF  a copy of the chat's tiles 0-127, so that the
;                          panel's letters keep their numbers
;     map $9C00 rows 20-31 the strip, drawn once: the log, which shares the
;                          map, only writes rows 0-17 - which is why the panel
;                          (rows 0-5) is drawn again on the way in
;
; The scene runs from the VBlank handler (src/app/rei_walk.asm). This file is
; the main context's side: the way in and out, and the thoughts.
;
; A thought, every 20-37 s (the first after 8): the conversation's state - wH,
; wAbsPos, wChatStarted, the same set the battery save keeps - is copied aside;
; a hidden line from the pool below is staged as if the player had said it; the
; model answers onto the panel through the same teletype and the same writer
; as the chat; the answer stays six seconds; the state is put back. Every word
; on the panel is the model's. Nothing of a thought reaches the log, her reply
; history or the save, and the chat afterwards is bit for bit the chat it would
; have been (py/tests/test_rei_world.py).
;
; THE POOL IS A STAND-IN. This checkpoint was never trained to describe what it
; sees, so for now a thought is her answer to a line she does know, chosen with
; the twin (py/rei_muse.py) for answers that read as musing rather than as a
; reply to somebody. When the observation corpus exists, the hidden prompt will
; be built from what she is near - which is why each thought already records
; the nearest thing (wWorldNear, an index into ReiWorldObjects and its words),
; though nothing shows it and the model is not told.
;
; Cost: nothing in ROM0 here (the loop is 75 bytes of src/app/main.asm); a ROM
; bank of its own - about 600 bytes of code, 4 KB of scene tiles, 1.9 KB of
; her, 0.8 KB of map; 4 bytes of WRAM0; 194 bytes of WRAM bank 3.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

DEF PANEL_ROWS EQU THINK_H + 2

SECTION "Rei world thoughts", WRAM0
wWorldNear::  db                    ; NEAR_*: what she was nearest when she thought
wWorldMuse::  db                    ; which line of the pool it was
wWorldSnap:   db                    ; the snapshot holds the conversation: put it back
wWorldBeen:   db                    ; she has a place on the promenade already

SECTION "Rei world snapshot", WRAMX, BANK[REI_SNAP_BANK]
wSnapH:       ds N_LAYERS * DIM
wSnapAbsPos:  db
wSnapStarted: db

SECTION "Rei world", ROMX, BANK[REI_WORLD_BANK]

DEF REI_WORLD_DATA EQU 1
INCLUDE "rei_world_art.inc"

DEF MUSES EQU 9
; What she says to each (py/rei_muse.py: fresh state / after a chat):
;   "do you dream"
;       when it is quiet i rest. maybe i dream.
;   "what do you think"
;       a little! small thoughts for a small head.
;   "where do you live"
;       i am in here, in the cartridge. it is small but it is mine.
;   "the sun is warm"
;       i like it when it is warm.
;   "what makes you happy"
;       i like it when it is windy.  /  i do not know. my nights are very still.
;   "are you sad"
;       it is ok to be sad. it will pass.
;   "what do you like"
;       my favourite animal is mouse.  /  my favourite game is hide and seek.
;   "what is your favourite colour"
;       my favourite colour is black.
;   "tell me a story"
;       once a pig lost a bell at the park. i helped it look.  /  once a pig lost a ball at the park. i helped it look.
ReiMuses:
    dw .m0, .m1, .m2, .m3, .m4, .m5, .m6, .m7, .m8
.m0: db "do you dream", 0
.m1: db "what do you think", 0
.m2: db "where do you live", 0
.m3: db "the sun is warm", 0
.m4: db "what makes you happy", 0
.m5: db "are you sad", 0
.m6: db "what do you like", 0
.m7: db "what is your favourite colour", 0
.m8: db "tell me a story", 0

; hl = eight palettes. VBlank or LCD off.
ReiWorld_Pals:
    ld a, BGPI_AUTOINC
    ldh [rBCPS], a
    ld b, 8 * 8
.loop
    ld a, [hl+]
    ldh [rBCPD], a
    dec b
    jr nz, .loop
    ret

; Once, with the LCD off, after the chat screen is drawn: the scene's tiles
; and hers into VRAM bank 1, the chat's low tiles copied to where the world's
; LCDC will look for them, her palette, and an OAM with nothing in it.
ReiWorld_Load::
    ld a, 1
    ldh [rVBK], a
    ld hl, ReiWorldTiles
    ld de, TILEBLOCK1
    ld bc, WORLD_TILES * 16
    call CopyBytes
    ld hl, ReiWorldObjTiles
    ld de, TILEBLOCK0
    ld bc, WORLD_OBJ_TILES * 16
    call CopyBytes
    ld hl, ReiWorldAttr             ; the strip, once: the log never reaches these rows
    ld de, TILEMAP1 + WORLD_MAP_Y * CON_W
    ld bc, WORLD_W * WORLD_H
    call CopyBytes
    xor a
    ldh [rVBK], a
    ld hl, ReiWorldMap
    ld de, TILEMAP1 + WORLD_MAP_Y * CON_W
    ld bc, WORLD_W * WORLD_H
    call CopyBytes
    ld hl, TILEBLOCK0               ; the font: tiles 0-127 again at $9000
    ld de, TILEBLOCK2
    ld bc, 128 * 16
    call CopyBytes

    ld a, OBPI_AUTOINC
    ldh [rOBPI], a
    ld hl, ReiPalObj
    ld b, 8
.pal
    ld a, [hl+]
    ldh [rOBPD], a
    dec b
    jr nz, .pal
    ld hl, OAMRAM
    ld b, OAM_SIZE
    xor a
.oam
    ld [hl+], a
    dec b
    jr nz, .oam

    ld a, [wWorldBeen]              ; where she starts, the first time
    or a
    jr nz, .on
    inc a
    ld [wWorldBeen], a
    ld a, 140
    ld [wWorldX], a
    ld a, 40
    ld [wWorldTimer], a
    ld a, [wWorldRng]               ; a seed the harness set stays set
    or a
    jr nz, .on
    ldh a, [rDIV]
    or 1
    ld [wWorldRng], a
.on
    ld a, REI_LCDC                  ; everything is loaded: the chat screen, lit
    ldh [rLCDC], a
    ret

; The panel's shadow blank, the writer at its first cell. The handler copies
; it out a row a frame.
ReiWorld_ClearBox:
    ld hl, wWorldBox
    ld b, THINK_H * CON_W
    xor a
.zero
    ld [hl+], a
    dec b
    jr nz, .zero
    ld [wReiCol], a
    ld [wReiRow], a
    ld [wReiReplyLen], a
    inc a
    ld [wReiPaneDirty], a
    ret

; Chat -> world. Returns with interrupts on and the handler running the scene.
ReiWorld_Enter::
    call Console_WaitVBlank         ; the panel, while the chat is still showing:
    xor a                           ; six blank rows - the log may have been here
    call .panel
    call Console_WaitVBlank         ; and their attributes: palette 0, tile bank 0
    ld a, 1
    ldh [rVBK], a
    xor a
    call .panel
    xor a
    ldh [rVBK], a

    ld [wWorldQuit], a
    ld [wWorldThink], a
    ld [wWorldThinking], a
    ld [wWorldRows], a
    ld [wWorldLinger + 0], a
    ld [wWorldLinger + 1], a
    ld [wTypeOn], a
    ld [wReiPaneDirty], a
    ld hl, wWorldOam                ; nothing of her until the first frame places her
    ld b, WORLD_OBJS * 4
.noSprite
    ld [hl+], a
    dec b
    jr nz, .noSprite
    dec a
    ld [wWorldPose], a              ; no pose: the first frame builds her
    ld a, LOW(THINK_FIRST)
    ld [wWorldThinkT + 0], a
    ld a, HIGH(THINK_FIRST)
    ld [wWorldThinkT + 1], a
    ld a, LOW(wWorldBox + THINK_X)  ; the writer: the thought panel now
    ld [wReiPaneOrg + 0], a
    ld a, HIGH(wWorldBox + THINK_X)
    ld [wReiPaneOrg + 1], a
    ld a, THINK_W
    ld [wReiPaneW], a
    ld a, THINK_H
    ld [wReiPaneH], a
    ld a, [wWorldX]                 ; the camera, with her in the middle if it can
    sub (CAM_LEFT + CAM_RIGHT) / 2
    jr nc, :+
    xor a
:   cp CAM_MAX + 1
    jr c, :+
    ld a, CAM_MAX
:   ld [wWorldScx], a

    call Console_WaitVBlank         ; the switch: palettes, scroll, window, LCDC
    ld a, [wWorldScx]
    ldh [rSCX], a
    ld a, WORLD_SCY
    ldh [rSCY], a
    ld a, WORLD_WIN_Y
    ldh [rWY], a
    ld a, 7
    ldh [rWX], a
    ld hl, ReiPalWorld
    call ReiWorld_Pals
    ld a, WORLD_LCDC
    ldh [rLCDC], a

    ld a, 1
    ld [wWorldOn], a
    xor a
    ldh [rIF], a
    ld a, IE_VBLANK
    ldh [rIE], a
    ei
    ret
.panel                              ; a = what to fill the panel's cells with
    ld hl, TILEMAP1
    ld c, PANEL_ROWS
.panelRow
    ld b, CON_VIS_W
.panelCell
    ld [hl+], a
    dec b
    jr nz, .panelCell
    ld de, CON_W - CON_VIS_W
    add hl, de
    dec c
    jr nz, .panelRow
    ret

; World -> chat: interrupts off, whatever she was thinking dropped, the
; conversation as it was. ReiScr_Chat (the UI bank) then puts the screen back.
ReiWorld_Leave::
    di
    xor a
    ld [wWorldOn], a
    ld [wTypeOn], a
    ld [wWorldThinking], a
    ld [wReiPaneDirty], a
    ld [wReiTalking], a
    ld [wWorldQuit], a
    ldh [rVBK], a
    ; fall through

; The conversation, as it was before she thought.
ReiWorld_Restore:
    ld a, [wWorldSnap]
    or a
    ret z
    ld a, REI_SNAP_BANK
    ldh [rSVBK], a
    ld hl, wSnapH
    ld de, wH
    ld bc, N_LAYERS * DIM
    call CopyBytes
    ld a, [wSnapAbsPos]
    ld [wAbsPos], a
    ld a, [wSnapStarted]
    ld [wChatStarted], a
    ld a, 1
    ldh [rSVBK], a
    xor a
    ld [wWorldSnap], a
    ret

; The timer ran out. Puts the conversation aside and stages a hidden line in
; wPromptText, as if the player had sent it. Interrupts stay on throughout.
ReiWorld_Muse::
    ld a, 1
    ld [wWorldThinking], a
    xor a
    ld [wWorldThink], a

    ld a, REI_SNAP_BANK
    ldh [rSVBK], a
    ld hl, wH
    ld de, wSnapH
    ld bc, N_LAYERS * DIM
    call CopyBytes
    ld a, [wAbsPos]
    ld [wSnapAbsPos], a
    ld a, [wChatStarted]
    ld [wSnapStarted], a
    ld a, 1
    ldh [rSVBK], a
    ld [wWorldSnap], a

    ld hl, ReiWorldObjects          ; what is she nearest? (for the retrain)
    ld b, WORLD_OBJECTS
    ld c, 0
    ld d, $FF                       ; d = the least distance so far, e = whose
.object
    ld a, [wWorldX]
    add a, WORLD_REI_W / 2          ; her middle
    sub [hl]
    jr nc, :+
    cpl
    inc a
:   cp d
    jr nc, :+
    ld d, a
    ld e, c
:   ld a, [hl+]                     ; past the x and the words
    or a
    jr nz, :-
    inc c
    dec b
    jr nz, .object
    ld a, e
    ld [wWorldNear], a

    di                              ; the generator is the handler's
    call World_Rand
    ei
    and $0F
    cp MUSES
    jr c, :+
    sub MUSES
:   ld [wWorldMuse], a
    add a, a
    ld e, a
    ld d, 0
    ld hl, ReiMuses
    add hl, de
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld de, wPromptText
    ld c, 0
.copy
    ld a, [hl+]
    or a
    jr z, .staged
    ld [de], a
    inc de
    inc c
    jr .copy
.staged
    ld a, c
    ld [wPromptLen], a

    jp ReiWorld_ClearBox

; The model has finished (or was interrupted). Lets the teletype finish, leaves
; the thought up for a while, clears it, and puts the conversation back. A
; button cuts all of it short.
ReiWorld_Settle::
    ei                              ; the profiler leaves them off
.typing
    ld a, [wWorldQuit]
    or a
    jr nz, .over
    call Type_Idle
    jr z, .typed
    halt
    jr .typing
.typed
    ld a, LOW(THINK_STAYS)
    ld [wWorldLinger + 0], a
    ld a, HIGH(THINK_STAYS)
    ld [wWorldLinger + 1], a
.staying
    ld a, [wWorldQuit]
    or a
    jr nz, .over
    ld hl, wWorldLinger
    ld a, [hl+]
    or [hl]
    jr z, .over
    halt
    jr .staying
.over
    xor a
    ld [wTypeOn], a
    call ReiWorld_ClearBox
    call ReiWorld_Restore
    di
    call World_Rand                 ; the next one: 20 s and up to 17 more
    ei
    ld l, a
    ld h, 0
    add hl, hl
    add hl, hl
    ld de, THINK_EVERY
    add hl, de
    ld a, l
    ld [wWorldThinkT + 0], a
    ld a, h
    ld [wWorldThinkT + 1], a
    xor a
    ld [wWorldThinking], a
    ret

ASSERT MUSES <= 16 && PROMPT_MAX >= 29 + 4, "the longest line, staged"
ASSERT WORLD_TILES == 256 && WORLD_OBJ_TILES <= 128

ENDC
