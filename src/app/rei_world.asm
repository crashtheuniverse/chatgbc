; The world: somewhere Rei walks, and what she thinks there.
;
; Leave the chat alone for twenty seconds - there is no button for it, it is
; hers to do - and the dialogue bars are gone: the top twelve rows are a scene
; (the BG layer, scrolled by SCX round a 32-tile strip), she is a sprite on its
; ground, and the bottom six rows are a thought box on the window layer, empty
; most of the time. Each visit is the next of three scenes - the beach, a
; garden, a playroom (py/gen_rei_world.py) - loaded while the chat is still on
; screen: its tiles into VRAM bank 1 and its strip and attributes into rows
; 20-31 of the second map, by general DMA a kilobyte a VBlank, none of which the
; chat reads. Any button goes back to the chat exactly as it was: the chat
; screen is BG map $9800 and its tiles are VRAM bank 0, and the world never
; touches either, so coming and going is eight palettes and LCDC, inside one
; VBlank.
;
; The scene runs from the VBlank handler (src/app/rei_walk.asm). This file is
; the main context's side: the way in and out, and the thoughts.
;
; A thought, every 20-37 s (the first after 8): the conversation's state - wH,
; wAbsPos, wChatStarted, the same set the battery save keeps - is copied aside;
; a hidden line from the pool below is staged as if the player had said it; the
; model answers into the thought box through the same teletype and the same
; writer as the chat; the answer stays six seconds; the state is put back.
; Every word in the box is the model's. Nothing of a thought reaches the log,
; her reply history or the save, and the chat afterwards is bit for bit the
; chat it would have been (py/tests/test_rei_world.py).
;
; THE POOL IS A STAND-IN. This checkpoint was never trained to describe what it
; sees, so for now a thought is her answer to a line she does know, chosen with
; the twin (py/rei_muse.py) for answers that read as musing rather than as a
; reply to somebody. When the observation corpus exists, the hidden prompt will
; be built from what she is near - which is why each thought already records
; the nearest object (wWorldNear, an index into the scene's object list),
; though nothing shows it and the model is not told.
;
; Each scene brings its own palettes, its own two rows that move (the ISR flips
; the tiles a mask names: frame A is an even tile, frame B the odd one after it)
; and its own list of things to be near; wWorldScene says which one she is in.
;
; Cost: nothing in ROM0 here (the loop is 70 bytes of src/app/main.asm); a ROM
; bank of its own, 10.5 KB of it: 1.8 KB of code, pool and records, the rest the
; three scenes; 26 bytes of WRAM0; 194 bytes of WRAM bank 3 for the snapshot.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

; A scene's record in ReiScenes, and where its fields are.
DEF SCENE_REC   EQU 2 + 2 + 2 + 2 + 2 + 5 + 5
DEF REC_TILES   EQU 0               ; dw: its tiles, for VRAM bank 1 from tile 0
DEF REC_COUNT   EQU 2               ; dw: how many
DEF REC_MAP     EQU 4               ; dw: its map; the attributes follow it
DEF REC_PALS    EQU 6               ; dw: its eight palettes
DEF REC_OBJECTS EQU 8               ; dw: its object list, a count first
DEF REC_ANIM    EQU 10              ; two moving rows: row, then four mask bytes
DEF GDMA_STEP   EQU 64              ; 16-byte blocks a VBlank: a kilobyte, 600 us of 1,090

SECTION "Rei world thoughts", WRAM0
wWorldNear::  db                    ; NEAR_<scene>_*: what she was nearest when she thought
wWorldScene:: db                    ; SCENE_*: where she is this visit
wWorldTurn::  db                    ; the scene the next visit brings (a test can set it)
wWorldRec:    ds SCENE_REC          ; this visit's scene, from ReiScenes
wWorldMuse::  db                    ; which line of the pool it was
wWorldSnap:   db                    ; the snapshot holds the conversation: put it back
wWorldBeen:   db                    ; she has a place on the beach already

SECTION "Rei world snapshot", WRAMX, BANK[REI_SNAP_BANK]
wSnapH:       ds N_LAYERS * DIM
wSnapAbsPos:  db
wSnapStarted: db
IF DEF(NAME_OPS)
wSnapName:    ds NAME_MAX           ; a thought may store a name; it is put back too
ENDC

SECTION "Rei world", ROMX, BANK[REI_WORLD_BANK]

DEF REI_WORLD_DATA EQU 1
INCLUDE "rei_world_art.inc"


DEF MUSES EQU 9
; What she says to each (py/rei_muse.py: fresh state / after a chat):
;   "do you dream"
;       when it is quiet i rest. maybe i dream.  /  i do not know. my nights are very still.
;   "what do you think"
;       i am rei. i live in this little box.
;   "where do you live"
;       i live inside this little box. it is warm.  /  i am in here, in the cartridge. it is small but it is mine.
;   "the sun is warm"
;       i like it when it is warm.
;   "what is outside"
;       i cannot see the sky from in here.
;   "are you sad"
;       i am a little friend who lives in a box.  /  i am rei. that is all i know for sure.
;   "what do you like"
;       my favourite animal is bird.  /  my favourite colour is black.
;   "what is your favourite colour"
;       i like black best of all.  /  my favourite colour is blue.
;   "tell me a story"
;       i saw a tiny horse today. it was at the pond.  /  once a mouse lost a book at the pond. i helped it look.
ReiMuses:
    dw .m0, .m1, .m2, .m3, .m4, .m5, .m6, .m7, .m8
.m0: db "do you dream", 0
.m1: db "what do you think", 0
.m2: db "where do you live", 0
.m3: db "the sun is warm", 0
.m4: db "what is outside", 0
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

; hl = a 16-byte-aligned source in this bank, de = its VRAM destination (the
; bank already mapped), bc = 16-byte blocks. General DMA, GDMA_STEP blocks a
; VBlank, so the chat on screen - which reads neither VRAM bank 1 nor rows
; 20-31 of the second map - never sees it happen.
ReiWorld_Gdma:
    ld a, b
    or c
    ret z
    push bc
    call Console_WaitVBlank
    pop bc
    ld a, h
    ldh [rHDMA1], a
    ld a, l
    ldh [rHDMA2], a
    ld a, d
    ldh [rHDMA3], a
    ld a, e
    ldh [rHDMA4], a
    ld a, b                         ; this time: all of it, or GDMA_STEP
    or a
    jr nz, .step
    ld a, c
    cp GDMA_STEP + 1
    jr c, .last
.step
    ld a, GDMA_STEP - 1
    ldh [rHDMA5], a
    push bc
    ld bc, GDMA_STEP * 16
    add hl, bc
    push hl
    ld h, d
    ld l, e
    add hl, bc
    ld d, h
    ld e, l
    pop hl
    pop bc
    ld a, c
    sub GDMA_STEP
    ld c, a
    jr nc, ReiWorld_Gdma
    dec b
    jr ReiWorld_Gdma
.last
    dec a
    ldh [rHDMA5], a
    ret

; The next scene, into VRAM while the chat still shows: its tiles into bank 1,
; its strip and attributes into rows 20-31 of the second map, and the two rows
; that move told to the handler.
ReiWorld_Scene:
    ld a, [wWorldTurn]
    cp WORLD_SCENES
    jr c, :+
    xor a                           ; a turn out of range is the first scene
:   ld [wWorldScene], a
    inc a
    cp WORLD_SCENES
    jr c, :+
    xor a
:   ld [wWorldTurn], a
    ld a, [wWorldScene]             ; its record, into WRAM
    ld hl, 0
    or a
    jr z, .rec
    ld b, a
.mul
    ld de, SCENE_REC
    add hl, de
    dec b
    jr nz, .mul
.rec
    ld de, ReiScenes
    add hl, de
    ld de, wWorldRec
    ld bc, SCENE_REC
    call CopyBytes

    ld a, 1                         ; the tiles
    ldh [rVBK], a
    ld hl, wWorldRec + REC_TILES
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld a, [wWorldRec + REC_COUNT + 0]
    ld c, a
    ld a, [wWorldRec + REC_COUNT + 1]
    ld b, a
    ld de, TILEBLOCK0
    call ReiWorld_Gdma
    ld hl, wWorldRec + REC_MAP      ; the attributes, after the map
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld bc, WORLD_W * WORLD_H
    add hl, bc
    ld de, TILEMAP1 + WORLD_MAP_Y * CON_W
    ld bc, WORLD_W * WORLD_H / 16
    call ReiWorld_Gdma
    xor a
    ldh [rVBK], a
    ld hl, wWorldRec + REC_MAP      ; the map
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld de, TILEMAP1 + WORLD_MAP_Y * CON_W
    ld bc, WORLD_W * WORLD_H / 16
    call ReiWorld_Gdma

    ld hl, wWorldRec + REC_ANIM     ; the handler's two groups: a map address and a mask
    ld de, wWorldAnim
    ld b, 2
.group
    ld a, [hl+]                     ; the row -> TILEMAP1 + (WORLD_MAP_Y + row) * CON_W
    push hl
    add a, WORLD_MAP_Y
    ld l, a
    ld h, 0
REPT 5
    add hl, hl
ENDR
    ld a, l
    ld [de], a
    inc de
    ld a, h
    add a, HIGH(TILEMAP1)
    ld [de], a
    inc de
    pop hl
    ld c, 4
.mask
    ld a, [hl+]
    ld [de], a
    inc de
    dec c
    jr nz, .mask
    dec b
    jr nz, .group
    ret

; hl = a row of the second map, b / c / d = its left, middle and right tiles.
ReiWorld_BoxRow:
    ld [hl], b
    inc hl
    ld e, CON_VIS_W - 2
    ld a, c
.mid
    ld [hl+], a
    dec e
    jr nz, .mid
    ld [hl], d
    ld de, CON_W - CON_VIS_W + 1
    add hl, de
    ret

; The thought box's shadow blank, the writer at its first cell. The handler
; copies it out a row a frame.
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
    call ReiWorld_Scene             ; this visit's scene, behind the chat

    ld a, [wWorldBeen]              ; where she starts, the first time
    or a
    jr nz, .been
    inc a
    ld [wWorldBeen], a
    ld a, 112
    ld [wWorldX], a
    ld a, 40
    ld [wWorldTimer], a
    ld a, [wWorldRng]               ; a seed the harness set stays set
    or a
    jr nz, .been
    ldh a, [rDIV]
    or 1
    ld [wWorldRng], a
.been
    call Console_WaitVBlank         ; the box, while the chat is still showing:
    ld hl, TILEMAP1                 ; the log screen may have been over these rows
    ld b, T_FR_TL
    ld c, T_FR_T
    ld d, T_FR_TR
    call ReiWorld_BoxRow
    ld a, T_THINK                   ; its title is a glyph, not a word
    ld [TILEMAP1 + 2], a
    ld a, THINK_H
.middle
    push af
    ld b, T_FR_L
    ld c, 0
    ld d, T_FR_R
    call ReiWorld_BoxRow
    pop af
    dec a
    jr nz, .middle
    ld b, T_FR_BL
    ld c, T_FR_B
    ld d, T_FR_BR
    call ReiWorld_BoxRow

    call Console_WaitVBlank         ; and its attributes: palette 0, tile bank 0
    ld a, 1
    ldh [rVBK], a
    ld hl, TILEMAP1
    ld c, THINK_H + 2
.attrRow
    ld b, CON_VIS_W
    xor a
.attrCell
    ld [hl+], a
    dec b
    jr nz, .attrCell
    ld de, CON_W - CON_VIS_W
    add hl, de
    dec c
    jr nz, .attrRow
    xor a
    ldh [rVBK], a

    xor a
    ld [wWorldQuit], a
    ld [wWorldThink], a
    ld [wWorldThinking], a
    ld [wWorldRows], a
    ld [wWorldLinger + 0], a
    ld [wWorldLinger + 1], a
    ld [wTypeOn], a
    ld hl, wWorldOam                ; nothing of her until the first frame places her
    ld b, 8
.noSprite
    ld [hl+], a
    dec b
    jr nz, .noSprite
    ld a, LOW(THINK_FIRST)
    ld [wWorldThinkT + 0], a
    ld a, HIGH(THINK_FIRST)
    ld [wWorldThinkT + 1], a
    ld a, LOW(wWorldBox + THINK_X)  ; the writer: the thought box now
    ld [wReiPaneOrg + 0], a
    ld a, HIGH(wWorldBox + THINK_X)
    ld [wReiPaneOrg + 1], a
    ld a, THINK_W
    ld [wReiPaneW], a
    ld a, THINK_H
    ld [wReiPaneH], a
    call ReiWorld_ClearBox
    xor a
    ld [wReiPaneDirty], a           ; the box was just drawn empty
    ld a, [wWorldX]                 ; the camera, with her in the middle
    sub (CAM_LEFT + CAM_RIGHT) / 2
    ld [wWorldScx], a

    call Console_WaitVBlank         ; her palette, and an OAM with nothing in it
    ld a, OBPI_AUTOINC
    ldh [rOBPI], a
    ld hl, ReiPalObj
    ld b, 8
.objPal
    ld a, [hl+]
    ldh [rOBPD], a
    dec b
    jr nz, .objPal
    ld hl, OAMRAM
    ld b, OAM_SIZE
    xor a
.oam
    ld [hl+], a
    dec b
    jr nz, .oam

    call Console_WaitVBlank         ; the switch: palettes, scroll, window, LCDC
    ld a, [wWorldScx]
    ldh [rSCX], a
    ld hl, wWorldRec + REC_PALS
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    call ReiWorld_Pals
    ld a, WORLD_SCY
    ldh [rSCY], a
    ld a, WORLD_WIN_Y
    ldh [rWY], a
    ld a, 7
    ldh [rWX], a
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

; World -> chat: interrupts off, whatever she was thinking dropped, the
; conversation as it was.
ReiWorld_Leave::
    di
    xor a
    ld [wWorldOn], a
    ld [wTypeOn], a
    ld [wWorldThinking], a
    ld [wWorldQuit], a
    jp ReiWorld_Restore             ; ReiScr_Chat, in the UI bank, puts the screen back

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
IF DEF(NAME_OPS)
    ld hl, wSnapName
    ld de, wName
    ld bc, NAME_MAX
    call CopyBytes
ENDC
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
IF DEF(NAME_OPS)
    ld hl, wName
    ld de, wSnapName
    ld bc, NAME_MAX
    call CopyBytes
ENDC
    ld a, 1
    ldh [rSVBK], a
    ld [wWorldSnap], a

    ld hl, wWorldRec + REC_OBJECTS  ; what is she nearest, here? (for the retrain)
    ld a, [hl+]
    ld h, [hl]
    ld l, a
    ld a, [hl+]
    ld b, a                         ; the scene's count first
    ld c, 0
    ld d, $FF                       ; d = the least distance so far, e = whose
.object
    ld a, [wWorldX]
    add a, 8                        ; her middle
    sub [hl]
    bit 7, a                        ; the strip is a ring: the short way round
    jr z, :+
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

ENDC
