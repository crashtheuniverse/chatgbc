; Rei's screen: where everything is, in tiles. One persistent 20 x 18 BG map.
;
;   x 0-5   y 0-5    her face, a 6 x 6 frame around 4 x 4 tiles of art
;   x 0-5   y 6-8    the mood band: one icon, centred under the face, no frame
;   x 6-19  y 0-8    her words: a 14 x 9 frame around a 12 x 7 text pane
;   x 0-19  y 9-11   your words: a 20 x 3 frame around one 18-character row
;   x 0-19  y 12-17  the keys: a 20 x 6 frame around 4 rows - the canned
;                    prompts or the keyboard
;
; Only the Rei build assembles any of this: build.ps1 -Rei defines REI_UI.

IF !DEF(REI_INC)
DEF REI_INC EQU 1

DEF REI_BANK    EQU 31              ; the UI has the last ROM bank to itself

DEF FACE_FX     EQU 0               ; the face frame
DEF FACE_FY     EQU 0
DEF FACE_FW     EQU 6
DEF FACE_FH     EQU 6
DEF FACE_X      EQU 1               ; the art inside it
DEF FACE_Y      EQU 1
DEF FACE_W      EQU 4
DEF FACE_H      EQU 4
DEF FACE_CELLS  EQU FACE_W * FACE_H

DEF MOOD_X      EQU 0
DEF MOOD_Y      EQU 6

DEF OUT_FX      EQU 6
DEF OUT_FY      EQU 0
DEF OUT_FW      EQU 14
DEF OUT_FH      EQU 9
DEF PANE_X      EQU 7
DEF PANE_Y      EQU 1
DEF PANE_W      EQU 12
DEF PANE_H      EQU 7
DEF PANE_OFF    EQU PANE_Y * CON_W + PANE_X     ; offset into the map

DEF SAY_FX      EQU 0
DEF SAY_FY      EQU 9
DEF SAY_FW      EQU 20
DEF SAY_FH      EQU 3
DEF SAY_X       EQU 1
DEF SAY_Y       EQU 10
DEF SAY_W       EQU 18

DEF KEYS_FX     EQU 0
DEF KEYS_FY     EQU 12
DEF KEYS_FW     EQU 20
DEF KEYS_FH     EQU 6
DEF KEYS_X      EQU 1
DEF KEYS_Y      EQU 13
DEF KEYS_W      EQU 18
DEF KEYS_H      EQU 4

DEF REI_REPLY_MAX EQU 96            ; characters of a reply kept as text
DEF REI_HIST      EQU 8             ; replies remembered
DEF REI_HIST_BANK EQU 2             ; WRAM bank of the save image (history, log)
                                    ; and the log screen's shadow; 2..6 are free
DEF REI_LOG_LINES EQU 64            ; lines of conversation kept for the log
DEF REI_LOG_COLS  EQU 18
DEF REI_LOG_SLOT  EQU REI_LOG_COLS + 1      ; who said it, then the tiles
DEF REI_TEXT_MAX  EQU 44            ; typed characters: PROMPT_MAX less the
                                    ; turn marker and newline Chat_Stage adds

; wReiFaces holds four pictures of FACE_CELLS tiles; wReiFaceSel picks one.
DEF FSEL_IDLE   EQU 0               ; the mood of her last reply
DEF FSEL_BLINK  EQU 1
DEF FSEL_TALK_A EQU 2               ; mouth shut
DEF FSEL_TALK_B EQU 3               ; mouth open

DEF MOOD_CALM    EQU 0              ; the order of ReiFaceMaps / ReiMoodMaps
DEF MOOD_HAPPY   EQU 1
DEF MOOD_CURIOUS EQU 2
DEF MOOD_SAD     EQU 3

DEF REI_LCDC EQU LCDC_ON | LCDC_BG_ON | LCDC_BLOCK01 | LCDC_BG_9800

; Maps the UI bank and calls into it. Only from ROM0.
MACRO REI_FAR
    ld a, REI_BANK
    ld [rROMB0], a
    call \1
ENDM

ENDC
