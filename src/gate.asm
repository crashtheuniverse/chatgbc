; The gate as one byte table, the sigmoid folded in.
;
; The twin's state update (py/twin5.py forward_q5) is
;
;     zg = sig_l[zl + 128]                          ; Q0.8, the layer's sigmoid
;     h  = sat8( (zg*ht + (256-zg)*h + 128) >> 8 )
;
; Two identities, each checked over every one of the 256 x 255 x 255 inputs
; (py/tests/test_gate_table.py), make it one table read:
;
;   (1) the result equals h + T with T = (zg*(ht-h) + 128) >> 8, because
;       floor((256h + y) / 256) = h + floor(y / 256);
;   (2) it lies in [min(h,ht), max(h,ht)] - a convex blend - so sat8 never
;       fires, -128 never appears, and the byte sum h + T mod 256 IS h_new.
;
; So the table holds E[v][u] = (T + 128) mod 256 for v the sigmoid value and
; u = d + 256, d = ht - h in [-254, 254]: a 512-byte row per distinct v. Only
; 118 values occur across the three layers' tables (sigmoid_table(-3)'s 70
; are a subset of sigmoid_table(-4)'s 118), so the rows are shared: 118 x
; 512 = 60,416 bytes in four consecutive banks, 32 rows a bank. Reading it
; needs the row's bank and its high address byte, and both are a function of
; (layer, zl) - so the exporter writes per layer two page-aligned ROM0 side
; pages indexed by the RAW zl byte: the bank, then the high byte of the row's
; lower half (d < 0). The biased subtract (ht^$80) - (h^$80) leaves d mod 256
; in a with the borrow set iff d < 0; ccf turns that into the +1 that picks
; the row's upper half for d >= 0. The loop ends `ld a,[hl]; add a,e` with
; e = h^$80: E + h + 128 = h + T + 256, and the byte is the new state.
;
; The buffers are addressed as `ld l, c` with a fixed high byte: wZl, wHt and
; wH each start a WRAM0 page and hold every layer's slice at offset layer *
; DIM, so one index c = layer * DIM + i walks all three, and bc is the wH
; pointer for both the load and the store. The loop is unrolled once per
; layer for the side-page constants; the layer's exit test is one `bit` on c.
;
; Counted per element (M-cycles, CGB double speed):
;   ld h,HIGH(wZl) 2; ld l,c 1; ld a,[hl] 2; ld l,a 1;
;   ld h,HIGH(side) 2; ld a,[hl] 2; ld [rROMB0],a 4; inc h 1; ld d,[hl] 2  = 17
;   ld a,[bc] 2; xor $80 2; ld e,a 1                                       = 22
;   ld h,HIGH(wHt) 2; ld l,c 1; ld a,[hl] 2; xor $80 2; sub e 1; ld l,a 1;
;   ccf 1; ld a,d 1; adc a,0 2; ld h,a 1                                   = 36
;   ld a,[hl] 2; add a,e 1; ld [bc],a 2                                    = 41
;   inc c 1; bit n,c 2; jr z 3                                             = 47
; 47 an element, 46 for the last; per layer ld a,[wLayer] 4 + the cp/jp
; chain (6 a layer tried) + ld bc 3 + call/ret 10. Per token at 3 x 64:
; 192 x 47 - 3 + ~90 = 9,111, against 85,704 + 6,392 for the register
; multiply and the separate sigmoid pass it replaces.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; The page trick needs every layer's slice inside one page, and the exit test
; needs DIM to be a power of two (then c's high bits are the layer).
ASSERT N_LAYERS * DIM <= 256, "gate: the layer slices must share one page"
ASSERT (DIM & (DIM - 1)) == 0, "gate: DIM must be a power of two"
ASSERT GATE_BANK0 + GATE_BANKS <= 256, "gate: bank numbers must fit ROMB0"

SECTION "Gate logits", WRAM0, ALIGN[8]
wZl::      ds N_LAYERS * DIM          ; wz output per layer: gate logits, int8
wGateOut:: ds DIM                     ; GateSelftest's answer, for the harness

SECTION "Gate candidate", WRAM0, ALIGN[8]
wHt::      ds N_LAYERS * DIM          ; wh output per layer: the candidate state

SECTION "Gate code", ROM0

ASSERT LOW(wZl) == 0 && LOW(wHt) == 0, "gate: buffers must start a page"

; One layer's state update, in place: wH slice = gate(wZl, wHt, wH slice)
; for the layer in wLayer.
Gate_Update::
    ld a, [wLayer]
FOR LYR, N_LAYERS
    cp LYR
    jp z, .layer{d:LYR}
ENDR
    ret                                 ; no such layer: leave the state alone

FOR LYR, N_LAYERS
    ; The exit: c runs from LYR * DIM to (LYR + 1) * DIM - 1, whose high
    ; bits are LYR; the lowest set bit of (LYR + 1) * DIM is clear throughout
    ; that range and set the moment c leaves it. At 256 the byte wraps to
    ; zero instead.
    REDEF GATE_END = (LYR + 1) * DIM
    REDEF GATE_BIT = 0
    REPT 8
        IF ((GATE_END >> GATE_BIT) & 1) == 0
            REDEF GATE_BIT = GATE_BIT + 1
        ENDC
    ENDR
.layer{d:LYR}
    ld bc, wH + LYR * DIM               ; bc walks this layer's state
.elem{d:LYR}
    ld h, HIGH(wZl)
    ld l, c
    ld a, [hl]                          ; zl, the raw byte
    ld l, a
    ld h, HIGH(gate_side_l{d:LYR})
    ld a, [hl]                          ; the bank holding its sigmoid's row
    ld [rROMB0], a
    inc h                               ; the next page: the row's high byte
    ld d, [hl]
    ld a, [bc]
    xor $80                             ; h + 128 as a byte
    ld e, a
    ld h, HIGH(wHt)
    ld l, c
    ld a, [hl]
    xor $80                             ; ht + 128 as a byte
    sub e                               ; d mod 256; borrow iff d < 0
    ld l, a
    ccf                                 ; carry iff d >= 0
    ld a, d
    adc a, 0                            ; the row's upper half for d >= 0
    ld h, a
    ld a, [hl]                          ; (T + 128) mod 256
    add a, e                            ; h + T mod 256: the new state
    ld [bc], a
    inc c
    IF GATE_END == 256
    jr nz, .elem{d:LYR}
    ELSE
    bit GATE_BIT, c
    jr z, .elem{d:LYR}
    ENDC
    ret
ENDR
