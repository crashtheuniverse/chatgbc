; The two ends of a reply, and the replies she has given before.
;
; ReiUi_ReplyBegin clears her pane and puts the keys away while she thinks.
; ReiUi_After runs when the reply is complete: it reads her mood, files the
; reply, raises wReady for the harness, and then lets the player page through
; her last eight replies - UP for the one before, DOWN for the one after - until
; A, B or START goes back to talking. A marker in the bottom edge of her frame
; says which reply is showing: 8/8 is the newest once eight are on file.
;
; A reply is kept as text, not as tiles: a length byte and up to 96 characters,
; eight slots in a ring in WRAM bank 2. Showing one replays its characters
; through Rei_PanePut, the same writer the teletype uses, so an old reply wraps
; and scrolls exactly as it did when she said it. rSVBK is put back to 1 before
; anything else runs.
;
; Cost: nothing in ROM0; about 400 bytes of the UI bank, 3 bytes of WRAM0 and
; 776 of WRAM bank 2.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

DEF HIST_SLOT  EQU REI_REPLY_MAX + 1
DEF MARK_X     EQU OUT_FX + OUT_FW - 7      ; five cells, clear of the corner
DEF MARK_Y     EQU OUT_FY + OUT_FH - 1
DEF MARK_W     EQU 5

SECTION "Rei history state", WRAM0
wReiHistCount:: db                  ; replies on file, up to REI_HIST
wReiHistNext::  db                  ; the slot the next one goes in
wReiHistAge::   db                  ; the one showing: 0 = the newest

SECTION "Rei history store", WRAMX, BANK[REI_HIST_BANK]
wReiHist:: ds REI_HIST * HIST_SLOT

SECTION "Rei history", ROMX, BANK[REI_BANK]

sReiThinking: db "   ", T_DOT + FONT_FIRST, " ", T_DOT + FONT_FIRST, " ", T_DOT + FONT_FIRST, 0
sReiBack:     db T_ARROW_UP + FONT_FIRST, T_ARROW_DN + FONT_FIRST, "  her words", 0
sReiTalk:     db "A   talk to her", 0

; The keys' interior blank and unpicked, with up to two lines of help.
; hl = the first line (row 1) or 0, de = the second (row 2) or 0.
ReiHist_Panel:
    push de
    push hl
    xor a
    ld b, KEYS_X
    ld c, KEYS_Y
    ld d, KEYS_W
    ld e, KEYS_H
    call Rei_Fill
    pop hl
    ld a, h
    or l
    jr z, :+
    ld b, KEYS_X + 3
    ld c, KEYS_Y + 1
    call Rei_Print
:   pop hl
    ld a, h
    or l
    jr z, :+
    ld b, KEYS_X + 3
    ld c, KEYS_Y + 2
    call Rei_Print
:   call Console_WaitVBlank
    ld hl, KEYS_Y * CON_W + KEYS_X
    ld b, KEYS_H
    ld c, KEYS_W
    jp Rei_Blit

; She is about to answer: an empty pane, and the keys make way.
ReiUi_ReplyBegin::
    call Rei_PaneClear
    call Console_WaitVBlank
    call Rei_PaneBlit
    xor a
    ld [wReiPaneDirty], a
    ld hl, sReiThinking
    ld de, 0
    jp ReiHist_Panel

; a = slot -> hl = its address (in REI_HIST_BANK).
ReiHist_Slot:
    ld hl, wReiHist
    or a
    ret z
    ld de, HIST_SLOT
.next
    add hl, de
    dec a
    jr nz, .next
    ret

; Files wReiReply as the newest reply. An empty reply is not filed.
ReiHist_Store:
    ld a, [wReiReplyLen]
    or a
    ret z
    ld a, [wReiHistNext]
    call ReiHist_Slot
    ld a, REI_HIST_BANK
    ldh [rSVBK], a
    ld a, [wReiReplyLen]
    ld [hl+], a
    ld c, a
    ld de, wReiReply
.copy
    ld a, [de]
    ld [hl+], a
    inc de
    dec c
    jr nz, .copy
    ld a, 1
    ldh [rSVBK], a
    ld a, [wReiHistNext]
    inc a
    and REI_HIST - 1
    ld [wReiHistNext], a
    ld a, [wReiHistCount]
    cp REI_HIST
    ret nc
    inc a
    ld [wReiHistCount], a
    ret

; Shows the reply wReiHistAge names, and the marker. a = 0 for no marker.
ReiHist_Show:
    push af
    call Rei_PaneClear
    ld a, [wReiHistCount]
    or a
    jr z, .drawn
    ld a, [wReiHistAge]
    ld b, a
    ld a, [wReiHistNext]
    dec a
    sub b
    and REI_HIST - 1
    call ReiHist_Slot
    ld a, REI_HIST_BANK
    ldh [rSVBK], a
    ld a, [hl+]
    ld c, a
.char
    ld a, [hl+]
    push hl
    push bc
    call Rei_PanePut                ; WRAM0 only, so the bank can stay mapped
    pop bc
    pop hl
    dec c
    jr nz, .char
    ld a, 1
    ldh [rSVBK], a
.drawn
    ld a, T_FR_B                    ; the marker's cells: edge, or "^v n/8"
    ld b, MARK_X
    ld c, MARK_Y
    ld d, MARK_W
    ld e, 1
    call Rei_Fill
    pop af
    or a
    jr z, .push
    ld b, MARK_X
    ld c, MARK_Y
    call Rei_CellAddr
    ld a, T_ARROW_UP
    ld [hl+], a
    ld a, T_ARROW_DN
    ld [hl+], a
    ld a, [wReiHistAge]
    ld b, a
    ld a, [wReiHistCount]
    sub b
    add a, '0' - FONT_FIRST
    ld [hl+], a
    ld a, '/' - FONT_FIRST
    ld [hl+], a
    ld [hl], '0' + REI_HIST - FONT_FIRST
.push
    call Console_WaitVBlank
    call Rei_PaneBlit
    xor a
    ld [wReiPaneDirty], a
    ld hl, MARK_Y * CON_W + MARK_X
    ld b, 1
    ld c, MARK_W
    jp Rei_Blit

; The reply is complete. Returns when the player wants to talk again.
ReiUi_After::
    call ReiFace_Show               ; the mood of what she said
    call ReiHist_Store
    xor a
    ld [wReiHistAge], a
    inc a
    call ReiHist_Show               ; the same words, now with the marker
    ld hl, sReiBack
    ld de, sReiTalk
    call ReiHist_Panel

    ld a, READY_MAGIC               ; a stable window for the harness to read
    ld [wReady], a
.loop
    call Rei_IdleFrame
    ld b, a
    and KB_A | KB_B | KB_START
    jr nz, .leave
    ld a, b
    and KB_UP
    jr z, .down
    ld a, [wReiHistCount]           ; older, if there is one
    ld c, a
    ld a, [wReiHistAge]
    inc a
    cp c
    jr nc, .loop
    jr .page
.down
    ld a, b
    and KB_DOWN
    jr z, .loop
    ld a, [wReiHistAge]
    or a
    jr z, .loop
    dec a
.page
    ld [wReiHistAge], a
    ld a, 1
    call ReiHist_Show
    jr .loop
.leave
    xor a
    ld [wReady], a
    ld [wReiHistAge], a
    jp ReiHist_Show                 ; a = 0: the newest reply, the marker gone

ASSERT REI_HIST == 8, "the ring index is masked, the marker is one digit"

ENDC
