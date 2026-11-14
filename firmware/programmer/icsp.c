#include "icsp.h"
#include <string.h>

/* DS41244F table 3-1. x bits are transmitted as 0; wire order is LSb first. */
enum { LOAD_CONFIG = 0x00, LOAD_PROGRAM = 0x02, LOAD_DATA = 0x03,
       READ_PROGRAM = 0x04, READ_DATA = 0x05, INCREMENT = 0x06,
       BEGIN_INTERNAL = 0x08, ERASE_PROGRAM = 0x09 };
/* Table 6-1: TSET1/THLD1 >= 100ns, TDLY1/2 >= 1us, TDLY3 <= 80ns.
 * Conservative 1us phases; callback must not return early. Waits are split
 * into <=100us so cancellation/deadline remains serviced during erase/write. */
#define PHASE_US 1u
#define ENTRY_US 5u
#define ERASE_US 6000u
#define WRITE_PROGRAM_US 3000u
#define WRITE_DATA_US 6000u
#define DISCHARGE_US 100u

static bool valid_config(uint16_t config) {
    return config <= 0x3fffu && (config & 0x2000u) != 0;
}
static bool vdd_first_compatible(uint16_t config) {
    /* Stricter than entry alone in DS41244F: external VDD cannot be removed
     * by safe_off. Require MCLRE so holding MCLR low keeps the target in reset
     * after VPP is removed, even if an external oscillator remains active. */
    return (config & 0x20u) != 0;
}
static icsp_status fail(icsp_session *s, icsp_status status) {
    if (s != NULL) {
        if (s->initialized) s->io.safe_off(s->io.context);
        s->active = false;
        s->identified = false;
        s->last_status = status;
    }
    return status;
}
static icsp_status alive(icsp_session *s) {
    return s->io.alive(s->io.context) ? ICSP_OK : fail(s, ICSP_CANCELLED);
}
static icsp_status rails(icsp_session *s, bool require_vpp);
static icsp_status wait_us(icsp_session *s, uint32_t duration) {
    while (duration != 0) {
        if (alive(s) != ICSP_OK) return s->last_status;
        uint32_t step = duration > 100u ? 100u : duration;
        if (!s->io.delay_us(s->io.context, step)) return fail(s, ICSP_IO_ERROR);
        if (s->active && step == 100u) {
            icsp_status status = rails(s, true);
            if (status != ICSP_OK) return status;
        }
        duration -= step;
    }
    return alive(s);
}
static icsp_status rails(icsp_session *s, bool require_vpp) {
    uint16_t vdd, vpp;
    if (alive(s) != ICSP_OK) return s->last_status;
    if (!s->io.voltages_mv(s->io.context, &vdd, &vpp)) return fail(s, ICSP_IO_ERROR);
    /* BA policy deliberately narrower than device's 2.0V read/write minimum:
     * the engine uses a qualified nominal 5V target and supports bulk erase. */
    if (vdd < 4500u || vdd > 5500u ||
        (require_vpp && (vpp < 10000u || vpp > 12000u)))
        return fail(s, ICSP_VOLTAGE_ERROR);
    return ICSP_OK;
}
static icsp_status clock_pin(icsp_session *s, bool high) {
    return s->io.clock(s->io.context, high) ? ICSP_OK : fail(s, ICSP_IO_ERROR);
}
static icsp_status data_pin(icsp_session *s, icsp_data_drive value) {
    return s->io.data(s->io.context, value) ? ICSP_OK : fail(s, ICSP_IO_ERROR);
}
#define TRY(call) do { icsp_status status_ = (call); if (status_ != ICSP_OK) return status_; } while (0)

static icsp_status write_bits(icsp_session *s, uint16_t bits, unsigned count) {
    for (unsigned i = 0; i < count; ++i) {
        TRY(data_pin(s, (bits & 1u) ? ICSP_DATA_HIGH : ICSP_DATA_LOW));
        TRY(wait_us(s, PHASE_US));
        TRY(clock_pin(s, true));
        TRY(wait_us(s, PHASE_US));
        TRY(clock_pin(s, false)); /* target latches here */
        TRY(wait_us(s, PHASE_US));
        bits >>= 1;
    }
    TRY(data_pin(s, ICSP_DATA_LOW));
    return wait_us(s, PHASE_US);
}
static icsp_status command(icsp_session *s, unsigned code) {
    TRY(rails(s, true));
    return write_bits(s, (uint16_t)code, 6);
}
static icsp_status load(icsp_session *s, unsigned code, uint16_t data) {
    TRY(command(s, code));
    /* 0 start, 14 data LSb-first, 0 stop. */
    return write_bits(s, (uint16_t)(data << 1), 16);
}
static icsp_status read_current(icsp_session *s, bool eeprom, uint16_t *word) {
    TRY(command(s, eeprom ? READ_DATA : READ_PROGRAM));
    TRY(data_pin(s, ICSP_DATA_HIZ));
    TRY(wait_us(s, PHASE_US));
    uint16_t value = 0;
    for (unsigned cycle = 0; cycle < 16; ++cycle) {
        TRY(clock_pin(s, true));
        TRY(wait_us(s, PHASE_US)); /* > TDLY3 before sample */
        /* First and last cycles are high impedance at the target. Do not
         * interpret their sampled levels as reliable framing/error flags. */
        if (cycle >= 1 && cycle <= 14) {
            bool high;
            if (!s->io.sample_data(s->io.context, &high)) return fail(s, ICSP_IO_ERROR);
            if (high) value |= (uint16_t)(1u << (cycle - 1));
        }
        TRY(clock_pin(s, false));
        TRY(wait_us(s, PHASE_US));
    }
    TRY(data_pin(s, ICSP_DATA_LOW));
    TRY(wait_us(s, PHASE_US));
    *word = eeprom ? (value & 0xffu) : value;
    return ICSP_OK;
}
static icsp_status enter(icsp_session *s) {
    /* Qualification is checked again on every re-entry; no raw bypass path. */
    if (!s->policy.board_qualified) return fail(s, ICSP_UNQUALIFIED);
    TRY(alive(s));
    if (!s->io.vpp(s->io.context, false)) return fail(s, ICSP_IO_ERROR);
    TRY(clock_pin(s, false));
    TRY(data_pin(s, ICSP_DATA_LOW));
    if (s->policy.entry == ICSP_VPP_FIRST) {
        if (!s->io.vdd(s->io.context, false)) return fail(s, ICSP_IO_ERROR);
        TRY(wait_us(s, ENTRY_US));
        /* Electrical qualification must establish VDD discharged and a VPP
         * edge <=1us; software delay cannot prove either property. */
        uint16_t vdd, vpp;
        if (!s->io.voltages_mv(s->io.context, &vdd, &vpp)) return fail(s, ICSP_IO_ERROR);
        if (vdd > 200u || vpp > 200u) return fail(s, ICSP_VOLTAGE_ERROR);
        if (!s->io.vpp(s->io.context, true)) return fail(s, ICSP_IO_ERROR);
        TRY(wait_us(s, ENTRY_US));
        if (!s->io.voltages_mv(s->io.context, &vdd, &vpp)) return fail(s, ICSP_IO_ERROR);
        if (vdd > 200u || vpp < 10000u || vpp > 12000u) return fail(s, ICSP_VOLTAGE_ERROR);
        if (!s->io.vdd(s->io.context, true)) return fail(s, ICSP_IO_ERROR);
        TRY(wait_us(s, ENTRY_US));
    } else {
        TRY(rails(s, false));
        uint16_t vdd, vpp;
        if (!s->io.voltages_mv(s->io.context, &vdd, &vpp)) return fail(s, ICSP_IO_ERROR);
        if (vpp > 200u) return fail(s, ICSP_VOLTAGE_ERROR);
        TRY(wait_us(s, ENTRY_US));
        if (!s->io.vpp(s->io.context, true)) return fail(s, ICSP_IO_ERROR);
        TRY(wait_us(s, ENTRY_US));
    }
    TRY(rails(s, true));
    s->pc = 0;
    s->active = true;
    return ICSP_OK;
}
static icsp_status restart(icsp_session *s) {
    s->io.safe_off(s->io.context);
    s->active = false;
    TRY(wait_us(s, DISCHARGE_US));
    return enter(s);
}
static icsp_status seek(icsp_session *s, uint16_t address, bool eeprom) {
    uint16_t wanted = eeprom ? (uint16_t)(address - 0x2100u) : address;
    bool config = !eeprom && address >= 0x2000u;
    if ((!config && s->pc >= 0x2000u) || wanted < s->pc) TRY(restart(s));
    if (config && s->pc < 0x2000u) {
        /* All-ones load prevents accidental programming of old latch data. */
        TRY(load(s, LOAD_CONFIG, 0x3fffu));
        s->pc = 0x2000u;
    }
    while (s->pc < wanted) {
        TRY(command(s, INCREMENT));
        ++s->pc;
    }
    return ICSP_OK;
}
static bool readable_address(uint16_t address) {
    return address < 0x2000u || (address >= 0x2000u && address <= 0x2003u) ||
           (address >= 0x2006u && address <= 0x2009u) ||
           (address >= 0x2100u && address <= 0x21ffu);
}
static icsp_status read_at(icsp_session *s, uint16_t address, uint16_t *word) {
    bool eeprom = address >= 0x2100u;
    TRY(seek(s, address, eeprom));
    return read_current(s, eeprom, word);
}
static icsp_status snapshot_identity(icsp_session *s, icsp_identity *id) {
    for (unsigned i = 0; i < 4; ++i) TRY(read_at(s, (uint16_t)(0x2000u + i), &id->user_id[i]));
    TRY(read_at(s, 0x2006u, &id->device_id));
    if ((id->device_id & ICSP_DEVICE_ID_MASK) != ICSP_DEVICE_ID_VALUE)
        return fail(s, ICSP_WRONG_DEVICE);
    TRY(read_at(s, 0x2007u, &id->config));
    if (!valid_config(id->config)) return fail(s, ICSP_VERIFY_ERROR);
    TRY(read_at(s, 0x2008u, &id->calibration[0]));
    TRY(read_at(s, 0x2009u, &id->calibration[1]));
    id->program_readable = (id->config & 0x40u) != 0;
    id->eeprom_readable = (id->config & 0x80u) != 0;
    return ICSP_OK;
}

icsp_status icsp_init(icsp_session *s, const icsp_io *io, const icsp_policy *policy) {
    if (s == NULL) return ICSP_INVALID;
    memset(s, 0, sizeof(*s));
    if (io == NULL || policy == NULL || io->safe_off == NULL) return ICSP_INVALID;
    s->io = *io;
    s->policy = *policy;
    s->initialized = true;
    s->io.safe_off(s->io.context); /* startup never relies on previous pin state */
    if (!io->clock || !io->data || !io->sample_data || !io->vpp || !io->voltages_mv ||
        !io->delay_us || !io->alive) return fail(s, ICSP_INVALID);
    if (policy->entry != ICSP_VPP_FIRST && policy->entry != ICSP_VDD_FIRST)
        return fail(s, ICSP_INVALID);
    if (policy->entry == ICSP_VPP_FIRST && (!policy->controls_target_vdd || !io->vdd))
        return fail(s, ICSP_POLICY_ERROR);
    if (policy->entry == ICSP_VDD_FIRST &&
        (policy->controls_target_vdd || !policy->current_config_known ||
         !valid_config(policy->current_config) || !vdd_first_compatible(policy->current_config)))
        return fail(s, ICSP_POLICY_ERROR);
    s->last_status = ICSP_OK;
    return ICSP_OK;
}
icsp_status icsp_open(icsp_session *s) {
    if (s == NULL || !s->initialized) return ICSP_INVALID;
    if (s->last_status != ICSP_OK || s->active) return fail(s, ICSP_POLICY_ERROR);
    TRY(enter(s));
    TRY(snapshot_identity(s, &s->identity));
    if (s->policy.entry == ICSP_VDD_FIRST && s->identity.config != s->policy.current_config)
        return fail(s, ICSP_POLICY_ERROR);
    s->identified = true;
    if (s->identity.eeprom_readable) {
        for (unsigned i = 0; i < ICSP_EEPROM_BYTES; ++i) {
            uint16_t value;
            TRY(read_at(s, (uint16_t)(0x2100u + i), &value));
            s->eeprom_snapshot[i] = (uint8_t)value;
        }
    }
    return ICSP_OK;
}
void icsp_close(icsp_session *s) {
    if (s != NULL && s->initialized) {
        s->io.safe_off(s->io.context);
        s->active = false;
        s->identified = false;
    }
}
icsp_status icsp_read(icsp_session *s, uint16_t address, uint16_t *word) {
    if (s == NULL || !s->initialized) return ICSP_INVALID;
    if (!s->active || !s->identified) return fail(s, ICSP_NOT_OPEN);
    if (word == NULL || !readable_address(address)) return fail(s, ICSP_INVALID);
    if ((address < 0x2000u && !s->identity.program_readable) ||
        (address >= 0x2100u && !s->identity.eeprom_readable)) return fail(s, ICSP_PROTECTED);
    return read_at(s, address, word);
}
static icsp_status write_verify(icsp_session *s, uint16_t address, uint16_t value, bool data) {
    TRY(seek(s, address, data));
    TRY(load(s, data ? LOAD_DATA : LOAD_PROGRAM, value));
    TRY(command(s, BEGIN_INTERNAL));
    TRY(wait_us(s, data ? WRITE_DATA_US : WRITE_PROGRAM_US));
    TRY(wait_us(s, DISCHARGE_US));
    uint16_t actual;
    TRY(read_current(s, data, &actual));
    if (actual != value) return fail(s, ICSP_VERIFY_ERROR);
    return ICSP_OK;
}
static bool identity_unchanged(const icsp_identity *a, const icsp_identity *b, bool compare_config) {
    if (a->device_id != b->device_id || (compare_config && a->config != b->config)) return false;
    for (unsigned i = 0; i < 4; ++i) if (a->user_id[i] != b->user_id[i]) return false;
    for (unsigned i = 0; i < 2; ++i) if (a->calibration[i] != b->calibration[i]) return false;
    return true;
}
icsp_status icsp_program(icsp_session *s, const icsp_image *image, icsp_result *result) {
    if (result != NULL) { memset(result, 0, sizeof(*result)); result->failed_address = 0xffffu; }
    if (s == NULL || !s->initialized) return ICSP_INVALID;
    if (!s->active || !s->identified) return fail(s, ICSP_NOT_OPEN);
    if (!image || !result || !image->program_words || image->program_count != ICSP_PROGRAM_WORDS ||
        !valid_config(image->config)) return fail(s, ICSP_INVALID);
    if (!s->policy.allow_programming || !s->policy.backup_verified)
        return fail(s, ICSP_POLICY_ERROR);
    if (!s->identity.program_readable || !s->identity.eeprom_readable || (image->config & 0xc0u) != 0xc0u)
        return fail(s, ICSP_PROTECTED);
    if (s->policy.entry == ICSP_VDD_FIRST && !vdd_first_compatible(image->config))
        return fail(s, ICSP_POLICY_ERROR);
    if ((image->eeprom_policy != ICSP_EEPROM_PRESERVE && image->eeprom_policy != ICSP_EEPROM_REPLACE) ||
        (image->eeprom_policy == ICSP_EEPROM_PRESERVE && (image->eeprom || image->eeprom_count)) ||
        (image->eeprom_policy == ICSP_EEPROM_REPLACE && (!image->eeprom || image->eeprom_count != ICSP_EEPROM_BYTES)))
        return fail(s, ICSP_INVALID);
    /* Validate the entire input before the first erase. Never mask malformed words. */
    for (unsigned i = 0; i < ICSP_PROGRAM_WORDS; ++i)
        if (image->program_words[i] > 0x3fffu) return fail(s, ICSP_INVALID);
    icsp_identity before;
    TRY(snapshot_identity(s, &before));
    if (!identity_unchanged(&s->identity, &before, true)) return fail(s, ICSP_VERIFY_ERROR);
    for (unsigned i = 0; i < ICSP_EEPROM_BYTES; ++i) {
        uint16_t current;
        TRY(read_at(s, (uint16_t)(0x2100u + i), &current));
        if (current != s->eeprom_snapshot[i]) return fail(s, ICSP_VERIFY_ERROR);
    }
    /* No LOAD_CONFIG before erase: PC must be in program space. This preserves
     * user IDs. CPD=1 has already been checked so EEPROM is not bulk-erased. */
    TRY(restart(s));
    s->policy.allow_programming = false;
    s->policy.backup_verified = false;
    result->erase_started = true; /* conservatively true even if command aborts */
    TRY(command(s, ERASE_PROGRAM));
    TRY(wait_us(s, ERASE_US));
    /* Verify every erased/programmed word. No row erase or batch latch state. */
    for (unsigned i = 0; i < ICSP_PROGRAM_WORDS; ++i) {
        result->failed_address = (uint16_t)i;
        uint16_t erased;
        TRY(read_at(s, (uint16_t)i, &erased));
        if (erased != 0x3fffu) return fail(s, ICSP_VERIFY_ERROR);
        if (image->program_words[i] != 0x3fffu) {
            TRY(write_verify(s, (uint16_t)i, image->program_words[i], false));
            ++result->program_words_written;
        }
    }
    for (unsigned i = 0; i < ICSP_EEPROM_BYTES; ++i) {
        result->failed_address = (uint16_t)(0x2100u + i);
        uint16_t expected = image->eeprom_policy == ICSP_EEPROM_PRESERVE ?
                            s->eeprom_snapshot[i] : image->eeprom[i];
        uint16_t current;
        TRY(read_at(s, result->failed_address, &current));
        if (image->eeprom_policy == ICSP_EEPROM_REPLACE && current != expected) {
            /* Data programming is self-erasing. No blanket EEPROM erase. */
            TRY(write_verify(s, result->failed_address, expected, true));
            ++result->eeprom_bytes_written;
        } else if (current != expected) return fail(s, ICSP_VERIFY_ERROR);
    }
    /* Config is written last, CP and CPD kept at 1 so verification is possible.
     * Config latches do not self-clear; restart immediately afterward resets
     * all eight, without ever issuing a write at 2008/2009. */
    result->failed_address = ICSP_CONFIG_ADDRESS;
    uint16_t erased_config;
    TRY(read_at(s, ICSP_CONFIG_ADDRESS, &erased_config));
    if (erased_config != 0x3fffu) return fail(s, ICSP_VERIFY_ERROR);
    TRY(write_verify(s, ICSP_CONFIG_ADDRESS, image->config, false));
    TRY(restart(s));
    icsp_identity after;
    TRY(snapshot_identity(s, &after));
    if (!identity_unchanged(&before, &after, false) || after.config != image->config)
        return fail(s, ICSP_VERIFY_ERROR);
    /* Final readback after ALL writes detects corruption from later operations,
     * not only an immediate read at the last programmed location. */
    for (unsigned i = 0; i < ICSP_PROGRAM_WORDS; ++i) {
        result->failed_address = (uint16_t)i;
        uint16_t actual;
        TRY(read_at(s, (uint16_t)i, &actual));
        if (actual != image->program_words[i]) return fail(s, ICSP_VERIFY_ERROR);
    }
    for (unsigned i = 0; i < ICSP_EEPROM_BYTES; ++i) {
        result->failed_address = (uint16_t)(0x2100u + i);
        uint16_t actual;
        uint8_t expected = image->eeprom_policy == ICSP_EEPROM_PRESERVE ?
                           s->eeprom_snapshot[i] : image->eeprom[i];
        TRY(read_at(s, result->failed_address, &actual));
        if (actual != expected) return fail(s, ICSP_VERIFY_ERROR);
    }
    if (image->eeprom_policy == ICSP_EEPROM_REPLACE)
        memcpy(s->eeprom_snapshot, image->eeprom, ICSP_EEPROM_BYTES);
    s->identity = after;
    s->policy.current_config = after.config;
    result->failed_address = 0xffffu;
    result->verified = true;
    return ICSP_OK;
}
const char *icsp_status_name(icsp_status status) {
    static const char *const names[] = {"ok", "invalid", "unqualified", "not_open",
        "io_error", "cancelled", "voltage_error", "wrong_device", "protected",
        "verify_error", "policy_error"};
    return (unsigned)status < sizeof(names)/sizeof(names[0]) ? names[status] : "unknown";
}
