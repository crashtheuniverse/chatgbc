; A chat turn's input: the typed line staged as the model was trained to read
; it, and - when the engine knows the player's name - the header.
;
; Shared by the cartridge (src/app/main.asm) and the lab ROM, whose
; LAB_GO_STAGE runs Chat_Stage, the encoder and the header on a line the
; harness typed (py/tests/test_rei_header.py against golden5.staged_ids).
; A story build (CHAT_MODE 0) assembles none of it.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

IF CHAT_MODE

SECTION "Chat stage", ROM0

; Puts the turn marker in front of the typed text, in place and back to front
; so the overlap is safe. The first exchange gets "> "; every later one gets a
; newline first, which is the token that tells the model the last turn ended.
Chat_Stage::
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
wChatStarted:: db               ; 0 until the first exchange; boot clears WRAM.
                                ; Exported for Rei's battery save.

ENDC
