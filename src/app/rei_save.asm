; The battery save: the conversation survives the power switch.
;
; The Rei cartridge is MBC5+RAM+BATTERY with one 8 KB bank of SRAM. What is
; kept is everything a conversation is made of:
;
;   $A000  4  magic: "REI" and the layout's version
;   $A004  2  checksum: SAVE_SEED plus every byte of the body, 16 bits
;   $A006     the body, a copy of wReiImage (WRAM bank 2):
;          2    visits          boots that reached the main screen
;          2    lines           exchanges completed; both saturate at 65,535
;          1    wChatStarted    the model has a conversation going
;          1    wAbsPos         the model's step counter
;          1    wReiMood        the mood of her last reply
;          2    wReiHistCount, wReiHistNext    her reply history's ring
;          2    wReiLogCount, wReiLogNext      the conversation log's ring
;          N_LAYERS * DIM   wH, the model's recurrent state - its whole memory
;          8 * 97           her last eight replies, as text
;          64 * 19          the log: a who byte and 18 tiles a line
;
; wH, wAbsPos and wChatStarted are all that Generate_Cont and EncodeCont carry
; from one exchange to the next: every other generator variable (wPrev, the
; no-repeat record, wRunStart, the token buffer) is rebuilt at the start of
; each exchange. py/tests/test_rei_ui.py proves it: a conversation continued
; from a save answers exactly as the uninterrupted one does.
;
; The history and the log live in the image already; the WRAM0 variables are
; gathered into it before a save and scattered from it after a load, by one
; table. A save clears the magic first and writes it last, so a save cut short
; by the power switch is a save that does not exist. SRAM is enabled only
; inside these routines, never from an interrupt, and the RAM bank register is
; left at 0. rROMB0 is not touched: the forward pass's bank writes go to
; $2000-$3FFF and cannot reach RAMG ($0000-$1FFF) or RAMB ($4000-$5FFF).
;
; Cost: nothing in ROM0; about 290 bytes of the UI bank, 5 bytes of WRAM0,
; 2,195 bytes of WRAM bank 2 and 2,201 of the cartridge's 8,192 of SRAM.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"
INCLUDE "app/rei.inc"

DEF SAVE_VERSION EQU 1
DEF SAVE_SEED    EQU $5A17          ; so that an all-zero body does not sum to zero
DEF SAVE_VARS    EQU 2 + 2 + 1 + 1 + 1 + 1 + 1 + 1 + 1   ; ReiSaveTable, less wH

SECTION "Rei save state", WRAM0
wReiVisits:: dw
wReiLines::  dw
wReiSaveOut: db                     ; ReiSave_Move's direction

SECTION "Rei save image", WRAMX[$D000], BANK[REI_HIST_BANK]
wReiImage::
wReiImgVars: ds SAVE_VARS
wReiImgH:    ds N_LAYERS * DIM
wReiHist::   ds REI_HIST * (REI_REPLY_MAX + 1)
wReiLog::    ds REI_LOG_LINES * REI_LOG_SLOT
wReiImageEnd:
DEF SAVE_BODY EQU wReiImageEnd - wReiImage

SECTION "Rei cartridge RAM", SRAM[$A000], BANK[0]
sReiMagic: ds 4
sReiSum:   dw
sReiBody:  ds SAVE_BODY

SECTION "Rei save", ROMX, BANK[REI_BANK]

ReiSaveMagic: db "REI", SAVE_VERSION

; The WRAM0 side of the image, in the image's order: address, length.
ReiSaveTable:
    dw wReiVisits
    db 2
    dw wReiLines
    db 2
    dw wChatStarted
    db 1
    dw wAbsPos
    db 1
    dw wReiMood
    db 1
    dw wReiHistCount
    db 1
    dw wReiHistNext
    db 1
    dw wReiLogCount
    db 1
    dw wReiLogNext
    db 1
    dw wH
    db N_LAYERS * DIM
    dw 0
ASSERT N_LAYERS * DIM < 256, "the table's lengths are bytes"

; a = 0: WRAM0 -> image. a = 1: image -> WRAM0. The image's bank must be mapped.
ReiSave_Move:
    ld [wReiSaveOut], a
    ld de, wReiImage
    ld hl, ReiSaveTable
.entry
    ld a, [hl+]
    ld c, a
    ld a, [hl+]
    ld b, a
    or c
    ret z
    ld a, [hl+]
    push hl
    ld l, a                         ; l = bytes
.byte
    ld a, [wReiSaveOut]
    or a
    jr nz, .out
    ld a, [bc]
    ld [de], a
    jr .next
.out
    ld a, [de]
    ld [bc], a
.next
    inc bc
    inc de
    dec l
    jr nz, .byte
    pop hl
    jr .entry

; de = the checksum of the body in SRAM. SRAM must be enabled.
ReiSave_Sum:
    ld hl, sReiBody
    ld bc, SAVE_BODY
    ld de, SAVE_SEED
.loop
    ld a, [hl+]
    add a, e
    ld e, a
    jr nc, :+
    inc d
:   dec bc
    ld a, b
    or c
    jr nz, .loop
    ret

ReiSave_Open:
    ld a, RAMG_SRAM_ENABLE
    ld [rRAMG], a
    xor a
    ld [rRAMB], a
    ret

ReiSave_Close:
    xor a
    ld [rRAMG], a
    ret

; Writes the conversation to the cartridge. Interrupts must be off.
ReiSave_Write::
    ld a, REI_HIST_BANK
    ldh [rSVBK], a
    xor a                           ; gather
    call ReiSave_Move
    call ReiSave_Open
    xor a
    ld [sReiMagic], a               ; no save, until it is whole
    ld hl, wReiImage
    ld de, sReiBody
    ld bc, SAVE_BODY
    call CopyBytes
    call ReiSave_Sum
    ld a, e
    ld [sReiSum + 0], a
    ld a, d
    ld [sReiSum + 1], a
    ld hl, ReiSaveMagic
    ld de, sReiMagic
    ld bc, 4
    call CopyBytes
    call ReiSave_Close
    ld a, 1
    ldh [rSVBK], a
    ret

; Carry set if the cartridge holds a whole save of this version.
ReiSave_Check::
    call ReiSave_Open
    ld hl, ReiSaveMagic
    ld de, sReiMagic
    ld b, 4
.magic
    ld a, [de]
    cp [hl]
    jr nz, .none
    inc hl
    inc de
    dec b
    jr nz, .magic
    call ReiSave_Sum
    ld a, [sReiSum + 0]
    cp e
    jr nz, .none
    ld a, [sReiSum + 1]
    cp d
    jr nz, .none
    call ReiSave_Close
    scf
    ret
.none
    call ReiSave_Close
    or a
    ret

; The save, into the image and the WRAM0 variables. Only after ReiSave_Check.
ReiSave_Load::
    ld a, REI_HIST_BANK
    ldh [rSVBK], a
    call ReiSave_Open
    ld hl, sReiBody
    ld de, wReiImage
    ld bc, SAVE_BODY
    call CopyBytes
    call ReiSave_Close
    ld a, 1                         ; scatter
    call ReiSave_Move
    ld a, 1
    ldh [rSVBK], a
    ret

; "new friend": no save on the cartridge, nothing remembered in RAM.
ReiSave_Forget::
    call ReiSave_Open
    xor a
    ld [sReiMagic], a
    call ReiSave_Close
    ld a, REI_HIST_BANK
    ldh [rSVBK], a
    ld hl, wReiImage
    ld bc, SAVE_BODY
.zero
    xor a
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .zero
    ld a, 1                         ; and the zeros out to WRAM0
    call ReiSave_Move
    ld a, 1
    ldh [rSVBK], a
    ret

; hl = a 16-bit counter. One more, stopping at 65,535.
ReiSave_Count::
    inc [hl]
    ret nz
    inc hl
    inc [hl]
    ret nz
    ld a, $FF                       ; it wrapped: pin it
    ld [hl-], a
    ld [hl], a
    ret

ENDC
