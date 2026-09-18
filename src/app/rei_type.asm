; Rei's teletype: src/teletype.asm with her pane as the paper.
;
; The same queue and the same pacing - PrintToken queues characters, the VBlank
; handler releases one every few frames, faster when more are waiting - but a
; released character goes to Rei_PanePut (src/app/rei_pane.asm) instead of the
; full-screen console, and the handler's VRAM work is her pane and her face
; instead of the console GDMA and the status bar. The Rei build assembles this
; file in place of src/teletype.asm and exports the same names.
;
; One VRAM job a frame: the pane if it changed (about 1,050 cycles), else the
; face (about 250). The handler only starts work in the first four lines of
; VBlank, so a late entry cannot run a copy into the picture.
;
; At the end of a reply the queue is played out at a brisk pace rather than
; dumped, so her last words are typed like the rest.
;
; Cost: about 200 bytes of ROM0, 75 bytes of WRAM0.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"

DEF TYPE_QLEN   EQU 64                   ; a power of two
DEF TYPE_FRAMES EQU 18                   ; 0.3 s a character
DEF TYPE_HURRY  EQU 9                    ; a couple of tokens are waiting
DEF TYPE_RUSH   EQU 2                    ; the queue is half full
DEF TYPE_FINISH EQU 4                    ; the pace of the tail, after the model stops

SECTION "Rei teletype state", WRAM0
wTypeQ:     ds TYPE_QLEN
wTypeHead:  db                           ; next character to print
wTypeTail:  db                           ; next free slot
wTypeOn::   db
wTypeTick:  db                           ; frames until the next character

SECTION "Rei teletype code", ROM0

Type_Enable::
    xor a
    ld [wTypeHead], a
    ld [wTypeTail], a
    ld a, 1
    ld [wTypeTick], a
    ld [wTypeOn], a
    ret

; a = character. A full queue releases its oldest character at once: that is
; shadow work only, safe at any time.
Type_PutChar::
    ld b, a
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

; The main loop's "push the screen": the handler does all the pushing.
Type_Flush::
    ret

; Releases the oldest queued character into the pane's shadow. No VRAM.
Type_Step:
    ld a, [wTypeHead]
    ld hl, wTypeTail
    cp [hl]
    ret z                                ; nothing queued
    ld l, a
    ld h, 0
    ld de, wTypeQ
    add hl, de
    ld d, [hl]
    inc a
    and TYPE_QLEN - 1
    ld [wTypeHead], a
    ld a, 1
    ld [wReiTalking], a                  ; her first letter: the mouth takes over
    ld a, d
    jp Rei_PanePut

; One frame of teletype. Must be entered at the start of VBlank.
Type_Frame:
    ld a, [wReiPaneDirty]
    or a
    jr z, .face
    xor a
    ld [wReiPaneDirty], a
    call Rei_PaneBlit
    jr .tick
.face
    ld a, [wReiFaceDirty]
    or a
    jr z, .tick
    xor a
    ld [wReiFaceDirty], a
    call Rei_FaceBlit
.tick
    call Rei_BlinkTick                   ; while she thinks; talking stops it
    ld hl, wTypeTick
    dec [hl]
    ret nz
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
    jr Type_Step

; The VBlank handler.
Type_ISR::
    push af
    ld a, [wTypeOn]
    or a
    jr z, .out
    ldh a, [rLY]
    sub 144                              ; lines 144..147 leave room for a copy
    cp 4
    jr nc, .out
    push bc
    push de
    push hl
    call Type_Frame
    pop hl
    pop de
    pop bc
.out
    pop af
    reti

; The end of a reply, interrupts off: plays out what is still queued, a
; character every TYPE_FINISH frames, then the last VRAM jobs, and switches off.
Type_Drain::
.more
    call Console_WaitVBlank
    ld a, [wTypeTick]
    cp TYPE_FINISH + 1
    jr c, :+
    ld a, TYPE_FINISH
    ld [wTypeTick], a
:   call Type_Frame
    ld a, [wTypeHead]
    ld hl, wTypeTail
    cp [hl]
    jr nz, .more
    ld a, [wReiPaneDirty]
    ld hl, wReiFaceDirty
    or [hl]
    jr nz, .more
    xor a
    ld [wTypeOn], a
    ret

ENDC
