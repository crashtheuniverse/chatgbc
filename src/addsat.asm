; The residual add, saturating: wX[i] = sat8(wX[i] + wXb[i]) for i < DIM.
;
; The twin's line is Q.add_requant(x, ex, y, ex, ex) with both sides on the
; stream grid (py/quant.py): shr_round by zero is the identity, so it is
; sat8(x + y) = clip(x + y, -127, 127). Both inputs are sat8 outputs, hence
; in [-127, 127], and the sum is in [-254, 254]: the int8 add wraps only
; when the true sum is outside [-128, 127], and the wrapped byte then has
; the sign the true sum does not. So the overflow test is the classic one,
; bit 7 of (s ^ x) & (s ^ y): set exactly when x and y share a sign and s
; does not - and then the answer is 127 if s came out negative, -127 if
; positive. Without overflow the byte is the sum, except the one value the
; symmetric range excludes: -128 (from x + y = -128, no wrap) is -127, as
; sat8 clips it. The audit checked this rule against Q.sat8(x + y) on all
; 255 x 255 pairs (verdicts_gate.json, "Adds (if not fused)");
; py/tests/test_module_f.py repeats the check on a byte model of this loop
; and runs the loop itself over the exporter's vectors.
;
; Placement makes the loop: wX starts a page and wXb is the same page at
; offset DIM = 64 (src/state.asm), so one index in c reaches x as l = c and
; y as l = c | $40, and the store goes back to x after `res 6, l`. The exit
; test is bit 6 of the index after the increment: c = 64 ends it.
;
; Counted per element (M-cycles, CGB double speed):
;   ld l,c 1; ld a,[hl] 2; ld d,a 1; set 6,l 2; ld a,[hl] 2; ld e,a 1    =  9
;   add a,d 1; ld b,a 1; xor d 1; ld d,a 1; ld a,b 1; xor e 1; and d 1;
;   rlca 1; ld a,b 1                                                    = 18
;   jr c 2 (not taken); cp $80 2; jr z 2 (not taken)                    = 24
;   res 6,l 2; ld [hl],a 2; inc c 1; bit 6,c 2; jr z 3                  = 34
; An overflow or an exact -128 takes a detour of 5 to 7 cycles; on the
; model's activations both are rare. Per call: ld h 2 + ld c 2 + 64 x 34
; - 1 (the last jr falls through) + ret 4 + call 6 = 2,189; six passes a
; token (three att, three ffn) = 13,134, against 18,664 for the register
; form with its push/pop and sign-extended 16-bit add that this replaces
; (48 an element).

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

ASSERT DIM == 64, "addsat: the index walks x and y with bit 6 of l, and ends on bit 6 of c"
ASSERT LOW(wX) == 0, "addsat: wX must start a page"
ASSERT wXb == wX + DIM, "addsat: wXb must be the same page at offset DIM"

SECTION "AddSat code", ROM0

; wX[i] = sat8(wX[i] + wXb[i]), i = 0..DIM-1. Clobbers a, bc, de, hl.
AddSat_Stream::
    ld h, HIGH(wX)
    ld c, 0
.elem
    ld l, c
    ld a, [hl]                      ; x
    ld d, a
    set 6, l                        ; -> wXb[i]
    ld a, [hl]                      ; y
    ld e, a
    add a, d                        ; s = x + y, wrapped
    ld b, a
    xor d                           ; s ^ x
    ld d, a
    ld a, b
    xor e                           ; s ^ y
    and d                           ; bit 7: x and y agree, s disagrees
    rlca                            ; -> carry
    ld a, b
    jr c, .sat
    cp $80                          ; -128 only arrives unwrapped
    jr z, .m128
.store
    res 6, l                        ; -> wX[i]
    ld [hl], a
    inc c
    bit 6, c
    jr z, .elem
    ret
.m128
    ld a, -127                      ; the symmetric range has no -128
    jr .store
.sat
    ld a, 127                       ; the wrapped byte's sign is the true sum's opposite
    bit 7, b
    jr nz, .store
    ld a, -127
    jr .store
