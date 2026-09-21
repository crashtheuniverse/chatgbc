; The world, frame by frame: Rei walking the riverside, the camera, the light
; on the water, the thought box's teletype - all of it from the VBlank handler,
; in ROM0.
;
; This is the deferred-computation principle. A thought is a forward pass, a
; third of a second a token, run in the main context; the scene cannot wait for
; it, so the scene does not live there. Every frame the handler (Type_ISR, in
; src/app/rei_type.asm) calls World_Frame, which spends a small budget and
; returns to whatever the model was doing. The main context only ever sleeps
; (halt) or thinks. Like the chat's handler this one saves every register,
; never touches rROMB0, rSVBK or rVBK, and only starts in the first four lines
; of VBlank.
;
; A frame, in M-cycles (counted from the listing, worst path of each part):
;     SCX                                                       7
;     her nine objects to OAM, only when they changed         345
;     the light on the water: one palette colour, 1 frame in 32   25
;     one job for the thought panel, never two:
;         one row of it, 18 cells (4 frames after a wrap)     215
;         or the one cell a letter changed                     45
;     the pad (Joy_Read) and the quit flag                    105
;     the thought timer and the linger timer                   45
;     walk, pause, turn at the ends; the camera                130
;     her objects rebuilt in RAM, only when something moved    330
;     the teletype's tick                                      20
;         and, when a letter is due, Type_Step + Rei_PanePut  150, 330 on a wrap
; A frame in which she neither moves nor changes pose: about 330. One in which
; she does (every other frame while she walks and the camera is still; every
; eighth when it follows her): about 660, and the OAM copy falls in the next.
; Worst: about 1,230 - a wrapping letter on a frame that also rebuilds and
; copies her - of the 2,280 a double-speed VBlank has; only the first 650 of
; those are VRAM or OAM. Measured on the ROM's own counter over three
; thoughts: a token costs 858,700-862,100 cycles in the world against 847,900
; in the chat, over 24.5 frames - about 520 cycles a frame, 1.5% of the
; model's time.
;
; She walks half a pixel a frame between the ends of a picture 256 pixels wide
; and turns round there; the camera follows a pixel a frame and stops at 0 and
; 96. A pause is her back to us, looking at the sunset: four frames, slowly. Stretches last 2-6 s, pauses 2-5 s; the choices come from an 8-bit
; generator whose seed, like the thought timer, the harness can set.
;
; Cost: about 520 bytes of ROM0, 190 bytes of WRAM0 (128 of them the thought
; box's shadow, 36 her objects).

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"

SECTION "Rei world state", WRAM0
wWorldOn::       db                 ; the world is on screen: the handler runs it
wWorldQuit::     db                 ; a button was pressed: back to the chat
wWorldThink::    db                 ; the timer ran out: the main context should think
wWorldThinking:: db                 ; a thought is being computed or shown
wWorldThinkT::   dw                 ; frames until the next thought
wWorldLinger::   dw                 ; frames a finished thought stays up
wWorldRng::      db
wWorldX::        db                 ; the left edge of her 24-pixel box, in the picture
wWorldScx::      db
wWorldDir::      db                 ; 0 = to the left (as she is drawn), 1 = to the right
wWorldAct::      db                 ; 0 = walking, 1 = paused, her back to us
wWorldTimer::    db                 ; of this stretch or pause, in 4-frame units
wWorldFrame::    db                 ; VBlanks, wrapping
wWorldPose::     db                 ; what wWorldOam was built for: the pose,
wWorldPoseX:     db                 ; and where on the screen
wWorldOamNew:    db                 ; wWorldOam is ahead of OAM
wWorldRows::     db                 ; rows of the thought box still to copy
wWorldOam::      ds WORLD_OBJS * 4  ; her objects, as OAM wants them
wWorldBox::      ds THINK_H * CON_W ; the thought box's shadow: its four text rows

SECTION "Rei world frame", ROM0

DEF REI_WORLD_FRAMES EQU 1          ; ROM0 takes the small table: each frame's first tile
INCLUDE "rei_world_art.inc"

; One frame of the world. VBlank has just begun.
World_Frame::
    ; --- what must happen inside VBlank: last frame's results ---
    ld a, [wWorldScx]
    ldh [rSCX], a
    ld a, [wWorldOamNew]
    or a
    jr z, .light
    xor a
    ld [wWorldOamNew], a
    ld hl, wWorldOam
    ld de, OAMRAM
    ld b, WORLD_OBJS * 4
.oam
    ld a, [hl+]
    ld [de], a
    inc e
    dec b
    jr nz, .oam
.light
    ld hl, wWorldFrame
    inc [hl]
    ld a, [hl]
IF WORLD_TWINKLE_A != WORLD_TWINKLE_B    ; (the generator found no colour safe to touch: see twinkle())
    and $1F                         ; the sun's path on the water: one colour, two values
    jr nz, .box
    ld a, WORLD_TWINKLE | BGPI_AUTOINC
    ldh [rBCPS], a
    bit 5, [hl]
    ld hl, WORLD_TWINKLE_A
    jr z, :+
    ld hl, WORLD_TWINKLE_B
:   ld a, l
    ldh [rBCPD], a
    ld a, h
    ldh [rBCPD], a
ENDC

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
    ld de, TILEMAP1 + THINK_Y * CON_W - wWorldBox
    add hl, de                      ; the same cell of the window's map
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
    ld hl, TILEMAP1 + THINK_Y * CON_W
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
    ld hl, wWorldX
    ld a, [wWorldDir]
    or a
    jr nz, .right
    dec [hl]
    ld a, WORLD_MIN_X
    cp [hl]
    jr c, .camera                   ; min < x: carry on
    ld [hl], a
    ld a, 1                         ; the end: she turns round
    jr .turned
.right
    inc [hl]
    ld a, WORLD_MAX_X
    cp [hl]
    jr nc, .camera                  ; max >= x
    ld [hl], a
    xor a
.turned
    ld [wWorldDir], a
.camera
    ld hl, wWorldScx
    ld a, [wWorldX]
    sub [hl]                        ; where she is on the screen
    cp CAM_LEFT
    jr nc, :+
    ld a, [hl]
    or a
    jr z, .sprite
    dec [hl]
    jr .sprite
:   cp CAM_RIGHT + 1
    jr c, .sprite
    ld a, [hl]
    cp CAM_MAX
    jr nc, .sprite
    inc [hl]

    ; --- her pose: b = frame number * 2 + direction, c = her box's x on the screen ---
.sprite
    ld a, [wWorldX]
    sub [hl]
    ld c, a
    ld a, [wWorldAct]
    or a
    jr z, .walking
    ld a, [wWorldFrame]             ; from behind: frames 0-3, a slow sway
    rlca
    rlca
    rlca
    and 3
    add a, a
    jr .posed
.walking
    ld a, [wWorldX]                 ; walking: frames 4-7, a step every 4 pixels
    rra
    rra
    and 3
    add a, 4
    add a, a
    ld hl, wWorldDir
    or [hl]
.posed
    ld b, a
    ld hl, wWorldPose
    cp [hl]
    jr nz, .build
    inc hl
    ld a, c
    cp [hl]
    jr z, .tick                     ; nothing moved: her objects stand
.build
    ld hl, wWorldPose
    ld [hl], b
    inc hl
    ld [hl], c
    call World_Build
.tick
    ld a, [wTypeOn]
    or a
    ret z
    jp Type_Tick

; b = frame * 2 + direction, c = her box's x on the screen: wWorldOam.
; A frame is columns of three 8 x 16 objects, its tiles column by column; the
; back views are two columns, centred in the box; to the right is the same
; objects mirrored, columns taken from the other end.
World_Build:
    ld a, b
    srl a
    ld e, a
    ld d, 0
    ld hl, ReiWorldFrames
    add hl, de
    ld d, [hl]                      ; d = the frame's first tile
    cp 4
    ld e, WORLD_WALK_COLS
    jr nc, :+
    ld e, WORLD_IDLE_COLS
    ld a, c
    add a, (WORLD_WALK_COLS - WORLD_IDLE_COLS) * 4
    ld c, a
:   ld a, c
    add a, OAM_X_OFS
    ld c, a                         ; c = OAM x of the leftmost column
    bit 0, b
    ld b, OAM_BANK1
    jr z, .columns
    ld b, OAM_BANK1 | OAM_XFLIP     ; mirrored: start from the last column's tiles
    ld a, e
    dec a
    ld l, a
    add a, a
    add a, l
    add a, a                        ; (cols - 1) * 6
    add a, d
    ld d, a
.columns
    ld hl, wWorldOam
.column
    push de
    ld e, WORLD_REI_Y + OAM_Y_OFS
.object
    ld a, e
    ld [hl+], a
    ld a, c
    ld [hl+], a
    ld a, d
    ld [hl+], a
    ld a, b
    ld [hl+], a
    inc d
    inc d
    ld a, e
    add a, 16
    ld e, a
    cp WORLD_REI_Y + OAM_Y_OFS + 48
    jr c, .object
    pop de
    ld a, d                         ; the next column's tiles: 6 on, or 6 back
    bit B_OAM_XFLIP, b
    jr nz, :+
    add a, 12
:   sub 6
    ld d, a
    ld a, c
    add a, 8
    ld c, a
    dec e
    jr nz, .column
    ld a, [wWorldPose]              ; a back view is six objects: the other three
    cp 8                            ; go off screen
    jr nc, .built
    ld b, WORLD_OBJS - WORLD_IDLE_COLS * 3
    xor a
.spare
    ld [hl+], a
    inc hl
    inc hl
    inc hl
    dec b
    jr nz, .spare
.built
    ld a, 1
    ld [wWorldOamNew], a
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
    ld a, 1                         ; stop, turn to the water, look: 2-5 s
    ld [wWorldAct], a
    ld a, c
    and $3F
    add a, 30
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

ASSERT THINK_X + THINK_W <= CON_VIS_W && WORLD_REI_Y + 48 <= WORLD_WIN_Y

ENDC
