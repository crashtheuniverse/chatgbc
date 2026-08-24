; What does the classifier actually cost? Timed directly, at boot, on data
; that does not move - the same discipline the RMSNorm mismeasurement bought.
;
; This file builds identically against the input-major classifier (master) and
; the register-argmax one, because both export `Classify::` with the same
; contract: wXb in, wBestTok out. Whatever else changed, this number is the
; whole of it.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Cls bench state", WRAM0
wClsBenchCycles:: ds 4

SECTION "Cls bench", ROM0

MeasureClassify::
    ld hl, wXb                      ; a plausible activation vector: mixed
    ld b, DIM                       ; signs, no saturation
    ld a, 3
.seed
    ld [hl+], a
    add a, 11
    and $3F
    sub 24
    dec b
    jr nz, .seed

    ; wGenCount is zero this early, so NoRepeat_Ok exits at once and no retry
    ; fires: this times exactly one full classification.
    call Prof_Start
    call Classify
    call Prof_Stop
    ld de, wClsBenchCycles
    jp SaveCycles
