; Stage census: cycle counters around each stage of the forward pass.
;
; Compiled in only when CENSUS is defined (build.ps1 -Census), so the shipping
; ROM and the test lab are byte-for-byte untouched. In a census build the
; per-token profiler that wraps Forward is clobbered - each stage restarts the
; timer - so the token total comes from the stage sum and the known figure,
; not from wTokCycles. Stubbing measures a stage by removing it, which moves
; every data-dependent cost after it; this measures each stage in place.
IF !DEF(CENSUS_INC)
DEF CENSUS_INC EQU 1

DEF CENSUS_STAGES EQU 21

MACRO CENSUS_START
IF DEF(CENSUS)
    call Prof_Start
ENDC
ENDM

MACRO CENSUS_END                    ; \1 = stage index
IF DEF(CENSUS)
    call Prof_Stop
    ld de, wStage + \1 * 4
    call Census_Accum
ENDC
ENDM

ENDC
