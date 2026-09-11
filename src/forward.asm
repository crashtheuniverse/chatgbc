; The transformer forward pass and greedy decode loop.
;
; Mirrors forward_q() in py/quant.py step for step. Every matvec goes through
; the same Matvec_Run / Requant_All pair; only the manifest entry, the shift
; table and the destination change.

INCLUDE "hardware.inc"
INCLUDE "chatgbc.inc"
INCLUDE "model.inc"

; Bank 1 is free in v0.5 - there is no KV cache - so the diffstep snapshots
; live there and cost WRAM0 nothing. The probe sets SVBK before reading.
SECTION "Forward debug", WRAMX[$D000], BANK[1]
; Layer 0 snapshots, so py/diffstep.py can tell an attention bug from an FFN one.
wDbgAtt::   ds DIM
wDbgFfn::   ds DIM
wDbgRes::   ds DIM
wDbgXb::    ds DIM              ; layer 0: post-rmsnorm input to wz/wh
wDbgZl::    ds DIM              ; layer 0: gate logits
wDbgZg::    ds DIM              ; layer 0: gates after sigmoid
wDbgHt::    ds DIM              ; layer 0: candidate state
wDbgH1::    ds HIDDEN           ; layer 0: w1 output
wDbgHb::    ds HIDDEN           ; layer 0: after relu^2
wDbgXf::    ds DIM              ; layer 0: the FFN's input, after rms_ffn
wDbgRoute:: ds 8                ; layer 0: the router's four sums, int16
wDbgAo::    ds DIM              ; layer 0: wo's output after requant, before the add
wDbgAccWo:: ds DIM * 2          ; layer 0: wo's raw int16 accumulators

INCLUDE "census.inc"

SECTION "Forward state", WRAM0
wToken::    dw
wStep::     db
wMatIdx:    db
wBestTok::  dw
wClsPart::  db
wRetries::  ds 2                    ; no-repeat retries this run, for telemetry
wBlocked::  ds NOREPEAT_TRIES * 2   ; tokens the no-repeat rule has turned down
wBlockedN:: db                      ; how many of them, this step
wExpert::   db                      ; the expert the router chose this layer
wExpIdx::   db                      ; layer * EXPERTS + expert: the matrix index
wExpHi:     db                      ; scratch for the router's 16-bit compare

SECTION "Forward code", ROM0

; --- matvec plumbing -------------------------------------------------------

; Points the matvec at a matrix's precomputed product tables.
;   a = bank, hl = base address
SetLut:
    ld [wMvLutBank], a
    ld a, l
    ld [wMvLutAddr + 0], a
    ld a, h
    ld [wMvLutAddr + 1], a
    ret

; Points the matvec at one (tensor, layer) chunk.
;   hl = banks table, de = addrs table, a = layer
SetMatrix:
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [wMvBank], a
    ld h, d
    ld l, e
    add hl, bc
    add hl, bc
    ld a, [hl+]
    ld [wMvW + 0], a
    ld a, [hl]
    ld [wMvW + 1], a
    ret

; hl = shift table pointer for layer a.
ShiftTable:
    ld c, a
    ld b, 0
    add hl, bc
    add hl, bc
    ld a, [hl+]
    ld c, a
    ld a, [hl]
    ld h, a
    ld l, c
    ret

SetXPtr:
    ld a, l
    ld [wMvXPtr + 0], a
    ld a, h
    ld [wMvXPtr + 1], a
    ret

; --- one layer -------------------------------------------------------------

; Runs layer wLayer over wX.
ForwardLayer::
    ld a, 1                         ; the diffstep snapshots live in bank 1,
    ldh [rSVBK], a                  ; and nothing else banked runs mid-layer
    ; --- recurrent block: rmsnorm, gates, state, project ---
    ld hl, rms_att
    ld a, [wLayer]
    ld de, DIM
    call OffsetByLayer
    ld a, l
    ld [wRnGain + 0], a
    ld a, h
    ld [wRnGain + 1], a
    ld hl, rmsatt_shift
    ld a, [wLayer]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [wRnShift], a
    CENSUS_START
    ld hl, wX
    call SetRnSrc
    ld hl, wXb
    call SetRnDst
    call RmsNorm
    CENSUS_END 0

    CENSUS_START
    ld hl, wXb
    call SetXPtr
IF TERNARY || BINARY
    ld a, BLOCKS_DIM                ; the block kernel counts inputs in threes
    ld [wMvIn], a
ELSE
    ld a, DIM
    ld [wMvIn], a
    ld a, BANK(lut_wz)              ; gate logits
    ld hl, lut_wz
    call SetLut
ENDC
    ld hl, wz_banks
    ld de, wz_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
IF TERNARY || BINARY
    BLOCK_RUN
ELSE
    call Matvec_Run
ENDC
    CENSUS_END 1
    CENSUS_START
    ld hl, wz_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wZl
    call Requant_All16
    CENSUS_END 2

    CENSUS_START
    ld a, [wLayer]                  ; snapshot the logits for diffstep
    or a
    jr nz, :+
    ld hl, wXb
    ld de, wDbgXb
    ld bc, DIM
    call CopyBytes
    ld hl, wZl
    ld de, wDbgZl
    ld bc, DIM
    call CopyBytes
:
    CENSUS_END 17
    CENSUS_START
    ld hl, sig_tables               ; the layer's sigmoid, exponent baked in
    ld a, [wLayer]
    ld c, a
    ld b, 0
    add hl, bc
    add hl, bc
    ld a, [hl+]
    ld [wGruSig + 0], a
    ld a, [hl]
    ld [wGruSig + 1], a
    call Sigmoid_Row
    CENSUS_END 3
    CENSUS_START
    ld a, [wLayer]
    or a
    jr nz, :+
    ld hl, wZg
    ld de, wDbgZg
    ld bc, DIM
    call CopyBytes
:
    CENSUS_END 17

    CENSUS_START
    ld hl, wXb                      ; the candidate state
    call SetXPtr
IF TERNARY || BINARY
    ld a, BLOCKS_DIM
    ld [wMvIn], a
ELSE
    ld a, DIM
    ld [wMvIn], a
    ld a, BANK(lut_wh)
    ld hl, lut_wh
    call SetLut
ENDC
    ld hl, wh_banks
    ld de, wh_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
IF TERNARY || BINARY
    BLOCK_RUN
ELSE
    call Matvec_Run
ENDC
    CENSUS_END 4
    CENSUS_START
    ld hl, wh_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wHt
    call Requant_All16
    CENSUS_END 5

    CENSUS_START
    ld hl, wH                       ; this layer's 64 bytes of memory
    ld a, [wLayer]
    ld de, DIM
    call OffsetByLayer
    ld a, l
    ld [wGruH + 0], a
    ld a, h
    ld [wGruH + 1], a
    CENSUS_END 17
    CENSUS_START
    ld a, [wLayer]
    or a
    jr nz, :+
    ld hl, wHt
    ld de, wDbgHt
    ld bc, DIM
    call CopyBytes
:
    CENSUS_END 17
    CENSUS_START
    call Gate_Update                ; h += z * (h~ - h), in place
    CENSUS_END 6

    CENSUS_START
    ld a, [wLayer]                  ; snapshot layer 0's state for diffstep
    or a
    jr nz, :+
    ld a, [wGruH + 0]
    ld l, a
    ld a, [wGruH + 1]
    ld h, a
    ld de, wDbgAtt
    ld bc, DIM
    call CopyBytes
:
    CENSUS_END 17
    CENSUS_START
    ld a, [wGruH + 0]               ; project the state back into the stream
    ld l, a
    ld a, [wGruH + 1]
    ld h, a
    call SetXPtr
IF TERNARY || BINARY
    ld a, BLOCKS_DIM
    ld [wMvIn], a
ELSE
    ld a, DIM
    ld [wMvIn], a
    ld a, BANK(lut_wo)
    ld hl, lut_wo
    call SetLut
ENDC
    ld hl, wo_banks
    ld de, wo_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
IF TERNARY || BINARY
    BLOCK_RUN
ELSE
    call Matvec_Run
ENDC
    CENSUS_END 7
    ld a, [wLayer]                  ; snapshot wo's raw accumulators
    or a
    jr nz, :+
    ld hl, wAcc
    ld de, wDbgAccWo
    ld bc, DIM * 2
    call CopyBytes
:
    CENSUS_START
    ld hl, wo_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wXb
    call Requant_All16
    CENSUS_END 8
    ld a, [wLayer]                  ; snapshot wo's output before the add
    or a
    jr nz, :+
    ld hl, wXb
    ld de, wDbgAo
    ld bc, DIM
    call CopyBytes
:
    CENSUS_START
    ld hl, wXb                      ; residual: both sides already share X_EXP
    ld de, wX
    ld b, DIM
    call AddSaturating
    CENSUS_END 9
    CENSUS_START
    ld a, [wLayer]                  ; snapshot x after the recurrent residual
    or a
    jr nz, :+
    ld hl, wX
    ld de, wDbgRes
    ld bc, DIM
    call CopyBytes
:
    CENSUS_END 17

    ; --- feed-forward block: rmsnorm, w1, relu^2, w2 ---
    CENSUS_START
    ld hl, rms_ffn
    ld a, [wLayer]
    ld de, DIM
    call OffsetByLayer
    ld a, l
    ld [wRnGain + 0], a
    ld a, h
    ld [wRnGain + 1], a
    ld hl, rmsffn_shift
    ld a, [wLayer]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [wRnShift], a
    ld hl, wX
    call SetRnSrc
    ld hl, wXb
    call SetRnDst
    call RmsNorm
    CENSUS_END 10

IF EXPERTS
    ; --- experts: route, then one expert's w1 and w2 ---------------------
    ; The router is a 64 -> EXPERTS ternary matvec; its argmax picks the
    ; expert, ties to the lowest index as the twin's argmax does. Then the
    ; matrix index is layer * EXPERTS + expert, and an expert's w1 (HID_EXP
    ; outputs) and w2 (BLOCKS_HID_EXP inputs) each run whole: one fits a
    ; bank, the other fits int16.
    CENSUS_START
    ld hl, wXb
    call SetXPtr
    ld a, ROUTER_BLOCKS             ; ternary codes, blocks of three, whatever
    ld [wMvIn], a                   ; kernel the rows run
    ld hl, router_banks
    ld de, router_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, EXPERTS
    call Matvec_SetOut
    call Matvec3_Run                ; the router stays on the ternary kernel
    ld a, [wLayer]                  ; layer-0 snapshots: the FFN input and
    or a                            ; the router's sums, for the twin to check
    jr nz, :+
    ld hl, wXb
    ld de, wDbgXf
    ld bc, DIM
    call CopyBytes
    ld hl, wAcc
    ld de, wDbgRoute
    ld bc, 8
    call CopyBytes
:

    ld hl, wAcc
    ld de, 0                        ; best so far: -32768, high byte pre-flipped
    ld b, 0                         ; the index being examined
    ld [wExpert], a                 ; a is 0 here: expert 0 unless beaten
.route
    ld a, [hl+]
    ld c, a                         ; low
    ld a, [hl+]
    xor $80                         ; high, sign-flipped: unsigned order is signed order
    ld [wExpHi], a
    ld a, c
    sub e                           ; borrow if low < best low
    ld a, [wExpHi]
    sbc d                           ; carry set iff value < best
    jr c, .keep
    jr nz, .take                    ; high differs: greater
    ld a, c
    cp e
    jr z, .keep                     ; equal: the earlier index stays
.take
    ld a, [wExpHi]
    ld d, a
    ld e, c
    ld a, b
    ld [wExpert], a
.keep
    inc b
    ld a, b
    cp EXPERTS
    jr nz, .route

    ld a, [wLayer]                  ; matrix index = layer * EXPERTS + expert
    add a, a
    add a, a                        ; EXPERTS is 4; the exporter asserts it
    ld hl, wExpert
    add a, [hl]
    ld [wExpIdx], a

    ld hl, wXb
    call SetXPtr
    ld a, BLOCKS_DIM
    ld [wMvIn], a
    ld hl, w1_banks
    ld de, w1_addrs
    ld a, [wExpIdx]
    call SetMatrix
    ld hl, HID_EXP
    call Matvec_SetOut
    BLOCK_RUN
    CENSUS_END 11
    CENSUS_START
    ld hl, w1_shifts
    ld a, [wExpIdx]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wH1
    call Requant_All16
    CENSUS_END 12
    ld a, [wLayer]                  ; layer-0 snapshots, as the dense path keeps
    or a
    jr nz, :+
    ld hl, wH1
    ld de, wDbgH1
    ld bc, HID_EXP
    call CopyBytes
:

    CENSUS_START
    call Relu2_Row                  ; the activation, and its list of nonzeros
    CENSUS_END 13
    ld a, [wLayer]
    or a
    jr nz, :+
    ld hl, wHb
    ld de, wDbgHb
    ld bc, HID_EXP
    call CopyBytes
:

    CENSUS_START
    call W2_Run                     ; sparse over the list, or dense over wHb
    CENSUS_END 14
    CENSUS_START
    ld hl, w2_shifts
    ld a, [wExpIdx]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wXb
    call Requant_All16
    CENSUS_END 15
    ld a, [wLayer]
    or a
    jr nz, :+
    ld hl, wXb
    ld de, wDbgFfn
    ld bc, DIM
    call CopyBytes
:
IF DEF(CENSUS)
    CENSUS_START
    ld hl, wXb
    ld de, wX
    ld b, DIM
    call AddSaturating
    CENSUS_END 16
    ret
ELSE
    ld hl, wXb
    ld de, wX
    ld b, DIM
    jp AddSaturating
ENDC
ELSE

    CENSUS_START
    ; w1 runs as two output halves. A whole tensor at hidden 352 is 22,528
    ; bytes - it cannot fit an MBC5 bank, and a weight walk crossing $8000
    ; would read VRAM as weights. Each half fits at any size the 8-bit
    ; counters allow, and requants its own rows with its own shift table.
    ld hl, wXb
    call SetXPtr
IF TERNARY || BINARY
    ld a, BLOCKS_DIM
    ld [wMvIn], a
ELSE
    ld a, DIM
    ld [wMvIn], a
    ld a, BANK(lut_w1)
    ld hl, lut_w1
    call SetLut
ENDC
    ld hl, w1a_banks
    ld de, w1a_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, FFN_SPLIT
    call Matvec_SetOut
IF TERNARY || BINARY
    BLOCK_RUN
ELSE
    call Matvec_Run
ENDC
    CENSUS_END 11
    CENSUS_START
    ld hl, w1a_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wH1
    call Requant_All16
    CENSUS_END 12
    CENSUS_START
    ld hl, w1b_banks
    ld de, w1b_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, HIDDEN - FFN_SPLIT
    call Matvec_SetOut
IF TERNARY || BINARY
    BLOCK_RUN
ELSE
    call Matvec_Run
ENDC
    CENSUS_END 11
    CENSUS_START
    ld hl, w1b_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wH1 + FFN_SPLIT
    call Requant_All16
    CENSUS_END 12

    ld a, [wLayer]
    or a
    jr nz, :+
    ld hl, wH1
    ld de, wDbgH1
    ld bc, HIDDEN
    call CopyBytes
:
    CENSUS_START
    call Relu2_Row                  ; the activation: one page lookup each
    CENSUS_END 13
    ld a, [wLayer]
    or a
    jr nz, :+
    ld hl, wHb
    ld de, wDbgHb
    ld bc, HIDDEN
    call CopyBytes
:

    ; w2 runs as two input halves into the same accumulators - RunAccum after
    ; Run, same order as one pass, so the sums are bit-identical. The signed
    ; product tables carry no bias (Requant_SetBias is a no-op), so nothing
    ; double-counts. One requant at the end with w2's single shift table.
    CENSUS_START
    ld hl, wHb
    call SetXPtr
IF TERNARY || BINARY
    ; Two input halves, each an exact int16 sum, each requantized and added
    ; into the stream in turn - the twin's order. The first half here; the
    ; second follows its own requant and add below.
    ld a, W2_BLOCKS_A
    ld [wMvIn], a
    ld hl, w2a_banks
    ld de, w2a_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
    BLOCK_RUN
ELSE
    ld a, FFN_SPLIT
    ld [wMvIn], a
    ld a, BANK(lut_w2)
    ld hl, lut_w2
    call SetLut
    ld hl, w2a_banks
    ld de, w2a_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
    call Matvec_Run
    ld hl, wHb + FFN_SPLIT
    call SetXPtr
    ld a, HIDDEN - FFN_SPLIT
    ld [wMvIn], a
    ld hl, w2b_banks
    ld de, w2b_addrs
    ld a, [wLayer]
    call SetMatrix
    call Matvec_RunAccum
ENDC
    CENSUS_END 14
    CENSUS_START
    ld hl, w2_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wXb
    call Requant_All16
    CENSUS_END 15
    CENSUS_START
    ld a, [wLayer]                  ; snapshot layer 0's FFN output
    or a
    jr nz, :+
    ld hl, wXb
    ld de, wDbgFfn
    ld bc, DIM
    call CopyBytes
:
    CENSUS_END 17
IF TERNARY || BINARY
    CENSUS_START
    ld hl, wXb
    ld de, wX
    ld b, DIM
    call AddSaturating              ; the first half joins the stream
    CENSUS_END 16
    ; the second half: inputs from W2_SPLIT_IN, same rows, same shifts
    CENSUS_START
    ld hl, wHb + W2_SPLIT_IN
    call SetXPtr
    ld a, W2_BLOCKS_B
    ld [wMvIn], a
    ld hl, w2b_banks
    ld de, w2b_addrs
    ld a, [wLayer]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
    BLOCK_RUN
    CENSUS_END 14
    CENSUS_START
    ld hl, w2_shifts
    ld a, [wLayer]
    call ShiftTable
    ld d, h
    ld e, l
    ld bc, wXb
    call Requant_All16
    CENSUS_END 15
IF DEF(CENSUS)
    CENSUS_START
    ld hl, wXb
    ld de, wX
    ld b, DIM
    call AddSaturating
    CENSUS_END 16
    ret
ELSE
    ld hl, wXb
    ld de, wX
    ld b, DIM
    jp AddSaturating
ENDC
ELSE
IF DEF(CENSUS)
    CENSUS_START
    ld hl, wXb
    ld de, wX
    ld b, DIM
    call AddSaturating
    CENSUS_END 16
    ret
ELSE
    ld hl, wXb
    ld de, wX
    ld b, DIM
    jp AddSaturating
ENDC
ENDC
ENDC                                ; EXPERTS

IF EXPERTS
; The routed expert's w2 into wAcc, by whichever exact kernel is cheaper for
; this token: the sparse one over the (i, u) list src/relu2.asm just wrote,
; or - past W2_SPARSE_MAX nonzero u, where the sparse pass could cost more
; than the dense one - the block kernel over the whole of wHb. Both leave
; the same integers in wAcc, so the choice only bounds the worst case. The
; requant that follows counts rows by wMvOut and reads its shift table from
; the dense blob's bank: the block kernel sets both on its way, the sparse
; one neither (it leaves its column blob's bank mapped), so set them here.
; Returns a = 0 for the sparse path, 1 for the dense - the lab's selftest
; checks the guard by it; the forward pass ignores it.
W2_Run::
    ld a, [wSpCount]
    cp W2_SPARSE_MAX + 1
    jr nc, .dense
    ld a, [wExpIdx]
    call MatvecSparse_Run
    ld hl, DIM                      ; w1 left wMvOut at HID_EXP
    call Matvec_SetOut
    ld hl, w2_shbanks
    ld a, [wExpIdx]
    ld c, a
    ld b, 0
    add hl, bc
    ld a, [hl]
    ld [rROMB0], a
    xor a
    ret
.dense
    ld hl, wHb
    call SetXPtr
    ld a, BLOCKS_HID_EXP
    ld [wMvIn], a
    ld hl, w2_banks
    ld de, w2_addrs
    ld a, [wExpIdx]
    call SetMatrix
    ld hl, DIM
    call Matvec_SetOut
    BLOCK_RUN
    ld a, 1
    ret
ENDC

SetRnSrc:
    ld a, l
    ld [wRnSrc + 0], a
    ld a, h
    ld [wRnSrc + 1], a
    ret

SetRnDst:
    ld a, l
    ld [wRnDst + 0], a
    ld a, h
    ld [wRnDst + 1], a
    ret

; hl += a * de
OffsetByLayer:
    or a
    ret z
    ld b, a
.loop
    add hl, de
    dec b
    jr nz, .loop
    ret

; de[i] = sat8(de[i] + hl[i]) for b elements.
;
; Two int8s sum inside int16, so the whole element lives in registers: both
; sign-extended, added as 16-bit, and saturated to [-127, 127] by the same
; rule as Requant_Sat8. The census put the previous version - both operands
; extended into the 32-bit scratch, added there, saturated back out - at
; 440 cycles an element for one add.
AddSaturating::
.elem
    push bc
    ld a, [hl+]
    ld c, a
    add a, a
    sbc a, a
    ld b, a                         ; bc = hl[i], sign-extended
    ld a, [de]
    push hl
    ld l, a
    add a, a
    sbc a, a
    ld h, a                         ; hl = de[i], sign-extended
    add hl, bc                      ; the sum, in [-256, 254]
    ld a, l
    add a, a
    sbc a, a
    cp h                            ; h is the sign extension of l: it fits
    jr nz, .sat
    ld a, l
    cp $80
    jr nz, .store
    ld a, -127                      ; -128 is outside the symmetric range
    jr .store
.sat
    bit 7, h
    ld a, 127
    jr z, .store
    ld a, -127
.store
    pop hl
    pop bc
    ld [de], a
    inc de
    dec b
    jr nz, .elem
    ret

; wToken -> the argmax token, left in wBestTok.
Forward::
    CENSUS_START
    call EmbedToken
    CENSUS_END 18

    xor a
    ld [wLayer], a
.layer
    call ForwardLayer
    ld a, [wLayer]
    inc a
    ld [wLayer], a
    cp N_LAYERS
    jp c, .layer

    CENSUS_START
    ld hl, rms_final
    ld a, l
    ld [wRnGain + 0], a
    ld a, h
    ld [wRnGain + 1], a
    ld a, RMSFINAL_SHIFT
    ld [wRnShift], a
    ld hl, wX
    call SetRnSrc
    ld hl, wXb
    call SetRnDst
    call RmsNorm
    CENSUS_END 19
IF DEF(CENSUS)
    CENSUS_START
    call Classify                   ; timed as a stage, not quoted from a bench
    CENSUS_END 20
    ret
ENDC
    ; fall through

; Greedy decode needs argmax and nothing else - no softmax, no stored logits,
; and now no stored accumulators either. src/classifier.asm builds every
; input's product table into a WRAM bank once, then walks the vocabulary
; output-major: each logit is summed in a register pair, compared against the
; best so far, and forgotten.
Classify::
    call Cls_BuildTables

    ; Rank-walk the vocabulary until a token turns up that does not complete a
    ; 4-gram this run has already emitted. A retry re-runs the argmax with the
    ; turned-down token on the blocked list - the stored sums the old design
    ; re-scanned are exactly the storage this kernel deleted, and retries are
    ; rare: about six across a 160-token run.
    xor a
    ld [wBlockedN], a
.retry
    call Cls_Argmax
    call NoRepeat_Ok
    ret nz                          ; nothing repeated: take it
    ld a, [wBlockedN]
    cp NOREPEAT_TRIES
    ret nc                          ; out of patience: keep the best on offer
    ld l, a
    ld h, 0
    add hl, hl
    ld de, wBlocked
    add hl, de
    ld a, [wBestTok + 0]
    ld [hl+], a
    ld a, [wBestTok + 1]
    ld [hl], a
    ld hl, wBlockedN
    inc [hl]
    ld hl, wRetries                 ; count them: a retry re-runs the whole
    inc [hl]                        ; argmax now, so the rate matters
    jr nz, :+
    ld hl, wRetries + 1
    inc [hl]
:   jr .retry

; Z set when wBestTok would complete a 4-gram this run has already emitted,
; Z clear when it is safe to take.
;
; Searches every earlier position rather than only the recent ones: the loops
; worth breaking are the ones that come back to a phrase from a while ago.
NoRepeat_Ok:
    ld a, [wGenCount]
    cp OUT_MAX                      ; the history buffer is the whole record
    jr c, :+
    ld a, OUT_MAX
:   cp NOREPEAT_N
    jr c, .fine                     ; nothing four long has been said yet
    ld b, a                         ; b = tokens on record

    sub NOREPEAT_N - 1              ; de -> the trailing three
    ld l, a
    ld h, 0
    add hl, hl
    ld de, wOutTokens
    add hl, de
    ld d, h
    ld e, l

    ld a, b
    sub NOREPEAT_N - 1              ; start positions to try
    ld c, a
    ld hl, wOutTokens
.at
    push hl
    push de
    push bc
    ld b, NOREPEAT_N - 1
.three
    ld a, [de]
    cp [hl]
    jr nz, .miss
    inc de
    inc hl
    ld a, [de]
    cp [hl]
    jr nz, .miss
    inc de
    inc hl
    dec b
    jr nz, .three

    ld a, [wBestTok + 0]            ; three matched; hl -> the token that followed
    cp [hl]
    jr nz, .miss
    inc hl
    ld a, [wBestTok + 1]
    cp [hl]
    jr nz, .miss
    pop bc
    pop de
    pop hl
    xor a                           ; Z: this would repeat
    ret
.miss
    pop bc
    pop de
    pop hl
    inc hl
    inc hl
    dec c
    jr nz, .at
.fine
    or 1                            ; NZ: safe
    ret

; wX = requantized embedding row for wToken. The table is 32 KB, so it spans two
; banks of 256 tokens each.
EmbedToken:
    ; A part holds 2^EMB_ROW_BITS rows (the exporter sizes it to the bank):
    ; the part is the token shifted right by that many bits, the row the
    ; remainder. 64 wide: 256 rows, the high byte and the low byte. 96 wide:
    ; 128 rows, so bit 7 of the low byte joins the part.
    ld a, [wToken + 1]
    ld c, a                         ; c = high byte
    ld a, [wToken + 0]
    ld e, a                         ; e = low byte
IF EMB_ROW_BITS == 8
    ld a, e                         ; row = low byte, part = high byte
ELIF EMB_ROW_BITS == 7
    sla c                           ; part = high byte * 2 + bit 7 of the low
    bit 7, e
    jr z, :+
    inc c
:   ld a, e
    and $7F                         ; row = low 7 bits
ELSE
    FAIL "EmbedToken: EMB_ROW_BITS must be 7 or 8"
ENDC
    ld l, a                         ; hl = row
    ld h, 0
    ld b, 0
    push hl
    ld hl, emb_banks
    add hl, bc
    ld a, [hl]
    ld [rROMB0], a
    ld hl, emb_addrs
    add hl, bc
    add hl, bc                      ; word entries
    ld a, [hl+]
    ld e, a
    ld a, [hl]
    ld d, a                         ; de = the part's base
    pop hl
IF DIM == 64
REPT 6
    add hl, hl                      ; row * 64
ENDR
ELIF DIM == 96
REPT 5
    add hl, hl                      ; row * 32
ENDR
    ld b, h
    ld c, l
    add hl, hl                      ; row * 64
    add hl, bc                      ; row * 96
ELIF DIM == 128
REPT 7
    add hl, hl                      ; row * 128
ENDR
ELSE
    FAIL "EmbedToken: no row multiply for this DIM"
ENDC
    add hl, de

    ld de, wX
    ld bc, DIM
    push hl
    call CopyBytes
    pop hl

    ; One shift for every token: the embedding has a single exponent, so the
    ; 512-byte per-token table the exporter used to write was 512 copies of
    ; this constant. ROM0 needed the room.
    ld a, EMB_SHIFT
    ld [wRnShift], a

    ld hl, wX                       ; rescale in place
    ld b, DIM
.scale
    ld a, [hl]
    push hl
    push bc                         ; Requant_Shift and Requant_Sat8 both use b
    ldh [wTmp32 + 0], a
    add a, a
    sbc a, a
    ldh [wTmp32 + 1], a
    ldh [wTmp32 + 2], a
    ldh [wTmp32 + 3], a
    ld a, [wRnShift]
    call Requant_Shift
    call Requant_Sat8
    pop bc
    pop hl
    ld [hl+], a
    dec b
    jp nz, .scale
    ret
