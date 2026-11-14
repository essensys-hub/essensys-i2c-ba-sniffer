/* Independent PIC wire model using DS41244F table 3-1 and timing diagrams.
 * Observes actual GPIO edges; production internals/static commands are not used.
 * Hardware analog behaviour is deliberately NOT simulated or qualified here. */
#include "icsp.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct target {
    uint16_t program[8192], config, uid[4], calibration[2], device;
    uint8_t eeprom[256];
    uint16_t pc, shift, latch, read_word;
    unsigned phase, bits, load_kind;
    bool clock_high, vpp_enabled, controls_vdd, vdd_enabled;
    icsp_data_drive drive;
    uint64_t now, changed_at, fallen_at, cancel_at;
    unsigned commands, erases, writes, safe_offs, vpp_edges, max_wait;
    unsigned command_trace[80000], trace_count;
    uint16_t pc_trace[80000], load_trace[10000];
    unsigned load_count;
    int fail_after_clocks;
    bool corrupt_write, corrupt_calibration, corrupt_eeprom;
    bool cancel_erase, bad_rail_erase, dropped_rail, forbidden_write;
    bool port_exclusive, lose_interlock_on_erase;
};
static struct target t;
static uint16_t image_words[8192];
static icsp_session session;

static void defaults(void) {
    memset(&t, 0, sizeof(t));
    for (unsigned i = 0; i < 8192; ++i) t.program[i] = 0x1234;
    for (unsigned i = 0; i < 256; ++i) t.eeprom[i] = (uint8_t)(i ^ 0x5a);
    for (unsigned i = 0; i < 4; ++i) t.uid[i] = (uint16_t)(0x3f00 | (i * 13));
    t.config = 0x3ff2; t.calibration[0] = 0x28f7; t.calibration[1] = 0x3ffc;
    t.device = 0x1463; /* PIC16F946 rev3, literal from table 4-1 */
    t.drive = ICSP_DATA_HIZ; t.controls_vdd = true;
    t.fail_after_clocks = -1; t.port_exclusive = true;
    for (unsigned i = 0; i < 8192; ++i) image_words[i] = 0x3fff;
    image_words[0] = 0x25e6; image_words[8191] = 0x123;
}
static uint16_t read_program(void) {
    if (t.pc < 8192) return (t.config & 0x40) ? t.program[t.pc] : 0;
    if (t.pc < 0x2004) return t.uid[t.pc - 0x2000];
    if (t.pc == 0x2006) return t.device;
    if (t.pc == 0x2007) return t.config;
    if (t.pc == 0x2008 || t.pc == 0x2009) return t.calibration[t.pc - 0x2008];
    assert(0 && "driver attempted reserved read");
    return 0;
}
static void command_received(unsigned value) {
    assert(t.trace_count < 80000);
    t.command_trace[t.trace_count] = value;
    t.pc_trace[t.trace_count++] = t.pc;
    ++t.commands;
    switch (value) {
    case 0x00: t.pc = 0x2000; t.phase = 1; t.load_kind = 0; break;
    case 0x02: t.phase = 1; t.load_kind = 0; break;
    case 0x03: t.phase = 1; t.load_kind = 1; break;
    case 0x04: t.phase = 2; t.read_word = read_program(); break;
    case 0x05: t.phase = 2; t.read_word = (t.config & 0x80) ? t.eeprom[t.pc & 255] : 0; break;
    case 0x06:
        t.pc = (uint16_t)((t.pc & 0x2000) | ((t.pc + 1) & 0x1fff));
        break;
    case 0x08:
        ++t.writes;
        if (!t.corrupt_write) {
            if (t.load_kind == 1) t.eeprom[t.pc & 255] = (uint8_t)t.latch;
            else if (t.pc < 8192) t.program[t.pc] &= t.latch;
            else if (t.pc == 0x2007) t.config &= t.latch;
            else { t.forbidden_write = true; assert(0 && "unexpected config/calibration write"); }
        }
        t.latch = 0x3fff;
        break;
    case 0x09:
        ++t.erases;
        assert(t.pc < 0x2000 && "erase in configuration space would erase user IDs");
        for (unsigned i = 0; i < 8192; ++i) t.program[i] = 0x3fff;
        if (!(t.config & 0x80)) memset(t.eeprom, 255, sizeof(t.eeprom));
        t.config = 0x3fff;
        if (t.corrupt_calibration) t.calibration[0] ^= 1;
        if (t.corrupt_eeprom) t.eeprom[0] ^= 1;
        if (t.cancel_erase) t.cancel_at = t.now + 250;
        if (t.bad_rail_erase) t.dropped_rail = true;
        if (t.lose_interlock_on_erase) t.port_exclusive = false;
        break;
    default: assert(0 && "unknown/forbidden command");
    }
}
static bool clock_cb(void *context, bool high) {
    (void)context;
    if (t.fail_after_clocks == 0) return false;
    if (t.fail_after_clocks > 0) --t.fail_after_clocks;
    if (!high && t.clock_high) {
        if (t.phase != 2) {
            assert(t.drive != ICSP_DATA_HIZ);
            assert(t.now - t.changed_at >= 1); /* setup before target latch */
            if (t.drive == ICSP_DATA_HIGH) t.shift |= (uint16_t)(1u << t.bits);
        }
        ++t.bits;
        if (t.phase == 0 && t.bits == 6) {
            unsigned cmd = t.shift;
            t.bits = 0; t.shift = 0;
            command_received(cmd);
        } else if (t.phase == 1 && t.bits == 16) {
            assert((t.shift & 0x8001) == 0); /* literal start/stop framing */
            assert(t.load_count < 10000);
            t.load_trace[t.load_count++] = t.shift;
            t.latch = (uint16_t)(t.shift >> 1);
            t.phase = 0; t.bits = 0; t.shift = 0;
        } else if (t.phase == 2 && t.bits == 16) {
            assert(t.drive == ICSP_DATA_HIZ);
            t.phase = 0; t.bits = 0; t.shift = 0;
        }
        t.fallen_at = t.now;
    }
    if (high && !t.clock_high && t.commands != 0) assert(t.now - t.fallen_at >= 1);
    t.clock_high = high;
    return true;
}
static bool data_cb(void *ctx, icsp_data_drive drive) {
    (void)ctx;
    assert(!t.clock_high);
    if (drive != t.drive) t.changed_at = t.now;
    t.drive = drive;
    return true;
}
static bool sample_cb(void *ctx, bool *value) {
    (void)ctx;
    assert(t.phase == 2 && t.clock_high && t.drive == ICSP_DATA_HIZ);
    assert(t.bits >= 1 && t.bits <= 14);
    *value = (t.read_word & (1u << (t.bits - 1))) != 0;
    return true;
}
static bool vpp_cb(void *ctx, bool enabled) {
    (void)ctx;
    if (enabled) {
        assert(t.drive == ICSP_DATA_LOW && !t.clock_high);
        ++t.vpp_edges;
    } else { t.pc = 0; t.phase = 0; t.bits = 0; t.shift = 0; t.latch = 0x3fff; }
    t.vpp_enabled = enabled;
    return true;
}
static bool vdd_cb(void *ctx, bool enabled) { (void)ctx; t.vdd_enabled = enabled; return true; }
static bool voltages_cb(void *ctx, uint16_t *vdd, uint16_t *vpp) {
    (void)ctx;
    *vdd = t.vdd_enabled ? (t.dropped_rail ? 3000 : 5000) : 0;
    *vpp = t.vpp_enabled ? 11000 : 0;
    return true;
}
static bool delay_cb(void *ctx, uint32_t us) {
    (void)ctx;
    assert(us > 0 && us <= 100);
    if (us > t.max_wait) t.max_wait = us;
    t.now += us;
    return true;
}
static bool alive_cb(void *ctx) { (void)ctx; return t.port_exclusive && (t.cancel_at == 0 || t.now < t.cancel_at); }
static void off_cb(void *ctx) {
    (void)ctx;
    ++t.safe_offs;
    if (t.controls_vdd) t.vdd_enabled = false;
    t.vpp_enabled = false; t.drive = ICSP_DATA_HIZ; t.clock_high = false;
    t.phase = 0; t.bits = 0; t.shift = 0; t.pc = 0; t.latch = 0x3fff;
}
static icsp_io io(void) {
    icsp_io value = {0};
    value.clock = clock_cb; value.data = data_cb; value.sample_data = sample_cb;
    value.vpp = vpp_cb; value.vdd = vdd_cb; value.voltages_mv = voltages_cb;
    value.delay_us = delay_cb; value.alive = alive_cb; value.safe_off = off_cb;
    return value;
}
static icsp_policy policy(void) {
    icsp_policy value = {0};
    value.board_qualified = true; value.controls_target_vdd = true;
    value.allow_programming = true; value.backup_verified = true;
    return value;
}
static void start(void) {
    icsp_io callbacks = io(); icsp_policy rules = policy();
    assert(icsp_init(&session, &callbacks, &rules) == ICSP_OK);
    assert(icsp_open(&session) == ICSP_OK);
}
static icsp_image image(void) {
    icsp_image value = {0};
    value.program_words = image_words; value.program_count = 8192; value.config = 0x3ff2;
    return value;
}
static void shutdown_assertion(void) {
    assert(!t.vpp_enabled && t.drive == ICSP_DATA_HIZ && !t.clock_high);
    assert(!session.active && !session.identified);
}
static void test_unqualified(void) {
    defaults(); icsp_io callbacks = io(); icsp_policy rules = policy();
    rules.board_qualified = false;
    assert(icsp_init(&session, &callbacks, &rules) == ICSP_OK);
    assert(icsp_open(&session) == ICSP_UNQUALIFIED);
    assert(t.commands == 0 && t.vpp_edges == 0);
    shutdown_assertion();
}
static void test_read_wire(void) {
    defaults(); start();
    assert(session.identity.device_id == 0x1463 && session.identity.config == 0x3ff2);
    assert(session.identity.calibration[0] == 0x28f7);
    assert(t.command_trace[0] == 0x00 && t.load_trace[0] == 0x7ffe);
    /* First access is LOAD_CONFIG/all ones, then read UID0 and increment. */
    const unsigned expected[] = {0x00, 0x04, 0x06, 0x04, 0x06, 0x04, 0x06, 0x04,
                                 0x06, 0x06, 0x06, 0x04, 0x06, 0x04, 0x06, 0x04, 0x06, 0x04};
    for (unsigned i = 0; i < sizeof(expected)/sizeof(expected[0]); ++i)
        assert(t.command_trace[i] == expected[i]);
    uint16_t value;
    assert(icsp_read(&session, 8191, &value) == ICSP_OK && value == 0x1234);
    assert(icsp_read(&session, 0, &value) == ICSP_OK && value == 0x1234);
    assert(icsp_read(&session, 0x210a, &value) == ICSP_OK && value == 0x50);
    assert(icsp_read(&session, 0x2005, &value) == ICSP_INVALID);
    shutdown_assertion();
}
static void test_protection_device_and_policy(void) {
    defaults(); t.device = 0x13a1;
    icsp_io callbacks = io(); icsp_policy rules = policy();
    assert(icsp_init(&session, &callbacks, &rules) == ICSP_OK);
    assert(icsp_open(&session) == ICSP_WRONG_DEVICE); shutdown_assertion();
    defaults(); t.config &= (uint16_t)~0x40; start(); uint16_t value = 123;
    assert(icsp_read(&session, 0, &value) == ICSP_PROTECTED && value == 123);
    assert(t.erases == 0); shutdown_assertion();
    defaults(); t.config &= (uint16_t)~0x80; start();
    assert(!session.identity.eeprom_readable);
    assert(icsp_read(&session, 0x2100, &value) == ICSP_PROTECTED); shutdown_assertion();
    defaults(); start(); icsp_result result; icsp_image img = image();
    session.policy.backup_verified = false;
    assert(icsp_program(&session, &img, &result) == ICSP_POLICY_ERROR && t.erases == 0);
    shutdown_assertion();
    defaults(); start(); img = image(); img.config &= (uint16_t)~0x40;
    assert(icsp_program(&session, &img, &result) == ICSP_PROTECTED && t.erases == 0);
    shutdown_assertion();
    defaults(); start(); img = image(); image_words[8191] = 0x4000;
    assert(icsp_program(&session, &img, &result) == ICSP_INVALID && t.erases == 0);
    shutdown_assertion();
    defaults(); start(); img = image(); img.program_count = 8191;
    assert(icsp_program(&session, &img, &result) == ICSP_INVALID && t.erases == 0);
    shutdown_assertion();
}
static void test_program_preserve(void) {
    defaults(); start(); icsp_image img = image(); icsp_result result;
    uint8_t original[256]; memcpy(original, t.eeprom, sizeof(original));
    assert(icsp_program(&session, &img, &result) == ICSP_OK);
    assert(result.verified && result.erase_started && result.program_words_written == 2);
    assert(result.eeprom_bytes_written == 0 && result.failed_address == 0xffff);
    assert(t.erases == 1 && t.writes == 3 && !t.forbidden_write);
    for (unsigned i = 0; i < 8192; ++i) assert(t.program[i] == image_words[i]);
    assert(memcmp(t.eeprom, original, sizeof(original)) == 0);
    assert(t.calibration[0] == 0x28f7 && t.calibration[1] == 0x3ffc);
    assert(t.uid[0] == 0x3f00 && t.uid[3] == 0x3f27);
    assert(t.config == 0x3ff2 && t.max_wait == 100);
    assert(!session.policy.allow_programming && !session.policy.backup_verified);
    assert(icsp_program(&session, &img, &result) == ICSP_POLICY_ERROR && t.erases == 1);
    icsp_close(&session); shutdown_assertion();
}
static void test_full_dense_image(void) {
    defaults(); start(); icsp_image img = image(); icsp_result result;
    for (unsigned i = 0; i < 8192; ++i) image_words[i] = (uint16_t)(i ^ 0x2345);
    assert(icsp_program(&session, &img, &result) == ICSP_OK);
    assert(result.program_words_written == 8191 && result.verified);
    assert(memcmp(t.program, image_words, sizeof(image_words)) == 0);
    assert(!t.forbidden_write && t.uid[0] == 0x3f00);
    icsp_close(&session);
}
static void test_eeprom_replace_and_errors(void) {
    defaults(); start(); icsp_image img = image(); icsp_result result;
    uint8_t replacement[256]; memcpy(replacement, t.eeprom, sizeof(replacement));
    replacement[0] = 0x42; replacement[255] = 0x11;
    img.eeprom_policy = ICSP_EEPROM_REPLACE; img.eeprom = replacement; img.eeprom_count = 256;
    assert(icsp_program(&session, &img, &result) == ICSP_OK);
    assert(result.eeprom_bytes_written == 2 && memcmp(t.eeprom, replacement, 256) == 0);
    defaults(); start(); img = image(); img.eeprom = replacement;
    assert(icsp_program(&session, &img, &result) == ICSP_INVALID && t.erases == 0);
    defaults(); start(); img = image(); t.corrupt_write = true;
    assert(icsp_program(&session, &img, &result) == ICSP_VERIFY_ERROR && !result.verified);
    assert(result.failed_address == 0); shutdown_assertion();
    defaults(); start(); t.corrupt_calibration = true;
    assert(icsp_program(&session, &img, &result) == ICSP_VERIFY_ERROR && !result.verified);
    shutdown_assertion();
    defaults(); start(); t.corrupt_eeprom = true;
    assert(icsp_program(&session, &img, &result) == ICSP_VERIFY_ERROR && !result.verified);
    assert(result.failed_address == 0x2100); shutdown_assertion();
}
static void test_faults(void) {
    defaults(); start(); uint16_t value;
    t.fail_after_clocks = 4;
    assert(icsp_read(&session, 0x2101, &value) == ICSP_IO_ERROR); shutdown_assertion();
    defaults(); start(); icsp_image img = image(); icsp_result result;
    t.cancel_erase = true;
    assert(icsp_program(&session, &img, &result) == ICSP_CANCELLED);
    assert(t.erases == 1 && t.writes == 0 && !result.verified); shutdown_assertion();
    defaults(); start(); t.bad_rail_erase = true;
    assert(icsp_program(&session, &img, &result) == ICSP_VOLTAGE_ERROR);
    assert(t.erases == 1 && t.writes == 0 && !result.verified); shutdown_assertion();
    defaults(); start(); t.lose_interlock_on_erase = true;
    assert(icsp_program(&session, &img, &result) == ICSP_CANCELLED);
    assert(t.erases == 1 && t.writes == 0 && !result.verified); shutdown_assertion();
}
static void test_vdd_first(void) {
    defaults(); t.controls_vdd = false; t.vdd_enabled = true;
    icsp_io callbacks = io(); icsp_policy rules = policy();
    rules.controls_target_vdd = false; rules.entry = ICSP_VDD_FIRST;
    rules.current_config_known = true; rules.current_config = 0x3ff2;
    assert(icsp_init(&session, &callbacks, &rules) == ICSP_OK);
    assert(icsp_open(&session) == ICSP_OK);
    icsp_image img = image(); icsp_result result;
    /* Unknown/internal-MCLR INTOSC new config would prevent VDD-first reentry. */
    img.config = 0x3fd4;
    assert(icsp_program(&session, &img, &result) == ICSP_POLICY_ERROR && t.erases == 0);
    shutdown_assertion();
    defaults(); t.controls_vdd = false; t.vdd_enabled = true;
    assert(icsp_init(&session, &callbacks, &rules) == ICSP_OK);
    assert(icsp_open(&session) == ICSP_OK);
    img.config = 0x3fd2; /* External HS oscillator does not make MCLR reset valid. */
    assert(icsp_program(&session, &img, &result) == ICSP_POLICY_ERROR && t.erases == 0);
    shutdown_assertion();
    defaults(); rules.current_config = 0x3fd2;
    assert(icsp_init(&session, &callbacks, &rules) == ICSP_POLICY_ERROR);
    assert(t.vpp_edges == 0);
    defaults(); rules.current_config_known = false;
    assert(icsp_init(&session, &callbacks, &rules) == ICSP_POLICY_ERROR);
    assert(t.vpp_edges == 0);
    defaults(); rules.current_config_known = true; rules.current_config = 0x3fd4;
    assert(icsp_init(&session, &callbacks, &rules) == ICSP_POLICY_ERROR);
    defaults(); t.controls_vdd = false; t.vdd_enabled = true; rules.current_config = 0x3ff1;
    assert(icsp_init(&session, &callbacks, &rules) == ICSP_OK);
    assert(icsp_open(&session) == ICSP_POLICY_ERROR); shutdown_assertion();
}
int main(void) {
    test_unqualified(); test_read_wire(); test_protection_device_and_policy();
    test_program_preserve(); test_full_dense_image(); test_eeprom_replace_and_errors(); test_faults(); test_vdd_first();
    assert(strcmp(icsp_status_name(ICSP_UNQUALIFIED), "unqualified") == 0);
    puts("ICSP native protocol, policy and fault tests passed");
    return 0;
}
