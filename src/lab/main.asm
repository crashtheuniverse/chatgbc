; The lab ROM: the same model with none of the presentation.
;
; The demo boots into a keyboard, draws a frame and waits for START. That costs
; the test suite wall-clock it cannot spare, and loop latency is the thing this
; project actually optimises for. So the suite builds this instead.
;
; It parks in an idle loop advertising LAB_IDLE. The harness fills in the prompt
; and the number of tokens it wants, then writes LAB_GO. One ROM instance can
; therefore serve several runs of different lengths without rebooting - a test
; that only needs to see the encoder run can ask for one token instead of
; ninety-six.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Lab state", WRAM0
wLabState:: db                  ; LAB_IDLE while waiting for parameters
wLabGo::    db                  ; the harness writes LAB_GO to start a run

SECTION "Lab", ROM0

Run::
    call Lab_DefaultPrompt      ; so a run with no setup still matches the golden

.idle
    xor a
    ld [wReady], a
    ld [wLabGo], a
    ld a, LAB_IDLE
    ld [wLabState], a
.wait
    ld a, [wLabGo]
    cp LAB_GO_NORM
    jr z, .norm
    cp LAB_GO_SHIFT
    jr z, .shift
    cp LAB_GO
    jr nz, .wait
    xor a
    ld [wLabState], a           ; running; wGenSteps and the prompt are set

    call Encode
    call Console_Clear
    call Console_Flush
    call Generate
    call Console_Flush
    call ReportTiming
    call Console_Flush

    ; Last, so the forward pass cannot overwrite the buffer it checks.
    call MeasureSelftest
    jr .done

.norm                           ; one kernel, on the vector the harness wrote
    xor a
    ld [wLabState], a
    call RmsNorm
    jr .done

.shift                          ; e:hl = wX+0..2, b = wX+3 -> wXb+0..2
    xor a
    ld [wLabState], a
    ld a, [wX + 0]
    ld l, a
    ld a, [wX + 1]
    ld h, a
    ld a, [wX + 2]
    ld e, a
    ld a, [wX + 3]
    ld b, a
    call ShiftRound24
    ld a, l
    ld [wXb + 0], a
    ld a, h
    ld [wXb + 1], a
    ld a, e
    ld [wXb + 2], a

.done
    ld a, READY_MAGIC
    ld [wReady], a
.held
    ld a, [wLabGo]              ; hold the result until the harness clears it,
    or a                        ; whichever go value started this run
    jr nz, .held
    jr .idle

Lab_DefaultPrompt:
    ld hl, sLabPrompt
    ld de, wPromptText
    ld b, 0
.copy
    ld a, [hl+]
    or a
    jr z, .done
    ld [de], a
    inc de
    inc b
    jr .copy
.done
    ld a, b
    ld [wPromptLen], a
    ld a, GEN_STEPS
    ld [wGenSteps], a
    ret

sLabPrompt: db "Once upon a time", 0
