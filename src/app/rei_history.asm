; The two ends of a reply, and the replies the cartridge keeps.
;
; ReiUi_ReplyBegin clears her pane and puts the list away while she thinks.
; ReiUi_After runs when the reply is complete: it reads her mood, files the
; reply, adds it to the log, counts the exchange, saves, and raises wReady for
; the harness. Then the input screen comes straight back, her reply still up.
;
; Her replies are filed as text - a length byte and up to 96 characters, eight
; slots in a ring in the save image (WRAM bank 2) - so that "continue" can put
; the last one back in her pane: ReiHist_Render replays its characters through
; Rei_PanePut, the writer the teletype uses, and it wraps and scrolls exactly
; as it did when she said it. Looking back further is the log's business now
; (START); the pane no longer pages. The ring keeps its eight slots because the
; save format does. rSVBK is put back to 1 before anything else runs.
;
; Cost: nothing in ROM0; about 190 bytes of the UI bank, 2 bytes of WRAM0.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

DEF HIST_SLOT  EQU REI_REPLY_MAX + 1

SECTION "Rei history state", WRAM0
wReiHistCount:: db                  ; replies on file, up to REI_HIST
wReiHistNext::  db                  ; the slot the next one goes in

SECTION "Rei history", ROMX, BANK[REI_BANK]

; She is about to answer: an empty pane, and the list makes way - a blank bar
; over three dots, the middle one on the screen's centre line (ReiThinkMap, a
; whole row: py/gen_rei_art.py says why it is not a dot tile printed three
; times).
ReiUi_ReplyBegin::
    call Rei_PaneClear
    call Console_WaitVBlank
    call Rei_PaneBlit
    xor a
    ld [wReiPaneDirty], a
    ld b, LIST_X
    ld c, BAR_Y
    ld d, LIST_W
    ld e, LIST_H + 1
    call Rei_Fill
    ld hl, ReiThinkMap
    ld b, LIST_X
    ld c, LIST_Y + LIST_H / 2
    ld d, LIST_W
    ld e, 1
    call Rei_DrawMap
    call Console_WaitVBlank
    ld hl, BAR_Y * CON_W + LIST_X
    ld b, LIST_H + 1
    ld c, LIST_W
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

; The newest reply on file, into her pane's shadow. No VRAM: the main screen's
; first draw pushes it, when a conversation is continued from the save.
ReiHist_Render::
    call Rei_PaneClear
    ld a, [wReiHistCount]
    or a
    ret z
    ld a, [wReiHistNext]
    dec a
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
    ret

; The reply is complete. Her pane already shows it.
ReiUi_After::
    call ReiFace_Show               ; the mood of what she said
    call ReiHist_Store
    ld hl, wReiReply                ; her side of the log
    ld a, [wReiReplyLen]
    ld c, a
    ld b, 0
    call ReiLog_Add
    ld hl, wReiLines
    call ReiSave_Count
    call ReiSave_Write              ; interrupts are off: the run is over
    ld a, READY_MAGIC               ; the exchange is whole and saved; the flag
    ld [wReady], a                  ; stays up until the next message is sent
    ret

ASSERT REI_HIST == 8, "the ring index is masked"

ENDC
