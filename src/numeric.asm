; Decimal and hex output for 32-bit values. Display only - tests read raw bytes.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"

SECTION "Numeric state", WRAM0
wNum::      ds 4                ; little-endian working value
wDigits::   ds 10               ; the rendered decimal, no terminator
wDigitLen:: db

SECTION "Numeric code", ROM0

; hl = pointer to a 4-byte little-endian value. Prints it in decimal.
Print_Dec32At::
    ld de, wNum
    ld b, 4
.copy
    ld a, [hl+]
    ld [de], a
    inc de
    dec b
    jr nz, .copy
    ; fall through

; Prints wNum in decimal with no leading zeros. Destroys wNum.
Print_Dec32::
    call Dec32_Render
    ld hl, wDigits
    ld a, [wDigitLen]
    ld b, a
.out
    ld a, [hl+]
    push hl
    push bc
    call Console_PutChar
    pop bc
    pop hl
    dec b
    jr nz, .out
    ret

; Renders wNum into wDigits with no leading zeros, length in wDigitLen.
; Destroys wNum.
;
; Two things print numbers - the console and the status window - and they format
; through here rather than each carrying their own loop, which is why they can
; never disagree about a value.
Dec32_Render::
    xor a
    ld [wDigitLen], a
    ld hl, .powers
    ld c, 0                     ; set once a significant digit has been emitted
    ld d, 10                    ; powers of ten remaining
.nextPower
    ld b, '0'
.subLoop
    call Num_Sub32
    jr c, .underflow
    inc b
    jr .subLoop
.underflow
    call Num_Add32              ; put back the subtraction that went negative

    ld a, b
    cp '0'
    jr nz, .emit
    ld a, c
    or a
    jr z, .skip                 ; still in the leading run of zeros
    ld a, '0'
.emit
    ld c, 1
    push hl
    push de
    push af
    ld a, [wDigitLen]
    inc a
    ld [wDigitLen], a
    dec a
    ld e, a
    ld d, 0
    ld hl, wDigits
    add hl, de
    pop af
    ld [hl], a
    pop de
    pop hl
.skip
    inc hl
    inc hl
    inc hl
    inc hl
    dec d
    jr nz, .nextPower

    ld a, c
    or a
    ret nz
    ld a, '0'                   ; the value was zero, so nothing emitted yet
    ld [wDigits], a
    ld a, 1
    ld [wDigitLen], a
    ret

.powers
    dl 1000000000
    dl 100000000
    dl 10000000
    dl 1000000
    dl 100000
    dl 10000
    dl 1000
    dl 100
    dl 10
    dl 1

; wNum -= [hl..hl+3]. hl and de survive; carry set if it borrowed.
; pop only affects flags for `pop af`, so the carry from the last sbc survives.
Num_Sub32:
    push hl
    push de
    ld de, wNum
    ld a, [de]
    sub a, [hl]
    ld [de], a
REPT 3
    inc de
    inc hl
    ld a, [de]
    sbc a, [hl]
    ld [de], a
ENDR
    pop de
    pop hl
    ret

; wNum += [hl..hl+3]. hl and de survive.
Num_Add32:
    push hl
    push de
    ld de, wNum
    ld a, [de]
    add a, [hl]
    ld [de], a
REPT 3
    inc de
    inc hl
    ld a, [de]
    adc a, [hl]
    ld [de], a
ENDR
    pop de
    pop hl
    ret

; a = byte to print as two hex digits.
Print_Hex8::
    push af
    swap a
    call Print_Nibble
    pop af
    ; fall through

; Low nibble of a, as one hex digit.
Print_Nibble::
    and $0F
    add a, '0'
    cp '9' + 1
    jr c, .emit
    add a, 'A' - ('9' + 1)
.emit
    jp Console_PutChar
