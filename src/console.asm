; Text console: a WRAM shadow tilemap pushed to VRAM in one GDMA burst.
;
; Text lives in wConsole as raw tile indices (ASCII - 32). Tests read that
; buffer directly, which keeps them independent of the font's appearance.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"

SECTION "Console buffer", WRAM0, ALIGN[4]   ; GDMA source must be 16-byte aligned
wConsole:: ds CON_SIZE

SECTION "Console state", WRAM0
wCursorX:: db
wCursorY:: db

SECTION "Console code", ROM0

; Fills the shadow buffer with spaces and homes the cursor.
Console_Clear::
    ld hl, wConsole
    ld bc, CON_SIZE
    ld d, ' ' - FONT_FIRST
.loop
    ld a, d
    ld [hl+], a
    dec bc
    ld a, b
    or c
    jr nz, .loop

    xor a
    ld [wCursorX], a
    ld [wCursorY], a
    ret

; Copies the shadow buffer to the BG tilemap. Safe only outside rendering, so
; callers on a live LCD should use Console_Flush instead.
Console_FlushNow::
    ld a, HIGH(wConsole)
    ldh [rHDMA1], a
    ld a, LOW(wConsole)
    ldh [rHDMA2], a
    ld a, HIGH(TILEMAP0)
    ldh [rHDMA3], a
    ld a, LOW(TILEMAP0)
    ldh [rHDMA4], a
    ld a, VDMA_LEN_MODE_GENERAL | ((CON_SIZE / 16) - 1)
    ldh [rHDMA5], a
    ret

; Waits for the start of VBlank, then flushes.
Console_Flush::
    ldh a, [rLCDC]
    bit B_LCDC_ENABLE, a
    jr z, Console_FlushNow      ; LCD off: LY never advances, so don't wait on it
.leaveVBlank
    ldh a, [rLY]
    cp 144
    jr nc, .leaveVBlank         ; already inside VBlank; let it finish
.enterVBlank
    ldh a, [rLY]
    cp 144
    jr c, .enterVBlank
    jr Console_FlushNow

; hl = address of the cursor cell in the shadow buffer. Only a and hl change.
Console_CursorAddr::
    push de
    ld a, [wCursorY]
    ld h, 0
    ld l, a
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl
    add hl, hl                  ; y * CON_W (32)
    ld de, wConsole
    add hl, de
    pop de
    ld a, [wCursorX]
    add a, l
    ld l, a
    ret nc
    inc h
    ret

; a = ASCII character. $0A starts a new line.
Console_PutChar::
    cp $0A
    jr z, Console_NewLine

    push hl
    push bc
    sub FONT_FIRST
    ld b, a
    call Console_CursorAddr
    ld [hl], b
    pop bc
    pop hl

    ld a, [wCursorX]
    inc a
    ld [wCursorX], a
    cp CON_VIS_W
    ret c
    ; row is full, wrap to the next line

Console_NewLine::
    xor a
    ld [wCursorX], a
    ld a, [wCursorY]
    inc a
    cp CON_H
    jr c, .store
    call Console_Scroll         ; stay on the last row, move everything else up
    ld a, CON_H - 1
.store
    ld [wCursorY], a
    ret

; Shifts the shadow buffer up one row and blanks the bottom one. The rows are
; contiguous in the shadow (stride CON_W), so this is one forward copy, and the
; next flush pushes the result out with the usual single GDMA.
Console_Scroll::
    ld de, wConsole
    ld hl, wConsole + CON_W
    ld bc, (CON_H - 1) * CON_W
.move
    ld a, [hl+]
    ld [de], a
    inc de
    dec bc
    ld a, b
    or c
    jr nz, .move

    ld hl, wConsole + (CON_H - 1) * CON_W
    ld b, CON_W
    ld a, ' ' - FONT_FIRST
.blank
    ld [hl+], a
    dec b
    jr nz, .blank
    ret

; hl = pointer to a $00-terminated string.
Console_PrintStr::
    ld a, [hl+]
    or a
    ret z
    push hl
    call Console_PutChar
    pop hl
    jr Console_PrintStr

; b = column, c = row.
Console_SetPos::
    ld a, b
    ld [wCursorX], a
    ld a, c
    ld [wCursorY], a
    ret
