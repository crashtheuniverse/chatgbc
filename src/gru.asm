; The cheap square: the MLP's activation.
;
; Relu2_Row is what replaced SwiGLU: clamp, one quarter-square lookup for the
; exact square, one per-layer shift. Where SwiGLU cost a sigmoid table read
; AND a generic multiply per element, this costs neither.
;
; The recurrent gate that used to share this file - the sigmoid row and the
; quarter-square state update - lives in src/gate.asm now, as one byte table
; with the sigmoid folded in.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Gru HRAM", HRAM
hGruCnt: db
hGruOuter: db                       ; Relu2_Row's half-width outer count

SECTION "Gru pointers", WRAM0
wGzPtr: dw                          ; the walk pointers: source, destination
wGtPtr: dw
wR2Shift:: db                       ; this layer's ReLU^2 closing shift

SECTION "Gru code 2", ROM0

; wH1 -> wHb: u = sat8(shr_round(relu(a)^2, r2_shift)). The square is exact:
; tbl_qsq[2a] = a*a for 0 <= a <= 127, one lookup.
Relu2_Row::
    ld a, LOW(wH1)
    ld [wGzPtr + 0], a
    ld a, HIGH(wH1)
    ld [wGzPtr + 1], a
    ld a, LOW(wHb)
    ld [wGtPtr + 0], a
    ld a, HIGH(wHb)
    ld [wGtPtr + 1], a
    ; hidden can exceed an 8-bit count, so the walk runs twice at half width -
    ; the pointers carry across, only the counter reloads. One expert's
    ; hidden is a single pass.
IF EXPERTS
    ASSERT HID_EXP <= 256, "an expert's hidden must fit an 8-bit count (0 = 256)"
    ld a, 1
    ldh [hGruOuter], a
.half
    ld a, LOW(HID_EXP)              ; 256 wide counts as 0: the dec-jr loop
    ldh [hGruCnt], a                ; below runs 256 times from zero
ELSE
    ld a, 2
    ldh [hGruOuter], a
.half
    ld a, HIDDEN / 2
    ldh [hGruCnt], a
ENDC
.elem
    ld a, [wGzPtr + 0]
    ld l, a
    ld a, [wGzPtr + 1]
    ld h, a
    ld a, [hl]
    bit 7, a
    jr z, .positive
    xor a                           ; relu: negative squares to zero
    jr .store
.positive
    ld l, a                         ; a^2 = tbl_qsq[2a]; u16 entries, so the
    ld h, 0                         ; byte offset is 4a
    add hl, hl
    add hl, hl
    ld de, tbl_qsq
    add hl, de
    ld a, [hl+]
    ld e, a
    ld h, [hl]
    ld l, e                         ; hl = a*a, at most 16,129
    ld e, 0                         ; e:hl, non-negative
    ld a, [wR2Shift]                ; the exporter asserts it is >= 0
    ld b, a
    call ShiftRound24
    call Sat8_24
.store
    ld c, a
    ld a, [wGtPtr + 0]
    ld l, a
    ld a, [wGtPtr + 1]
    ld h, a
    ld [hl], c
    ld hl, wGzPtr
    inc [hl]
    jr nz, :+
    ld hl, wGzPtr + 1
    inc [hl]
:   ld hl, wGtPtr
    inc [hl]
    jr nz, :+
    ld hl, wGtPtr + 1
    inc [hl]
:   ldh a, [hGruCnt]
    dec a
    ldh [hGruCnt], a
    jp nz, .elem
    ldh a, [hGruOuter]
    dec a
    ldh [hGruOuter], a
    jr nz, .half
    ret
