#include "capture_config.h"
#include <string.h>

static bool decimal(const char **cursor, uint32_t *value) {
    const char *p = *cursor;
    if (*p < '0' || *p > '9') return false;
    *value = 0;
    while (*p >= '0' && *p <= '9') {
        uint32_t digit = (uint32_t)(*p++ - '0');
        if (*value > (UINT32_MAX - digit) / 10) return false;
        *value = *value * 10 + digit;
    }
    *cursor = p;
    return true;
}

bool capture_parse_request(const char *command, uint32_t *rate, uint32_t *count) {
    if (strncmp(command, "CAPTURE ", 8) != 0) return false;
    const char *cursor = command + 8;
    if (!decimal(&cursor, rate) || *cursor++ != ' ') return false;
    return decimal(&cursor, count) && *cursor == '\0';
}

bool capture_config_valid(uint32_t clock_hz, uint32_t rate, uint32_t count) {
    if (rate < CAPTURE_MIN_RATE || rate > CAPTURE_MAX_RATE) return false;
    if (count < 4 || count > CAPTURE_MAX_SAMPLES || count % 4) return false;
    // ARCHITECTURE NOTE: an integer divider makes the reported rate exact.
    // Fractional dividers introduce jitter and are deliberately not accepted.
    return clock_hz % (2 * rate) == 0 && clock_hz / (2 * rate) >= 1 && clock_hz / (2 * rate) <= 65535;
}

uint32_t capture_crc32(const uint8_t *data, uint32_t length) {
    uint32_t crc = 0xffffffffu;
    for (uint32_t i = 0; i < length; ++i) {
        crc ^= data[i];
        for (unsigned bit = 0; bit < 8; ++bit)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}
