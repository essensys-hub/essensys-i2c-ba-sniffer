#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bdm.h"

/* Independent scripted wire peer: each receive packet and expected request is
 * supplied by the test vectors, not calculated using the production encoder. */
typedef struct {
    uint64_t now, high_at, low_at;
    uint32_t rx[1024], tx[1024], accumulator;
    unsigned count, bits, sent, enables, releases, bkpt_assertions;
    unsigned cancel_bit, voltage_bit, reset_bit, interlock_bit, io_bit;
    bool clock, data, enabled, halt, never_halt, keep_halted, cancelled, bad_timer;
    bool initial_voltage_bad, initial_reset_bad, initial_interlock_bad;
    bool enable_fails;
} peer;

static bool enable(void *u) {
    peer *p = u; p->enables++; p->enabled = true;
    p->clock = p->data = false; p->low_at = p->now;
    return !p->enable_fails;
}
static void release(void *u) { peer *p = u; p->releases++; p->enabled = false; p->clock = false; }
static bool clk(void *u, bool high) {
    peer *p = u; assert(p->enabled);
    if (p->io_bit && p->bits >= p->io_bit) return false;
    if (high) {
        assert(!p->clock); assert(p->now - p->low_at >= 5);
        p->high_at = p->now;
        p->accumulator = (p->accumulator << 1) | p->data;
    } else if (p->clock) p->low_at = p->now;
    p->clock = high; return true;
}
static bool data(void *u, bool high) { peer *p = u; assert(!p->clock); p->data = high; return true; }
static bool sample(void *u, bool *high) {
    peer *p = u; assert(p->clock); assert(p->now - p->high_at >= 5);
    unsigned frame = p->bits / 17, bit = p->bits % 17;
    assert(frame < p->count);
    *high = ((p->rx[frame] >> (16 - bit)) & 1) != 0;
    ++p->bits;
    if (bit == 16) {
        assert(p->accumulator <= 0xffff); /* reserved TX bit is always zero */
        p->tx[p->sent++] = p->accumulator;
        if (p->accumulator == 0x0c00 && !p->keep_halted) p->halt = false;
        p->accumulator = 0;
    }
    return true;
}
static bool bkpt(void *u, bool asserted) {
    peer *p = u;
    if (asserted) { ++p->bkpt_assertions; if (!p->never_halt) p->halt = true; }
    return true;
}
static bool target(void *u, bdm_target_status *s) {
    peer *p = u;
    s->millivolts = p->initial_voltage_bad || (p->voltage_bit && p->bits >= p->voltage_bit) ? 2999 : 3300;
    s->reset_released = !(p->initial_reset_bad || (p->reset_bit && p->bits >= p->reset_bit));
    s->port_exclusive = !(p->initial_interlock_bad || (p->interlock_bit && p->bits >= p->interlock_bit));
    s->allpst = p->halt;
    return true;
}
static bool cancelled(void *u) { peer *p = u; return p->cancelled || (p->cancel_bit && p->bits >= p->cancel_bit); }
static uint64_t now(void *u) { return ((peer *)u)->now; }
static void delay(void *u, uint32_t us) { peer *p = u; if (!p->bad_timer) p->now += us; }
static bdm_io io(peer *p) {
    return (bdm_io){p, enable, release, clk, data, sample, bkpt, target, cancelled, now, delay};
}
static bdm_config cfg(void) {
    return (bdm_config){true, true, true, 1000000, 5, 100000, 4};
}
static void add(peer *p, uint32_t packet) { assert(p->count < 1024); p->rx[p->count++] = packet; }
static void setup(bdm *s, peer *p) {
    memset(p, 0, sizeof(*p)); bdm_io i = io(p); bdm_config c = cfg();
    assert(bdm_init(s, &i, &c) == BDM_OK); assert(bdm_open(s) == BDM_OK);
    assert(p->bits == 0 && p->enables == 1 && !s->may_be_halted);
}
static void halted(bdm *s, peer *p) {
    add(p, 0x10000); add(p, 0x0ffff); assert(bdm_halt(s) == BDM_OK);
    assert(s->synchronized && s->may_be_halted && p->sent == 2);
}
static void identified(bdm *s, peer *p) {
    halted(s, p); add(p, 0xffff); add(p, 0x0190); add(p, 0x0000);
    uint32_t csr = 0; assert(bdm_read_csr(s, &csr) == BDM_OK);
    assert(csr == 0x01900000 && s->revision_checked);
}
static void expected(peer *p, const uint32_t *words, size_t n) {
    assert(p->sent == n);
    for (size_t k = 0; k < n; ++k) assert(p->tx[k] == words[k]);
}
static void released(bdm *s, peer *p, bdm_result r) {
    assert(s->last_result == r); assert(!s->open && !p->enabled);
    assert(p->releases == 1); assert(!s->config.fresh_link_reset_confirmed);
    assert(bdm_open(s) == BDM_UNQUALIFIED); assert(p->enables == 1);
}
static void read_setup(peer *p) { add(p, 0xffff); add(p, 0x10000); add(p, 0x10000); }

static void test_qualification(void) {
    for (unsigned flag = 0; flag < 3; ++flag) {
        peer p = {0}; bdm s; bdm_io i = io(&p); bdm_config c = cfg();
        if (flag == 0) c.electrical_qualified = false;
        if (flag == 1) c.jc1_bdm_verified = false;
        if (flag == 2) c.fresh_link_reset_confirmed = false;
        assert(bdm_init(&s, &i, &c) == BDM_OK);
        assert(bdm_open(&s) == BDM_UNQUALIFIED);
        assert(p.enables == 0 && p.bits == 0 && p.bkpt_assertions == 0);
    }
}
static void test_read_long_busy(void) {
    peer p; bdm s; setup(&s, &p); identified(&s, &p); read_setup(&p);
    add(&p, 0x10000); add(&p, 0x10000); add(&p, 0xabcd); add(&p, 0xffff);
    uint8_t out[4] = {0}; assert(bdm_read_flash(&s, 0x12340, out, sizeof(out)) == BDM_OK);
    assert(memcmp(out, (uint8_t[]){0xab, 0xcd, 0xff, 0xff}, 4) == 0);
    expected(&p, (uint32_t[]){0,0,0x2d80,0,0,0x1980,1,0x2340,0,0,0,0}, 12);
    assert(p.now >= 12 * (170 + 32)); /* conservative low/high/interframe timing */
    bdm_close(&s); assert(p.releases == 1 && s.may_be_halted);
}
static void test_alignment_tail(void) {
    peer p; bdm s; setup(&s, &p); identified(&s, &p);
    read_setup(&p); add(&p, 0xabcd); /* upper byte undefined; lower is data */
    read_setup(&p); add(&p, 0xffff);
    uint8_t out[3] = {0}; assert(bdm_read_flash(&s, 0x7fffd, out, 3) == BDM_OK);
    assert(memcmp(out, (uint8_t[]){0xcd,0xff,0xff}, 3) == 0);
    expected(&p, (uint32_t[]){0,0,0x2d80,0,0,0x1900,7,0xfffd,0,0x1940,7,0xfffe,0}, 13);
}
static void test_read_bounds(void) {
    peer p; bdm s; setup(&s, &p); identified(&s, &p); uint8_t out[257];
    assert(bdm_read_flash(&s, 0x80000, out, 1) == BDM_INVALID_ARGUMENT);
    assert(bdm_read_flash(&s, 0x7ffff, out, 2) == BDM_INVALID_ARGUMENT);
    assert(bdm_read_flash(&s, UINT32_MAX, out, 1) == BDM_INVALID_ARGUMENT);
    assert(bdm_read_flash(&s, 0, out, 257) == BDM_INVALID_ARGUMENT);
    assert(bdm_read_flash(&s, 0, out, 0) == BDM_INVALID_ARGUMENT);
    assert(bdm_read_flash(&s, 0, NULL, 1) == BDM_INVALID_ARGUMENT);
    assert(p.sent == 5 && p.releases == 1 && !s.open);
}
static void test_response_error(uint32_t packet, bdm_result result, bool second_word) {
    peer p; bdm s; setup(&s, &p); identified(&s, &p); read_setup(&p);
    if (second_word) add(&p, 0x1234);
    add(&p, packet);
    uint8_t out[4] = {0xa5,0xa5,0xa5,0xa5};
    assert(bdm_read_flash(&s, 0x3000, out, 4) == result);
    assert(memcmp(out, (uint8_t[]){0xa5,0xa5,0xa5,0xa5}, 4) == 0);
    released(&s, &p, result);
}
static void test_busy_timeout(void) {
    peer p; bdm s; setup(&s, &p); identified(&s, &p); read_setup(&p);
    for (unsigned i = 0; i < 4; ++i) add(&p, 0x10000);
    uint8_t out = 0x5a; assert(bdm_read_flash(&s, 0, &out, 1) == BDM_TIMEOUT);
    assert(out == 0x5a && p.sent == 12); released(&s, &p, BDM_TIMEOUT);
}
static void test_midframe(unsigned which, bdm_result result) {
    peer p; bdm s; setup(&s, &p); identified(&s, &p); add(&p, 0xffff);
    unsigned fail_bit = p.bits + 8;
    if (which == 0) p.cancel_bit = fail_bit;
    if (which == 1) p.voltage_bit = fail_bit;
    if (which == 2) p.reset_bit = fail_bit;
    if (which == 3) p.interlock_bit = fail_bit;
    if (which == 4) p.io_bit = fail_bit;
    uint8_t out = 0xa5; assert(bdm_read_flash(&s, 0, &out, 1) == result);
    assert(p.bits == fail_bit && p.sent == 5 && out == 0xa5);
    released(&s, &p, result);
}
static void test_initial_guard(unsigned which, bdm_result result) {
    peer p = {0}; bdm s; bdm_io i = io(&p); bdm_config c = cfg();
    if (which == 0) p.initial_voltage_bad = true;
    if (which == 1) p.initial_reset_bad = true;
    if (which == 2) p.initial_interlock_bad = true;
    if (which == 3) p.cancelled = true;
    assert(bdm_init(&s, &i, &c) == BDM_OK);
    assert(bdm_open(&s) == result); assert(p.enables == 0 && p.bits == 0);
}
static void test_halt_timeout(void) {
    peer p; bdm s; setup(&s, &p); p.never_halt = true;
    assert(bdm_halt(&s) == BDM_TIMEOUT); assert(p.sent == 0 && s.may_be_halted);
    released(&s, &p, BDM_TIMEOUT);
}
static void test_resume(bool remains_halted) {
    peer p; bdm s; setup(&s, &p); identified(&s, &p);
    p.keep_halted = remains_halted; add(&p, 0xffff); add(&p, 0xffff);
    assert(bdm_resume(&s) == (remains_halted ? BDM_TIMEOUT : BDM_OK));
    expected(&p, (uint32_t[]){0,0,0x2d80,0,0,0xc00,0}, 7);
    assert(!s.open && !p.enabled && p.releases == 1);
    assert(s.may_be_halted == remains_halted);
}
static void test_debug_revision(void) {
    peer p; bdm s; setup(&s, &p); halted(&s, &p);
    add(&p, 0xffff); add(&p, 0x0010); add(&p, 0);
    uint32_t csr = 0;
    assert(bdm_read_csr(&s, &csr) == BDM_UNSUPPORTED_REVISION);
    assert(csr == 0x00100000); released(&s, &p, BDM_UNSUPPORTED_REVISION);
}
static void test_preconditions(void) {
    peer p; bdm s; setup(&s, &p); uint8_t out = 0;
    assert(bdm_read_flash(&s, 0, &out, 1) == BDM_NOT_HALTED);
    assert(p.sent == 0); released(&s, &p, BDM_NOT_HALTED);
    setup(&s, &p); halted(&s, &p);
    assert(bdm_read_flash(&s, 0, &out, 1) == BDM_UNQUALIFIED);
    assert(p.sent == 2); released(&s, &p, BDM_UNQUALIFIED);
}
static void test_config(void) {
    peer p = {0}; bdm s; bdm_io i = io(&p); bdm_config c = cfg();
    c.half_period_us = 4; assert(bdm_init(&s, &i, &c) == BDM_INVALID_ARGUMENT);
    c = cfg(); c.pstclk_min_hz = 0; assert(bdm_init(&s, &i, &c) == BDM_INVALID_ARGUMENT);
    c = cfg(); c.operation_timeout_us = 1000001; assert(bdm_init(&s, &i, &c) == BDM_INVALID_ARGUMENT);
    c = cfg(); c.max_poll_frames = 4097; assert(bdm_init(&s, &i, &c) == BDM_INVALID_ARGUMENT);
    c = cfg(); i.release = NULL; assert(bdm_init(&s, &i, &c) == BDM_INVALID_ARGUMENT);
    assert(p.enables == 0);
}
static void test_wall_timeout(void) {
    peer p; bdm s; setup(&s, &p); identified(&s, &p);
    s.config.operation_timeout_us = 10; add(&p, 0xffff);
    uint8_t out = 0; assert(bdm_read_flash(&s, 0, &out, 1) == BDM_TIMEOUT);
    assert(p.sent == 5); released(&s, &p, BDM_TIMEOUT);
}
static void test_enable_error(void) {
    peer p = {0}; bdm s; bdm_io i = io(&p); bdm_config c = cfg(); p.enable_fails = true;
    assert(bdm_init(&s, &i, &c) == BDM_OK);
    assert(bdm_open(&s) == BDM_IO_ERROR); assert(p.bits == 0); released(&s, &p, BDM_IO_ERROR);
}
static void test_invalid_active(unsigned mode) {
    peer p; bdm s; setup(&s, &p); identified(&s, &p);
    bdm_result r = mode == 0 ? bdm_open(&s) : bdm_read_csr(&s, NULL);
    assert(r == BDM_INVALID_ARGUMENT && p.sent == 5);
    released(&s, &p, BDM_INVALID_ARGUMENT);
}
int main(int argc, char **argv) {
    assert(argc == 2); int test = atoi(argv[1]);
    switch (test) {
        case 0: test_qualification(); break;
        case 1: test_read_long_busy(); break;
        case 2: test_alignment_tail(); break;
        case 3: test_read_bounds(); break;
        case 4: test_response_error(0x10001, BDM_BUS_ERROR, false); break;
        case 5: test_response_error(0x1ffff, BDM_ILLEGAL_COMMAND, false); break;
        case 6: test_response_error(0x10002, BDM_PROTOCOL_ERROR, false); break;
        case 7: test_response_error(0x10001, BDM_BUS_ERROR, true); break;
        case 8: test_busy_timeout(); break;
        case 9: test_midframe(0, BDM_CANCELLED); break;
        case 10: test_midframe(1, BDM_TARGET_VOLTAGE); break;
        case 11: test_midframe(2, BDM_TARGET_RESET); break;
        case 12: test_midframe(3, BDM_INTERLOCK); break;
        case 13: test_midframe(4, BDM_IO_ERROR); break;
        case 14: test_initial_guard(0, BDM_TARGET_VOLTAGE); break;
        case 15: test_initial_guard(1, BDM_TARGET_RESET); break;
        case 16: test_initial_guard(2, BDM_INTERLOCK); break;
        case 17: test_initial_guard(3, BDM_CANCELLED); break;
        case 18: test_halt_timeout(); break;
        case 19: test_resume(false); break;
        case 20: test_resume(true); break;
        case 21: test_debug_revision(); break;
        case 22: test_preconditions(); break;
        case 23: test_config(); break;
        case 24: test_wall_timeout(); break;
        case 25: test_enable_error(); break;
        case 26: test_invalid_active(0); break;
        case 27: test_invalid_active(1); break;
        default: assert(false);
    }
    printf("bdm case %d ok\n", test); return 0;
}
