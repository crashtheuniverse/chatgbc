; The world, frame by frame: Rei walking the beach, the camera, the sea, the
; thought box's teletype - all of it from the VBlank handler, in ROM0.
;
; This is the deferred-computation principle. A thought is a forward pass, a
; third of a second a token, run in the main context; the scene cannot wait for
; it, so the scene does not live there. Every frame the handler (Type_ISR, in
; src/app/rei_type.asm) calls World_Frame, which spends a small fixed budget
; and returns to whatever the model was doing. The main context only ever
; sleeps (halt) or thinks. Like the chat's handler it saves every register,
; never touches rROMB0, rSVBK or rVBK, and only starts in the first four lines
; of VBlank.
;
; A frame, in M-cycles (counted from the listing, worst path of each part):
;     SCX and the two OAM entries from their shadows        75
;     one VRAM job, never two:
;         the sea: 32 tile numbers flipped, a row at a time   300  (2 frames in 32)
;         or one row of the thought box, 18 cells             215  (4 frames after a wrap)
;         or the one cell a letter changed                     45
;     the pad (Joy_Read) and the quit flag                   105
;     the thought timer and the linger timer                  45
;     walk, pause, turn; camera; the sprite's shadow         190
;     the teletype's tick                                     20
;         and, when a letter is due, Type_Step + Rei_PanePut 150, 330 on a wrap
; Typical frame: about 450. Worst: about 1,050 (sea row + a wrapping letter),
; of the 2,280 a double-speed VBlank has and the 35,112 of a frame. Measured on
; the ROM's own counter: a token costs 859,281 cycles in the world against
; 847,862 in the chat, over 24.5 frames - 466 cycles a frame, 1.3% of the
; model's time.
;
; She walks half a pixel a frame along a strip that wraps at 256 pixels, so her
; position and the camera are plain bytes. The camera keeps her between x = 56
; and x = 88 on the screen. Walking stretches last 2-6 s, pauses (she looks out
; to sea) 1-3 s; the choices come from an 8-bit generator whose seed, like the
; thought timer, the harness can set.
;
; Cost: about 400 bytes of ROM0, 152 bytes of WRAM0 (128 of them the thought
; box's shadow).

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_world_art.inc"

SECTION "Rei world state", WRAM0
wWorldOn::       db                 ; the world is on screen: the handler runs it
wWorldQuit::     db                 ; a button was pressed: back to the chat
wWorldThink::    db                 ; the timer ran out: the main context should think
wWorldThinking:: db                 ; a thought is being computed or shown
wWorldThinkT::   dw                 ; frames until the next thought
wWorldLinger::   dw                 ; frames a finished thought stays up
wWorldRng::      db
wWorldX::        db                 ; her left edge along the strip, in pixels
wWorldScx::      db
wWorldDir::      db                 ; 0 = to the right, 1 = to the left
wWorldAct::      db                 ; 0 = walking, 1 = paused, looking at the sea
wWorldTimer::    db                 ; of this stretch or pause, in 4-frame units
wWorldFrame::    db                 ; VBlanks, wrapping
wWorldRows::     db                 ; rows of the thought box still to copy
wWorldOam::      ds 8               ; the two objects, as OAM wants them
wWorldBox::      ds THINK_H * CON_W ; the thought box's shadow: map rows 1-4

SECTION "Rei world frame", ROM0

; One frame of the world. VBlank has just begun.
World_Frame::
    ; --- what must happen inside VBlank: last frame's results ---
    ld a, [wWorldScx]
    ldh [rSCX], a
    ld hl, wWorldOam
    ld de, OAMRAM
    ld b, 8
.oam
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .oam

    ld hl, wWorldFrame
    inc [hl]
    ld a, [hl]
    and $0F                         ; the sea moves every 16 frames: the waves,
    jr nz, .box                     ; then 16 frames later the shore
    bit 4, [hl]
    ld hl, TILEMAP1 + (WORLD_MAP_Y + WORLD_ROW_WAVE) * CON_W
    jr z, :+
    ld hl, TILEMAP1 + (WORLD_MAP_Y + WORLD_ROW_SHORE) * CON_W
:   ld b, CON_W
.sea
    ld a, [hl]
    xor 1                           ; frame A is the even tile, frame B the odd
    ld [hl+], a
    dec b
    jr nz, .sea
    jr .logic

.box
    ld a, [wWorldRows]
    or a
    jr nz, .row
    ld a, [wReiPaneDirty]
    or a
    jr z, .logic
    ld b, a
    xor a
    ld [wReiPaneDirty], a
    dec b
    jr z, .whole
    ld a, [wReiCell + 0]            ; one letter: one cell
    ld l, a
    ld a, [wReiCell + 1]
    ld h, a
    ld a, [hl]
    ld de, TILEMAP1 + CON_W - wWorldBox
    add hl, de
    ld [hl], a
    jr .logic
.whole
    ld a, THINK_H
    ld [wWorldRows], a
.row                                ; a wrap or a clear: a row a frame, top down
    ld b, a
    ld a, THINK_H
    sub b
    swap a
    add a, a                        ; row * CON_W
    add a, THINK_X
    ld e, a
    ld d, 0
    ld hl, wWorldBox
    add hl, de
    push hl
    ld hl, TILEMAP1 + CON_W
    add hl, de
    pop de
    ld b, THINK_W
.cell
    ld a, [de]
    ld [hl+], a
    inc de
    dec b
    jr nz, .cell
    ld hl, wWorldRows
    dec [hl]

    ; --- the rest is RAM, and may run past VBlank ---
.logic
    call Joy_Read
    ld a, [wJoyNew]
    and KB_A | KB_B | KB_START | KB_SELECT
    jr z, :+
    ld a, 1
    ld [wWorldQuit], a
:
    ld a, [wWorldThinking]          ; the next thought comes nearer
    ld hl, wWorldThink
    or [hl]
    jr nz, .linger
    ld hl, wWorldThinkT
    call World_Dec16
    jr nz, .linger
    ld a, 1
    ld [wWorldThink], a
.linger
    ld hl, wWorldLinger
    ld a, [hl+]
    or [hl]
    jr z, :+
    dec hl
    call World_Dec16
:
    ld a, [wWorldFrame]             ; her stretch or her pause runs down
    and 3
    jr nz, .move
    ld hl, wWorldTimer
    dec [hl]
    call z, World_Choose
.move
    ld a, [wWorldAct]
    or a
    jr nz, .camera
    ld a, [wWorldFrame]
    rra
    jr nc, .camera                  ; a pixel every other frame
    ld a, [wWorldDir]
    or a
    ld hl, wWorldX
    jr nz, :+
    inc [hl]
    jr .camera
:   dec [hl]
.camera
    ld a, [wWorldScx]
    ld b, a
    ld a, [wWorldX]
    ld c, a
    sub b                           ; where she is on the screen
    cp CAM_LEFT
    jr nc, :+
    ld a, c
    sub CAM_LEFT
    jr .scx
:   cp CAM_RIGHT + 1
    jr c, .sprite
    ld a, c
    sub CAM_RIGHT
.scx
    ld [wWorldScx], a
    ld b, a
.sprite
    ld a, c
    sub b
    add a, OAM_X_OFS
    ld d, a                         ; d = OAM x of her left half
    ld e, SPR_LOOK
    ld a, [wWorldAct]
    or a
    jr nz, :+
    ld e, SPR_WALK_A
    bit 3, c                        ; a step every 8 pixels
    jr z, :+
    ld e, SPR_WALK_B
:   ld hl, wWorldOam
    ld a, [wWorldDir]
    or a
    jr nz, .left
    ld b, OAM_BANK1
    call .half
    ld a, d
    add a, 8
    ld d, a
    inc e
    inc e
    jr .lastHalf
.left                               ; mirrored: the halves change places too
    ld b, OAM_BANK1 | OAM_XFLIP
    inc e
    inc e
    call .half
    ld a, d
    add a, 8
    ld d, a
    dec e
    dec e
.lastHalf
    call .half

    ld a, [wTypeOn]
    or a
    ret z
    jp Type_Tick

.half
    ld a, WORLD_REI_Y + OAM_Y_OFS
    ld [hl+], a
    ld a, d
    ld [hl+], a
    ld a, e
    ld [hl+], a
    ld a, b
    ld [hl+], a
    ret

; [hl] (16 bits) one less. Z set when it reaches zero.
World_Dec16:
    ld a, [hl]
    sub 1
    ld [hl+], a
    jr nc, :+
    dec [hl]
:   or [hl]
    ret

; The next number: a full-period generator, the high bits the useful ones.
World_Rand::
    ld a, [wWorldRng]
    ld b, a
    add a, a
    add a, a
    add a, b                        ; 5x + 1
    inc a
    ld [wWorldRng], a
    swap a
    ret

; A stretch or a pause has ended: what next.
World_Choose:
    call World_Rand
    ld c, a
    ld a, [wWorldAct]
    or a
    jr nz, .walk                    ; after a pause she always walks on
    bit 0, c
    jr z, .walk
    ld a, 1                         ; stop and look: 1-3 s
    ld [wWorldAct], a
    ld a, c
    and $1F
    add a, 15
    ld [wWorldTimer], a
    ret
.walk
    xor a
    ld [wWorldAct], a
    ld a, c
    and $06                         ; one time in four she turns round
    jr nz, :+
    ld a, [wWorldDir]
    xor 1
    ld [wWorldDir], a
:   call World_Rand
    and $3F
    add a, 30                       ; 2-6 s
    ld [wWorldTimer], a
    ret

ASSERT THINK_X + THINK_W <= CON_W

ENDC
