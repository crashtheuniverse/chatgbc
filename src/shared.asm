; State shared across kernels that has no single owner.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

SECTION "Shared model state", WRAM0
wKvec::        ds KV_DIM      ; this position's K, before it goes to the cache
wVvec::        ds KV_DIM      ; and its V
wAttShift::    db             ; per-layer softmax input shift
wAttOutShift:: db             ; per-layer attention output shift
wPos::         db             ; current sequence position
wLayer::       db             ; layer being evaluated
wHeadQ::       dw             ; q slice for the head being evaluated
