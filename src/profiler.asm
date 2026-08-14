; Cycle profiler built on TIMA.
;
; TAC_16KHZ increments TIMA once per 64 M-cycles. That divider is tied to the
; CPU clock, not to wall-clock time, so the reading means the same thing in
; single and double speed - and it means the same thing on real hardware as
; under an emulator. Every timing number this project quotes comes from here.
;
; TIMA overflows every 256 ticks (16384 M-cycles); the timer interrupt extends
; the count to 24 bits. The ISR costs ~25 M-cycles per 16384, i.e. ~0.15%.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"

SECTION "Profiler state", WRAM0
wProfHi:      dw         ; TIMA overflows, maintained by the ISR
wProfTicks::  ds 4       ; last measurement in ticks; 24-bit value, zero-extended
wProfCycles:: ds 4       ; the same, converted to M-cycles

SECTION "Timer IRQ", ROM0[$50]
    jp Timer_ISR

SECTION "Profiler code", ROM0

Timer_ISR:
    push af
    push hl
    ld hl, wProfHi
    inc [hl]
    jr nz, .done
    inc hl
    inc [hl]
.done
    pop hl
    pop af
    reti

; Starts a measurement. Leaves interrupts enabled with only the timer armed.
Prof_Start::
    di
    xor a
    ldh [rTAC], a               ; stop the timer before touching it
    ldh [rTIMA], a
    ldh [rTMA], a               ; overflow reloads to zero
    ld [wProfHi + 0], a
    ld [wProfHi + 1], a
    ldh [rIF], a                ; drop anything already pending
    ld a, IE_TIMER
    ldh [rIE], a
    ld a, TAC_START | TAC_16KHZ
    ldh [rTAC], a
    ei
    ret

; Ends a measurement, leaving the result in wProfTicks and wProfCycles.
Prof_Stop::
    di
    xor a
    ldh [rTAC], a               ; freeze the count before reading it
    ldh a, [rTIMA]
    ld [wProfTicks + 0], a

    ldh a, [rIF]
    bit B_IE_TIMER, a           ; an overflow the ISR never got to service
    ld a, [wProfHi + 0]
    ld l, a
    ld a, [wProfHi + 1]
    ld h, a                     ; ld/ldh do not disturb the Z flag from `bit`
    jr z, .noPending
    inc hl
.noPending
    ld a, l
    ld [wProfTicks + 1], a
    ld a, h
    ld [wProfTicks + 2], a
    xor a
    ld [wProfTicks + 3], a      ; zero-extend so it can be read as 32-bit
    ; fall through

; wProfCycles = wProfTicks * PROF_TICK_CYCLES (64).
Prof_ComputeCycles::
    ld a, [wProfTicks + 0]
    ld [wProfCycles + 0], a
    ld a, [wProfTicks + 1]
    ld [wProfCycles + 1], a
    ld a, [wProfTicks + 2]
    ld [wProfCycles + 2], a
    xor a
    ld [wProfCycles + 3], a

    ld b, 6                     ; 1 << 6 == 64
.shift
    ld hl, wProfCycles
    sla [hl]
    inc hl
    rl [hl]
    inc hl
    rl [hl]
    inc hl
    rl [hl]
    dec b
    jr nz, .shift
    ret
