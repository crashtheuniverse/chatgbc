; The two ends of a reply, and the replies she has given before.
;
; ReiUi_ReplyBegin clears her pane and puts the keys away while she thinks.
; ReiUi_After runs when the reply is complete: it reads her mood, files the
; reply, adds it to the log, counts the exchange, saves, and raises wReady for
; the harness. Then the input screen comes straight back, her reply still up.
;
; Her last eight replies can be paged from the input screen at any time
; (src/app/rei_input.asm: UP off the top of the list or the keys for the one
; before, DOWN off the bottom for the one after). A marker in the bottom edge
; of her frame says which is showing: 8/8 is the newest once eight are on file.
; Sending a message goes back to the newest.
;
; A reply is kept as text, not as tiles: a length byte and up to 96 characters,
; eight slots in a ring in the save image (WRAM bank 2). Showing one replays its
; characters through Rei_PanePut, the same writer the teletype uses, so an old
; reply wraps and scrolls exactly as it did when she said it. rSVBK is put back
; to 1 before anything else runs.
;
; Cost: nothing in ROM0; about 300 bytes of the UI bank, 3 bytes of WRAM0.

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

SECTION "Rei history", ROMX, BANK[REI_BANK]

sReiThinking: db "   ", T_DOT + FONT_FIRST, " ", T_DOT + FONT_FIRST, " ", T_DOT + FONT_FIRST, 0

; The marker's cells as plain frame edge, into the shadow.
ReiHist_NoMark:
    ld a, T_FR_B
    ld b, MARK_X
    ld c, MARK_Y
    ld d, MARK_W
    ld e, 1
    jp Rei_Fill

; Pane and marker, shadow -> screen, in one VBlank.
ReiHist_Push:
    call Console_WaitVBlank
    call Rei_PaneBlit
    xor a
    ld [wReiPaneDirty], a
    ld hl, MARK_Y * CON_W + MARK_X
    ld b, 1
    ld c, MARK_W
    jp Rei_Blit

; She is about to answer: an empty pane, no marker, and the keys make way.
ReiUi_ReplyBegin::
    xor a
    ld [wReiHistAge], a             ; whatever was being read, the newest is next
    call Rei_PaneClear
    call ReiHist_NoMark
    call ReiHist_Push
    xor a                           ; the keys' interior: three dots
    ld b, KEYS_X
    ld c, KEYS_Y
    ld d, KEYS_W
    ld e, KEYS_H
    call Rei_Fill
    ld hl, sReiThinking
    ld b, KEYS_X + 3
    ld c, KEYS_Y + 1
    call Rei_Print
    call Console_WaitVBlank
    ld hl, KEYS_Y * CON_W + KEYS_X
    ld b, KEYS_H
    ld c, KEYS_W
    jp Rei_Blit

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

; The reply wReiHistAge names and the marker, into the shadow. No VRAM.
ReiHist_Render::
    call Rei_PaneClear
    call ReiHist_NoMark
    ld a, [wReiHistCount]
    or a
    ret z
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

    ld b, MARK_X                    ; "^v n/8"
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
    ret

; The same, and onto the screen.
ReiHist_Show::
    call ReiHist_Render
    jp ReiHist_Push

; The reply before the one showing, if there is one.
ReiHist_Older::
    ld a, [wReiHistCount]
    ld c, a
    ld a, [wReiHistAge]
    inc a
    cp c
    ret nc
    jr ReiHist_Page

; The reply after the one showing, if it is not the newest.
ReiHist_Newer::
    ld a, [wReiHistAge]
    or a
    ret z
    dec a
ReiHist_Page:
    ld [wReiHistAge], a
    jr ReiHist_Show

; The reply is complete.
ReiUi_After::
    call ReiFace_Show               ; the mood of what she said
    call ReiHist_Store
    ld hl, wReiReply                ; her side of the log
    ld a, [wReiReplyLen]
    ld c, a
    ld b, 0
    call ReiLog_Add
    xor a
    ld [wReiHistAge], a
    call ReiHist_Show               ; the same words, now with the marker
    ld hl, wReiLines
    call ReiSave_Count
    call ReiSave_Write              ; interrupts are off: the run is over
    ld a, READY_MAGIC               ; the exchange is whole and saved; the flag
    ld [wReady], a                  ; stays up until the next message is sent
    ret

ASSERT REI_HIST == 8, "the ring index is masked, the marker is one digit"

ENDC
