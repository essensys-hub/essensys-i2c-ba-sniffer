#include "bdm.h"

#include <string.h>

#define BDM_NOP UINT16_C(0x0000)
#define BDM_READ_BYTE UINT16_C(0x1900)
#define BDM_READ_WORD UINT16_C(0x1940)
#define BDM_READ_LONG UINT16_C(0x1980)
#define BDM_READ_CSR UINT16_C(0x2d80)
#define BDM_GO UINT16_C(0x0c00)
#define BDM_STATUS_OK UINT32_C(0x0ffff)
#define BDM_NOT_READY UINT32_C(0x10000)
#define BDM_ERROR_BUS UINT32_C(0x10001)
#define BDM_ERROR_ILLEGAL UINT32_C(0x1ffff)

static bdm_result fail(bdm *s, bdm_result result) {
    if (s->open) s->io.release(s->io.user);
    s->open = false;
    s->synchronized = false;
    s->revision_checked = false;
    s->require_halted = false;
    s->config.fresh_link_reset_confirmed = false;
    s->last_result = result;
    return result;
}

static bdm_result invalid(bdm *s) {
    return s != NULL && s->initialized ? fail(s, BDM_INVALID_ARGUMENT) : BDM_INVALID_ARGUMENT;
}

static bdm_result guard(bdm *s, bdm_target_status *observed) {
    bdm_target_status st;
    if (s->io.cancelled(s->io.user)) return fail(s, BDM_CANCELLED);
    uint64_t now = s->io.time_us(s->io.user);
    if (now < s->started_us) return fail(s, BDM_IO_ERROR);
    if (now - s->started_us >= s->config.operation_timeout_us)
        return fail(s, BDM_TIMEOUT);
    if (!s->io.target(s->io.user, &st)) return fail(s, BDM_IO_ERROR);
    if (!st.port_exclusive) return fail(s, BDM_INTERLOCK);
    if (!st.reset_released) return fail(s, BDM_TARGET_RESET);
    if (st.millivolts < 3000 || st.millivolts > 3600)
        return fail(s, BDM_TARGET_VOLTAGE);
    if (s->require_halted && !st.allpst) return fail(s, BDM_NOT_HALTED);
    if (st.allpst) s->may_be_halted = true;
    if (observed != NULL) *observed = st;
    return BDM_OK;
}

static bdm_result begin(bdm *s, bool halted) {
    if (s == NULL || !s->initialized) return BDM_INVALID_ARGUMENT;
    if (!s->open) return s->last_result = BDM_NOT_OPEN;
    s->started_us = s->io.time_us(s->io.user);
    s->require_halted = halted;
    return guard(s, NULL);
}

/* No frame pass-through is public: only reviewed opcodes are emitted. DSO is
 * sampled after the delayed high phase, not at the asynchronous DSCLK edge.
 * Each phase allows >=5 guaranteed PSTCLK periods (RM fig.33-12). */
static bdm_result exchange(bdm *s, uint16_t tx, uint32_t *rx) {
    uint32_t value = 0;
    bdm_result r;
    for (int bit = 16; bit >= 0; --bit) {
        if ((r = guard(s, NULL)) != BDM_OK) return r;
        if (!s->io.dsclk(s->io.user, false) ||
            !s->io.dsi(s->io.user, bit != 16 && ((tx >> bit) & 1u) != 0))
            return fail(s, BDM_IO_ERROR);
        s->io.delay_us(s->io.user, s->config.half_period_us);
        if ((r = guard(s, NULL)) != BDM_OK) return r;
        if (!s->io.dsclk(s->io.user, true)) return fail(s, BDM_IO_ERROR);
        s->io.delay_us(s->io.user, s->config.half_period_us);
        if ((r = guard(s, NULL)) != BDM_OK) return r;
        bool bit_value;
        if (!s->io.dso(s->io.user, &bit_value)) return fail(s, BDM_IO_ERROR);
        value = (value << 1) | (bit_value ? 1u : 0u);
    }
    if (!s->io.dsclk(s->io.user, false) || !s->io.dsi(s->io.user, false))
        return fail(s, BDM_IO_ERROR);
    /* Not-ready outside memory cycles requires >=32 processor clocks before
     * another serial transfer (RM 33.4.1.2). Use conservative minimum PSTCLK. */
    s->io.delay_us(s->io.user, s->interframe_us);
    if ((r = guard(s, NULL)) != BDM_OK) return r;
    *rx = value;
    return BDM_OK;
}

static bdm_result status(bdm *s, uint32_t value) {
    if (value <= UINT16_MAX) return BDM_OK;
    if (value == BDM_ERROR_BUS) return fail(s, BDM_BUS_ERROR);
    if (value == BDM_ERROR_ILLEGAL) return fail(s, BDM_ILLEGAL_COMMAND);
    return fail(s, BDM_PROTOCOL_ERROR);
}

static bdm_result command(bdm *s, uint16_t cmd) {
    uint32_t rx;
    bdm_result r = exchange(s, cmd, &rx);
    if (r != BDM_OK) return r;
    /* Every completed public command leaves a NOP queued. Its completion is
     * returned concurrently with this opcode; unknown previous state is fatal. */
    if (rx == BDM_STATUS_OK) return BDM_OK;
    if ((r = status(s, rx)) != BDM_OK) return r;
    return fail(s, BDM_PROTOCOL_ERROR);
}

static bdm_result extension(bdm *s, uint16_t word) {
    uint32_t rx;
    bdm_result r = exchange(s, word, &rx);
    if (r != BDM_OK) return r;
    if (rx == BDM_NOT_READY) return BDM_OK;
    if ((r = status(s, rx)) != BDM_OK) return r;
    return fail(s, BDM_PROTOCOL_ERROR);
}

static bdm_result data_word(bdm *s, uint16_t *word) {
    for (uint32_t poll = 0; poll < s->config.max_poll_frames; ++poll) {
        uint32_t rx;
        bdm_result r = exchange(s, BDM_NOP, &rx);
        if (r != BDM_OK) return r;
        if (rx == BDM_NOT_READY) continue;
        if ((r = status(s, rx)) != BDM_OK) return r;
        /* 0xffff with S=0 is legitimate memory/CSR data, not an end marker. */
        *word = (uint16_t)rx;
        return BDM_OK;
    }
    return fail(s, BDM_TIMEOUT);
}

bdm_result bdm_init(bdm *s, const bdm_io *io, const bdm_config *cfg) {
    if (s == NULL) return BDM_INVALID_ARGUMENT;
    memset(s, 0, sizeof(*s));
    s->last_result = BDM_INVALID_ARGUMENT;
    if (io == NULL || cfg == NULL || io->enable == NULL || io->release == NULL ||
        io->dsclk == NULL || io->dsi == NULL || io->dso == NULL || io->bkpt == NULL ||
        io->target == NULL || io->cancelled == NULL || io->time_us == NULL ||
        io->delay_us == NULL || cfg->pstclk_min_hz == 0 || cfg->half_period_us == 0 ||
        cfg->half_period_us > 1000 || cfg->operation_timeout_us == 0 ||
        cfg->operation_timeout_us > 1000000 || cfg->max_poll_frames == 0 ||
        cfg->max_poll_frames > 4096) return BDM_INVALID_ARGUMENT;
    /* Overflow-free rounded-up periods; require conservative 5 cycles/phase. */
    uint64_t required = (UINT64_C(5000000) + cfg->pstclk_min_hz - 1) / cfg->pstclk_min_hz;
    if (cfg->half_period_us < required) return BDM_INVALID_ARGUMENT;
    s->io = *io;
    s->config = *cfg;
    s->interframe_us = (uint32_t)((UINT64_C(32000000) + cfg->pstclk_min_hz - 1) /
                                 cfg->pstclk_min_hz);
    s->initialized = true;
    return s->last_result = BDM_OK;
}

bdm_result bdm_open(bdm *s) {
    if (s == NULL || !s->initialized) return BDM_INVALID_ARGUMENT;
    if (s->open) return fail(s, BDM_INVALID_ARGUMENT);
    if (!s->config.electrical_qualified || !s->config.jc1_bdm_verified ||
        !s->config.fresh_link_reset_confirmed) return s->last_result = BDM_UNQUALIFIED;
    s->started_us = s->io.time_us(s->io.user);
    s->require_halted = false;
    bdm_result r = guard(s, NULL);
    if (r != BDM_OK) return r;
    /* Set open before enabling so failed enable always takes the release path. */
    s->open = true;
    if (!s->io.enable(s->io.user)) return fail(s, BDM_IO_ERROR);
    return s->last_result = guard(s, NULL);
}

bdm_result bdm_halt(bdm *s) {
    bdm_result r = begin(s, false);
    if (r != BDM_OK) return r;
    s->may_be_halted = true; /* even a failed/late BKPT may have stopped CPU */
    if (!s->io.bkpt(s->io.user, true)) return fail(s, BDM_IO_ERROR);
    bool halted = false;
    /* Bound both wall-time and iterations; no wait can become an infinite loop. */
    for (uint32_t i = 0; i < s->config.max_poll_frames; ++i) {
        bdm_target_status st;
        if ((r = guard(s, &st)) != BDM_OK) return r;
        if (st.allpst) { halted = true; break; }
        s->io.delay_us(s->io.user, s->interframe_us);
    }
    if (!halted) return fail(s, BDM_TIMEOUT);
    s->require_halted = true;
    if (!s->synchronized) {
        uint32_t ignored, response;
        /* Fresh-reset frame boundary is a required external qualification, not
         * something two NOPs can discover or repair from a partial transfer. */
        if ((r = exchange(s, BDM_NOP, &ignored)) != BDM_OK) return r;
        if ((r = exchange(s, BDM_NOP, &response)) != BDM_OK) return r;
        if (response != BDM_STATUS_OK) {
            if ((r = status(s, response)) != BDM_OK) return r;
            return fail(s, BDM_PROTOCOL_ERROR);
        }
        s->synchronized = true;
    }
    return s->last_result = BDM_OK;
}

bdm_result bdm_read_csr(bdm *s, uint32_t *csr) {
    if (csr == NULL) return invalid(s);
    bdm_result r = begin(s, true);
    if (r != BDM_OK) return r;
    if (!s->synchronized) return fail(s, BDM_NOT_HALTED);
    uint16_t high, low;
    if ((r = command(s, BDM_READ_CSR)) != BDM_OK ||
        (r = data_word(s, &high)) != BDM_OK ||
        (r = data_word(s, &low)) != BDM_OK) return r;
    uint32_t value = ((uint32_t)high << 16) | low;
    *csr = value; /* Diagnostic value is useful even for incompatible HRL. */
    if (((value >> 20) & 15u) != 9u) return fail(s, BDM_UNSUPPORTED_REVISION);
    s->revision_checked = true;
    return s->last_result = BDM_OK;
}

bdm_result bdm_read_flash(bdm *s, uint32_t address, uint8_t *out, size_t length) {
    if (out == NULL || length == 0 || length > BDM_MAX_READ_BYTES ||
        address >= BDM_INTERNAL_FLASH_BYTES || length > BDM_INTERNAL_FLASH_BYTES - address)
        return invalid(s);
    bdm_result r = begin(s, true);
    if (r != BDM_OK) return r;
    if (!s->synchronized) return fail(s, BDM_NOT_HALTED);
    if (!s->revision_checked) return fail(s, BDM_UNQUALIFIED);
    uint8_t staged[BDM_MAX_READ_BYTES];
    size_t done = 0;
    while (done < length) {
        uint32_t at = address + (uint32_t)done;
        size_t left = length - done;
        unsigned n = ((at & 3u) == 0 && left >= 4) ? 4 :
                     ((at & 1u) == 0 && left >= 2) ? 2 : 1;
        uint16_t opcode = n == 4 ? BDM_READ_LONG : n == 2 ? BDM_READ_WORD : BDM_READ_BYTE;
        uint16_t high, low;
        if ((r = command(s, opcode)) != BDM_OK ||
            (r = extension(s, (uint16_t)(at >> 16))) != BDM_OK ||
            (r = extension(s, (uint16_t)at)) != BDM_OK ||
            (r = data_word(s, &high)) != BDM_OK) return r;
        if (n == 4) {
            if ((r = data_word(s, &low)) != BDM_OK) return r;
            staged[done] = (uint8_t)(high >> 8);
            staged[done + 1] = (uint8_t)high;
            staged[done + 2] = (uint8_t)(low >> 8);
            staged[done + 3] = (uint8_t)low;
        } else if (n == 2) {
            staged[done] = (uint8_t)(high >> 8);
            staged[done + 1] = (uint8_t)high;
        } else {
            staged[done] = (uint8_t)high;
        }
        done += n;
    }
    memcpy(out, staged, length);
    return s->last_result = BDM_OK;
}

bdm_result bdm_resume(bdm *s) {
    bdm_result r = begin(s, true);
    if (r != BDM_OK) return r;
    if (!s->synchronized) return fail(s, BDM_NOT_HALTED);
    if (!s->io.bkpt(s->io.user, false)) return fail(s, BDM_IO_ERROR);
    /* GO resumes a program: only an explicit caller request can reach here. */
    s->require_halted = false;
    if ((r = command(s, BDM_GO)) != BDM_OK) return r;
    uint16_t response;
    if ((r = data_word(s, &response)) != BDM_OK) return r;
    if (response != UINT16_MAX) return fail(s, BDM_PROTOCOL_ERROR);
    for (uint32_t i = 0; i < s->config.max_poll_frames; ++i) {
        bdm_target_status st;
        if ((r = guard(s, &st)) != BDM_OK) return r;
        if (!st.allpst) {
            s->may_be_halted = false;
            /* Release adapter immediately; next use requires a fresh session. */
            bdm_close(s);
            return s->last_result = BDM_OK;
        }
        s->io.delay_us(s->io.user, s->interframe_us);
    }
    return fail(s, BDM_TIMEOUT);
}

void bdm_close(bdm *s) {
    if (s == NULL || !s->initialized) return;
    if (s->open) s->io.release(s->io.user);
    s->open = false;
    s->synchronized = false;
    s->revision_checked = false;
    s->require_halted = false;
    /* Reopening a link after fault/close requires externally verified reset. */
    s->config.fresh_link_reset_confirmed = false;
}

const char *bdm_result_string(bdm_result r) {
    switch (r) {
        case BDM_OK: return "ok";
        case BDM_INVALID_ARGUMENT: return "invalid_argument";
        case BDM_UNQUALIFIED: return "unqualified";
        case BDM_NOT_OPEN: return "not_open";
        case BDM_NOT_HALTED: return "not_halted";
        case BDM_TARGET_VOLTAGE: return "target_voltage";
        case BDM_TARGET_RESET: return "target_reset";
        case BDM_INTERLOCK: return "port_interlock";
        case BDM_CANCELLED: return "cancelled";
        case BDM_TIMEOUT: return "timeout";
        case BDM_IO_ERROR: return "io_error";
        case BDM_BUS_ERROR: return "bus_error";
        case BDM_ILLEGAL_COMMAND: return "illegal_command";
        case BDM_PROTOCOL_ERROR: return "protocol_error";
        case BDM_UNSUPPORTED_REVISION: return "unsupported_debug_revision";
    }
    return "unknown";
}
