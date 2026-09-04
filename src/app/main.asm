; The demo ROM. Two personalities, decided at assembly time by the exported
; vocabulary: a model whose tokenizer has a newline piece is a conversation
; partner (CHAT_MODE), anything else is the story generator.
;
; This is what ships. src/lab/main.asm is the same model with none of the
; presentation, for the test suite.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "App", ROM0

Run::

IF CHAT_MODE

; The chat loop. One conversation is one stream: the ring keeps the KV cache,
; the absolute position keeps counting, and each exchange is encoded as a
; continuation of the last. The window does the forgetting.
.chat
    call Keyboard_Run           ; blocks until START; empty prompt in chat mode

    ; No table ends and no ring wraps: the stream continues for as long as
    ; the player keeps talking.
    call Chat_Stage             ; "> text" first, then "(nl)> text" after

    ; The keyboard draws its frame into the console shadow, so there is no
    ; transcript to preserve across a visit - every exchange draws its own
    ; screen. The *model* still remembers: the KV ring carries the conversation
    ; even though the display does not.
    call Console_Clear
    call StatusWin_Show
    call Console_Flush

    ld a, CHAT_REPLY_MAX
    ld [wGenSteps], a
    call Type_Enable            ; the reply arrives a character at a time
    ld a, [wChatStarted]
    or a
    jr nz, .cont
    call Encode
    call Generate
    ld a, 1
    ld [wChatStarted], a
    jr .after
.cont
    call EncodeCont
    call Generate_Cont

.after
    call Type_Drain             ; the tail of the reply, and the screen
    call MeasureSelftest        ; last, so the pass cannot overwrite the buffer

    ld a, READY_MAGIC           ; a stable window for the harness to read
    ld [wReady], a
    ; SELECT leaves the reply; START is reserved for sending. When one button
    ; did both, tapping "back" re-queued an empty message the instant the
    ; keyboard appeared, and the app looked stuck generating a reply to
    ; nothing.
.waitSelect
    call Console_WaitVBlank
    call Joy_Read
    ld a, [wJoyNew]
    and KB_SELECT
    jr z, .waitSelect
.release                            ; wait for a clean release, so the press
    call Console_WaitVBlank         ; cannot bleed into the keyboard as a
    call Joy_Read                   ; fresh SELECT and flip its case
    ld a, [wJoyHeld]
    or a
    jr nz, .release
    xor a
    ld [wReady], a
    call StatusWin_Hide
    jp .chat

; Puts the turn marker in front of the typed text, in place and back to front
; so the overlap is safe. The first exchange gets "> "; every later one gets a
; newline first, which is the token that tells the model the last turn ended.
Chat_Stage:
    ld a, [wChatStarted]
    or a
    jr z, :+
    ld b, 3                     ; newline, ">", " "
    jr .shift
:   ld b, 2                     ; ">", " "
.shift
    ld a, [wPromptLen]
    or a
    jr z, .prefix
    ld c, a                     ; c = bytes to move

    ld l, a                     ; hl = source end (text + len - 1)
    ld h, 0
    ld de, wPromptText - 1
    add hl, de

    push hl                     ; de = destination end (source end + b)
    pop de
    ld a, e
    add a, b
    ld e, a
    jr nc, .copy
    inc d
.copy
    ld a, [hl-]
    ld [de], a
    dec de
    dec c
    jr nz, .copy

.prefix
    ld hl, wPromptText
    ld a, b
    cp 3
    jr nz, :+
    ld a, $0A
    ld [hl+], a
:   ld a, $3E                   ; the turn marker, >
    ld [hl+], a
    ld a, $20                   ; ' ' 
    ld [hl+], a

    ; And the trailing newline, which is the whole turn protocol: it tells the
    ; model the player has finished. Without it, the model's first generated
    ; token IS that newline, and the turn-end stop fired on it before a single
    ; word of the reply existed.
    ld a, [wPromptLen]
    add a, b
    ld c, a
    ld l, a
    ld h, 0
    ld de, wPromptText
    add hl, de
    ld a, $0A
    ld [hl], a
    ld a, c
    inc a
    ld [wPromptLen], a
    ret

SECTION "Chat state", WRAM0
wChatStarted: db                ; 0 until the first exchange; boot clears WRAM

ELSE

; The story demo: keyboard, generate, report, repeat.
.app
    call Keyboard_Run           ; blocks until START
    call Encode
    call Console_Clear
    call StatusWin_Show
    call Console_Flush

    xor a                       ; no step limit: the story runs until SELECT.
    ld [wGenSteps], a           ; The state has no window to fall off.
    call Type_Enable            ; characters go out one at a time meanwhile
    call Generate
    call Type_Drain             ; whatever is still queued, and the screen
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
    and KB_START | KB_SELECT    ; either button: back to the keyboard
    jr z, .waitStart
    xor a
    ld [wReady], a
    call StatusWin_Hide
    jp .app

ENDC
