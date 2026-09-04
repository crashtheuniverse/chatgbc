; Teletype: characters go out one at a time, on the VBlank interrupt, while
; the forward pass is busy with the next token.
;
; A token is three or four characters, and they used to land on the screen
; in one burst followed by a second of nothing. Now PrintToken queues them and
; the VBlank handler releases one every TYPE_FRAMES frames: the reader sees a
; steady stream and the token boundaries disappear. While the teletype is on
; the handler is the only thing that touches VRAM. A character is one tile
; write inside VBlank. A scroll moves the shadow buffer (WRAM, any time) and
; asks for the GDMA on the next VBlank, where it fits. The status bar marks
; itself dirty and is pushed the same way. The forward pass never waits for
; the screen, and the screen never waits for the forward pass.
;
; Off - the lab ROM, the keyboard, every test - everything prints
; synchronously as before, so the golden tokens are untouched.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"

DEF TYPE_QLEN   EQU 64                   ; a power of two
DEF TYPE_FRAMES EQU 18                   ; 0.3 s a character
DEF TYPE_HURRY  EQU 9                    ; a couple of tokens are waiting
DEF TYPE_RUSH   EQU 2                    ; the queue is half full

SECTION "Teletype state", WRAM0
wTypeQ:        ds TYPE_QLEN
wTypeHead:     db                        ; next character to print
wTypeTail:     db                        ; next free slot
wTypeOn::      db
wTypeTick:     db                        ; frames until the next character
wTypeFlush:    db                        ; the console shadow needs its GDMA
wWinDirty::    db                        ; the status bar shadow needs pushing
wTypeCellOk:   db                        ; Type_Step: one cell describes the change
wTypeCellX:    db
wTypeCellY:    db
wTypeCellTile: db

SECTION "Teletype code", ROM0

Type_Enable::
    xor a
    ld [wTypeHead], a
    ld [wTypeTail], a
    ld [wTypeFlush], a
    ld [wWinDirty], a
    ld [wConScrolled], a
    ld a, 1
    ld [wTypeTick], a
    ld [wTypeOn], a
    ret

; a = character. Queued when the teletype is on, printed now when it is off.
; A full queue releases its oldest character synchronously rather than
; waiting: between tokens interrupts are off, so nothing else would drain it.
Type_PutChar::
    ld b, a
    ld a, [wTypeOn]
    or a
    ld a, b
    jp z, Console_PutChar
.again
    ld a, [wTypeTail]
    inc a
    and TYPE_QLEN - 1
    ld hl, wTypeHead
    cp [hl]
    jr nz, .room
    push bc
    call Type_Step
    pop bc
    jr .again
.room
    ld c, a                              ; c = the tail after this character
    ld a, [wTypeTail]
    ld l, a
    ld h, 0
    ld de, wTypeQ
    add hl, de
    ld [hl], b
    ld a, c
    ld [wTypeTail], a
    ret

; The main loop's "push the screen" while the teletype is on: nothing to do,
; the handler pushes the shadow when a character lands on it.
Type_Flush::
    ld a, [wTypeOn]
    or a
    jp z, Console_Flush
    ret

; Prints whatever is still queued, now, switches the teletype off and pushes
; the screen and the bar. For the end of a run, with interrupts off.
Type_Drain::
.more
    ld a, [wTypeHead]
    ld hl, wTypeTail
    cp [hl]
    jr z, .off
    call Type_Step
    jr .more
.off
    xor a
    ld [wTypeOn], a
    ld [wTypeFlush], a
    ld [wWinDirty], a
    call Console_Flush
    jp StatusWin_Flush

; Releases the oldest queued character into the console shadow. Nothing here
; touches VRAM. Afterwards either wTypeCellOk is set and the only cell that
; changed is (wTypeCellX, wTypeCellY) now holding wTypeCellTile, or
; wTypeFlush is set because the row wrapped and the screen scrolled - or a
; bare newline moved only the cursor and nothing on screen changed.
Type_Step:
    ld a, [wTypeHead]
    ld hl, wTypeTail
    cp [hl]
    ret z                                ; nothing queued
    ld l, a
    ld h, 0
    ld de, wTypeQ
    add hl, de
    ld d, [hl]                           ; d = the character
    inc a
    and TYPE_QLEN - 1
    ld [wTypeHead], a
    ld a, [wCursorX]
    ld [wTypeCellX], a
    ld a, [wCursorY]
    ld [wTypeCellY], a
    xor a
    ld [wConScrolled], a
    ld a, d
    cp $0A
    jr z, .newline
    sub FONT_FIRST
    ld [wTypeCellTile], a
    ld a, d
    call Console_PutChar                 ; the shadow; may wrap and scroll
    ld a, [wConScrolled]
    or a
    jr nz, .flush                        ; the cell just written moved up a row
    ld a, 1
    ld [wTypeCellOk], a
    ret
.newline
    ld a, d
    call Console_PutChar
    ld a, [wConScrolled]
    or a
    ret z
.flush
    ld a, 1
    ld [wTypeFlush], a
    ret

; The VBlank handler. One VRAM job a frame - the console GDMA if a scroll is
; waiting, else the status bar if it changed - then, when the tick runs out,
; one character. Entered at the first line of VBlank, so the job and the
; single tile write both land inside it; a scroll's shadow move may run past
; VBlank, but it is WRAM and its GDMA waits for the next frame.
Type_ISR::
    push af
    push bc
    push de
    push hl
    ld a, [wTypeOn]
    or a
    jr z, .done
    ld a, [wTypeFlush]
    or a
    jr z, .noFlush
    xor a
    ld [wTypeFlush], a
    call Console_FlushNow
    jr .tick
.noFlush
    ld a, [wWinDirty]
    or a
    jr z, .tick
    xor a
    ld [wWinDirty], a
    call StatusWin_FlushNow
.tick
    ld hl, wTypeTick
    dec [hl]
    jr nz, .done
    ld a, [wTypeTail]                    ; pace by how much is waiting
    ld hl, wTypeHead
    sub [hl]
    and TYPE_QLEN - 1
    ld b, TYPE_FRAMES
    cp 8
    jr c, .pace
    ld b, TYPE_HURRY
    cp TYPE_QLEN / 2
    jr c, .pace
    ld b, TYPE_RUSH
.pace
    ld a, b
    ld [wTypeTick], a
    xor a
    ld [wTypeCellOk], a
    call Type_Step
    ld a, [wTypeCellOk]
    or a
    jr z, .done
    ld a, [wTypeCellY]                   ; one tile, straight into the map
    ld l, a
    ld h, 0
REPT 5
    add hl, hl                           ; row * 32
ENDR
    ld a, [wTypeCellX]
    add a, l
    ld l, a
    jr nc, :+
    inc h
:   ld de, TILEMAP0
    add hl, de
    ld a, [wTypeCellTile]
    ld [hl], a
.done
    pop hl
    pop de
    pop bc
    pop af
    reti
