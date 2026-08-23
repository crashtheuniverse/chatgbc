; The demo ROM: keyboard, generate, report, repeat.
;
; This is what ships. src/lab/main.asm is the same model with none of the
; presentation, for the test suite.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "App", ROM0

Run::

.app
    call Keyboard_Run           ; blocks until START
    call Encode
    call Console_Clear
    call StatusWin_Show
    call Console_Flush

    ld a, APP_GEN_STEPS
    ld [wGenSteps], a
    call Generate
    call Console_Flush
    ; No ReportTiming here: the status bar has been showing cycles per token
    ; live for the whole run, so printing the same number into the text at the
    ; end puts it on screen twice and reads as a glitch. The lab ROM still
    ; prints it, because nothing there is watching a status bar.

    ; Last, so the forward pass cannot overwrite the buffer it checks.
    call MeasureSelftest

    ld a, READY_MAGIC           ; a stable window for the harness to read
    ld [wReady], a
.waitStart
    call Console_WaitVBlank
    call Joy_Read
    ld a, [wJoyNew]
    and KB_START
    jr z, .waitStart
    xor a
    ld [wReady], a
    call StatusWin_Hide
    jp .app
