#ifndef ESSENSYS_BDM_H
#define ESSENSYS_BDM_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* MCF52259 RM rev.4 ch.33. This interface exposes no memory/register writes,
 * reset, erase, flash security recovery, or arbitrary command pass-through. */
#define BDM_INTERNAL_FLASH_BYTES UINT32_C(0x80000)
#define BDM_MAX_READ_BYTES 256u

typedef enum {
    BDM_OK = 0,
    BDM_INVALID_ARGUMENT,
    BDM_UNQUALIFIED,
    BDM_NOT_OPEN,
    BDM_NOT_HALTED,
    BDM_TARGET_VOLTAGE,
    BDM_TARGET_RESET,
    BDM_INTERLOCK,
    BDM_CANCELLED,
    BDM_TIMEOUT,
    BDM_IO_ERROR,
    BDM_BUS_ERROR,
    BDM_ILLEGAL_COMMAND,
    BDM_PROTOCOL_ERROR,
    BDM_UNSUPPORTED_REVISION
} bdm_result;

typedef struct {
    uint32_t millivolts;
    bool reset_released;
    bool allpst; /* J33.5: high means CPU halted, not the sticky CSR HALT bit. */
    bool port_exclusive; /* Qualified adapter: BA disabled and VPP off. */
} bdm_target_status;

typedef struct {
    void *user;
    bool (*enable)(void *user); /* preload DSCLK/DSI low; BKPT released; then OE */
    void (*release)(void *user); /* OE off first; release BKPT; no GO or RESET */
    bool (*dsclk)(void *user, bool high);
    bool (*dsi)(void *user, bool high);
    bool (*dso)(void *user, bool *high);
    bool (*bkpt)(void *user, bool asserted); /* open-drain assertion only */
    bool (*target)(void *user, bdm_target_status *status);
    bool (*cancelled)(void *user); /* USB lost, explicit cancel, watchdog veto */
    uint64_t (*time_us)(void *user); /* monotonic, must continue during delay */
    void (*delay_us)(void *user, uint32_t us);
} bdm_io;

typedef struct {
    /* All false by default. Set only after board/interface and bench review. */
    bool electrical_qualified;
    bool jc1_bdm_verified;
    bool fresh_link_reset_confirmed; /* 17-bit frame alignment from target reset */
    uint32_t pstclk_min_hz; /* guaranteed live lower bound, not nominal CPU MHz */
    uint32_t half_period_us; /* each low/high phase >= 5 minimum-clock cycles */
    uint32_t operation_timeout_us; /* 1..1,000,000; each public operation bounded */
    uint32_t max_poll_frames; /* 1..4096; independent bound if host timer fails */
} bdm_config;

typedef struct {
    bdm_io io;
    bdm_config config;
    uint64_t started_us;
    uint32_t interframe_us;
    bool initialized;
    bool open;
    bool synchronized;
    bool require_halted;
    bool may_be_halted; /* retained after close/fault; never imply automatic resume */
    bool revision_checked;
    bdm_result last_result;
} bdm;

bdm_result bdm_init(bdm *session, const bdm_io *io, const bdm_config *config);
bdm_result bdm_open(bdm *session); /* enables adapter only; no reset/halt/clocks */
bdm_result bdm_halt(bdm *session); /* intrusive explicit operation, BKPT + ALLPST */
/* Read clears CSR status latches (RM 33.3.2). HRL=9 identifies B+ debug module,
 * not a unique MCF52259 identity. No memory reads until this revision check. */
bdm_result bdm_read_csr(bdm *session, uint32_t *csr);
/* Absolute flash only, 0..0x7ffff, <=256 bytes. Output remains unchanged on
 * failure. The caller must serialize chunks and verify the completed backup. */
bdm_result bdm_read_flash(bdm *session, uint32_t address, uint8_t *out, size_t length);
bdm_result bdm_resume(bdm *session); /* explicit GO; verifies ALLPST deasserts */
void bdm_close(bdm *session); /* electrical release only; target may remain halted */
const char *bdm_result_string(bdm_result result);

#endif
