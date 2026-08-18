; Does code run faster out of HRAM?
;
; On some handhelds it does. The GBA's IWRAM sits on a 32-bit bus with no wait
; states while EWRAM is 16-bit with two, so copying a hot routine into IWRAM is
; a real and well-known speedup. The instinct carries over easily, and it is
; worth knowing whether it survives the trip.
;
; On the Game Boy every region answers in one M-cycle - ROM, WRAM, HRAM alike -
; and instruction fetch is no exception, so it should make no difference at all.
; HRAM's advantage here is entirely in the instruction encodings that reach it:
; `ldh a, [c]` is one byte, `ldh a, [n]` two, `ld a, [nn]` three.
;
; Rather than assert that, measure it. The same loop runs from ROM and from
; HRAM and the ROM's own cycle counter compares them. py/tests/test_fetch.py
; asserts they agree; if they ever stop agreeing, the comment above is wrong.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"

DEF FETCH_ITERS EQU 4000
DEF FETCH_SLOT  EQU 32              ; HRAM reserved for the copied body

SECTION "Fetch bench HRAM", HRAM
hFetchBody: ds FETCH_SLOT

SECTION "Fetch bench state", WRAM0
wRomCycles::  ds 4
wHramCycles:: ds 4

SECTION "Fetch bench", ROM0

; Nothing in here is an absolute address: `jr` is relative and `ret` needs no
; label, so the identical bytes run correctly from either location. That is what
; makes the comparison fair. The body is mostly `nop` on purpose - a nop is
; nothing but a fetch, which is exactly the cost under test.
FetchBody:
.loop
REPT 16
    nop
ENDR
    dec bc
    ld a, b
    or c
    jr nz, .loop
    ret
FetchBodyEnd:

ASSERT FetchBodyEnd - FetchBody <= FETCH_SLOT, "fetch body outgrew its HRAM slot"

MeasureFetch::
    ld hl, FetchBody
    ld de, hFetchBody
    ld bc, FetchBodyEnd - FetchBody
    call CopyBytes

    call Prof_Start
    ld bc, FETCH_ITERS
    call FetchBody
    call Prof_Stop
    ld de, wRomCycles
    call SaveCycles

    call Prof_Start
    ld bc, FETCH_ITERS
    call hFetchBody
    call Prof_Stop
    ld de, wHramCycles
    jp SaveCycles
