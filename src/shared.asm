; State shared across kernels that has no single owner.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; Page-aligned for the gate (src/gate.asm), which addresses every layer's
; slice as `ld l, c` under one fixed high byte.
SECTION "Shared model state", WRAM0, ALIGN[8]
; The being's memory, whole: one int8 vector per layer, persisting across
; tokens. 192 bytes where the v0.4 cache was 20 KB. Zeroed at conversation
; start; between tokens it is never touched except by the gate.
wH::           ds N_LAYERS * DIM
wAbsPos::      db             ; step counter for prompt indexing only - it may
                              ; wrap freely, there is no table to fall off
wAttShift::    db             ; per-layer softmax input shift
wAttOutShift:: db             ; per-layer attention output shift
wLayer::       db             ; layer being evaluated
wHeadQ::       dw             ; q slice for the head being evaluated
