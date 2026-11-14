#ifndef ESSENSYS_ICSP_H
#define ESSENSYS_ICSP_H

/* PIC16F946-only protocol core. No GPIO or USB bindings and no raw-command API.
 * DS41244F (2009), sections 2-6. Addresses below are PIC words, not HEX bytes.
 * A zero-initialized policy does not authorize any hardware operation. */
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ICSP_PROGRAM_WORDS 8192u
#define ICSP_EEPROM_BYTES 256u
#define ICSP_CONFIG_ADDRESS 0x2007u
#define ICSP_DEVICE_ID_VALUE 0x1460u
#define ICSP_DEVICE_ID_MASK 0x3ff0u

typedef enum {
    ICSP_OK = 0, ICSP_INVALID, ICSP_UNQUALIFIED, ICSP_NOT_OPEN,
    ICSP_IO_ERROR, ICSP_CANCELLED, ICSP_VOLTAGE_ERROR, ICSP_WRONG_DEVICE,
    ICSP_PROTECTED, ICSP_VERIFY_ERROR, ICSP_POLICY_ERROR
} icsp_status;

typedef enum { ICSP_DATA_LOW, ICSP_DATA_HIGH, ICSP_DATA_HIZ } icsp_data_drive;
typedef enum { ICSP_VPP_FIRST = 0, ICSP_VDD_FIRST = 1 } icsp_entry;
typedef enum { ICSP_EEPROM_PRESERVE = 0, ICSP_EEPROM_REPLACE = 1 } icsp_eeprom_policy;

typedef struct {
    void *context;
    bool (*clock)(void *, bool high);
    bool (*data)(void *, icsp_data_drive drive);
    bool (*sample_data)(void *, bool *high);
    bool (*vpp)(void *, bool enabled); /* false holds MCLR low, not floating */
    bool (*vdd)(void *, bool enabled); /* mandatory for VPP-first */
    bool (*voltages_mv)(void *, uint16_t *vdd, uint16_t *vpp);
    bool (*delay_us)(void *, uint32_t duration); /* exact minimum, bounded callback */
    /* Deadline + USB cancellation + watchdog service + exclusive BA selection:
     * false if BP is enabled or a hardware interlock fails, even during waits. */
    bool (*alive)(void *);
    /* Mandatory idempotent electrical shutdown, even after any other callback
     * fails: VDD off first if controlled, VPP off/discharged, clock/data high-Z;
     * with external VDD keep MCLR low. This API never resumes target execution.
     * Must not depend on USB, the ordinary IO callbacks, or a successful init. */
    void (*safe_off)(void *);
} icsp_io;

typedef struct {
    bool board_qualified; /* hardware qualification, NOT a host override flag */
    bool controls_target_vdd;
    icsp_entry entry;
    bool current_config_known; /* required for externally powered VDD-first */
    uint16_t current_config;   /* qualified actual target state; VDD-first requires MCLRE=1 */
    bool allow_programming;
    bool backup_verified;      /* caller verified persistent backup before writes */
} icsp_policy;

typedef struct {
    uint16_t device_id, config, calibration[2], user_id[4];
    bool program_readable, eeprom_readable;
} icsp_identity;

typedef struct {
    const uint16_t *program_words; /* complete dense image, absent HEX words = 0x3fff */
    size_t program_count;          /* must be exactly 8192 */
    uint16_t config;               /* 14-bit, bit13 set; CP/CPD remain disabled */
    icsp_eeprom_policy eeprom_policy;
    const uint8_t *eeprom;         /* REPLACE requires exactly 256 bytes */
    size_t eeprom_count;
} icsp_image;

typedef struct {
    uint32_t program_words_written, eeprom_bytes_written;
    uint16_t failed_address;
    bool erase_started, verified;
} icsp_result;

/* Caller-owned storage. Treat fields as private; portable and allocation-free. */
typedef struct {
    icsp_io io;
    icsp_policy policy;
    icsp_identity identity;
    uint8_t eeprom_snapshot[ICSP_EEPROM_BYTES];
    uint16_t pc;
    bool active, identified, initialized;
    icsp_status last_status;
} icsp_session;

icsp_status icsp_init(icsp_session *, const icsp_io *, const icsp_policy *);
icsp_status icsp_open(icsp_session *);
void icsp_close(icsp_session *);
const char *icsp_status_name(icsp_status);
/* Read supports program 0000..1fff, user IDs 2000..2003, ID/config/calibration
 * 2006..2009 and EEPROM 2100..21ff. No reserved-area access or PC wrap-around. */
icsp_status icsp_read(icsp_session *, uint16_t address, uint16_t *word);
/* Full rewrite, program memory + config only by default. Preserves user IDs,
 * calibration and EEPROM. Writes are rejected for protected devices/images.
 * Write authorization is consumed by the first erase attempt. Caller must
 * close after success; errors always electrically shut down. */
icsp_status icsp_program(icsp_session *, const icsp_image *, icsp_result *);

#endif
