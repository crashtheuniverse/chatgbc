; Rei's mood: read off the reply's text, shown on her face and in the band
; under it. No model change - the words decide.
;
;   "forget", "sorry" or "sad" anywhere   -> sad      (a tear)
;   otherwise a '!'                       -> happy    (a heart)
;   otherwise a '?'                       -> curious
;   otherwise                             -> calm
;
; ReiFace_Set copies the four pictures the mood needs into wReiFaces, where the
; ROM0 handler can reach them with the UI bank unmapped: the mood's face, the
; same face blinking, and the two talking mouths.
;
; Cost: nothing in ROM0; about 260 bytes of the UI bank, one byte of WRAM0.

IF DEF(REI_UI)

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "app/rei.inc"
INCLUDE "rei_art.inc"

SECTION "Rei face state", WRAM0
wReiMood:: db                       ; MOOD_*

SECTION "Rei face", ROMX, BANK[REI_BANK]

sReiSadWords:
    db "forget", 0
    db "sorry", 0
    db "sad", 0
    db 0

; The palette of each mood's band: the symbol's colour.
ReiMoodPal:
    db PAL_GREEN, PAL_RED, PAL_AMBER, PAL_BLUE

; wReiReply -> wReiMood.
ReiFace_Scan::
    ld de, sReiSadWords
.word
    ld a, [de]
    or a
    jr z, .marks
    call ReiFace_Find
    ld a, MOOD_SAD
    jr c, .store
.skip                               ; to the next word
    ld a, [de]
    inc de
    or a
    jr nz, .skip
    jr .word
.marks
    ld b, '!'
    call ReiFace_FindChar
    ld a, MOOD_HAPPY
    jr c, .store
    ld b, '?'
    call ReiFace_FindChar
    ld a, MOOD_CURIOUS
    jr c, .store
    ld a, MOOD_CALM
.store
    ld [wReiMood], a
    ret

; b = character. Carry set if the reply holds it.
ReiFace_FindChar:
    ld a, [wReiReplyLen]
    or a
    ret z
    ld c, a
    ld hl, wReiReply
.loop
    ld a, [hl+]
    cp b
    jr z, .hit
    dec c
    jr nz, .loop
    or a
    ret
.hit
    scf
    ret

; de = $00-terminated word. Carry set if the reply holds it. Keeps de.
ReiFace_Find:
    ld a, [wReiReplyLen]
    or a
    ret z
    ld b, a                         ; b = places left to start from
    ld hl, wReiReply
.start
    push hl
    push de
    ld c, b                         ; c = characters left from here
.cmp
    ld a, [de]
    or a
    jr z, .hit                      ; the word ran out first: found
    inc c
    dec c
    jr z, .miss
    cp [hl]
    jr nz, .miss
    inc hl
    inc de
    dec c
    jr .cmp
.miss
    pop de
    pop hl
    inc hl
    dec b
    jr nz, .start
    or a
    ret
.hit
    pop de
    pop hl
    scf
    ret

; a = picture number in ReiFaceMaps, de = destination.
ReiFace_Copy:
    swap a                          ; * FACE_CELLS
    ld l, a
    ld h, 0
    ld bc, ReiFaceMaps
    add hl, bc
    ld bc, FACE_CELLS
    jp CopyBytes

; wReiMood -> wReiFaces, and the idle picture chosen. No VRAM.
ReiFace_Set::
    ld a, [wReiMood]
    ld de, wReiFaces + FSEL_IDLE * FACE_CELLS
    call ReiFace_Copy
    ld a, [wReiMood]
    add a, FACE_CALM_BLINK
    call ReiFace_Copy               ; de runs on: the pictures are in FSEL order
    ld a, FACE_TALK_A
    call ReiFace_Copy
    ld a, FACE_TALK_B
    call ReiFace_Copy
    xor a
    ld [wReiFaceSel], a
    ld [wReiTalking], a
    inc a
    ld [wReiFaceDirty], a
    ret

; The band for wReiMood, into the shadow.
ReiFace_DrawMood::
    ld a, [wReiMood]
    ld hl, ReiMoodMaps
    ld bc, REI_BAND_W * REI_BAND_H
    or a
    jr z, .draw
.next
    add hl, bc
    dec a
    jr nz, .next
.draw
    ld b, MOOD_X
    ld c, MOOD_Y
    ld d, REI_BAND_W
    ld e, REI_BAND_H
    jp Rei_DrawMap

; The band's palette. LCD off or VBlank.
ReiFace_MoodAttr::
    ld a, [wReiMood]
    ld e, a
    ld d, 0
    ld hl, ReiMoodPal
    add hl, de
    ld a, [hl]
    ld b, MOOD_X
    ld c, MOOD_Y
    ld d, REI_BAND_W
    ld e, REI_BAND_H
    jp Rei_Attr

; After a reply, LCD on: the new mood on the face and in the band.
ReiFace_Show::
    call ReiFace_Scan
    call ReiFace_Set
    call ReiFace_DrawMood
    call Console_WaitVBlank
    xor a
    ld [wReiFaceDirty], a
    call Rei_FaceBlit
    ld hl, MOOD_Y * CON_W + MOOD_X
    ld b, REI_BAND_H
    ld c, REI_BAND_W
    call Rei_Blit
    jp ReiFace_MoodAttr

ASSERT FACE_CALM == MOOD_CALM && FACE_SAD == MOOD_SAD, "mood numbers index ReiFaceMaps"
ASSERT FACE_SAD_BLINK == FACE_CALM_BLINK + MOOD_SAD

ENDC
