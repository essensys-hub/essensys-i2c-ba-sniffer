#pragma once
#include <stdbool.h>
#include <stdint.h>

#define CAPTURE_MAX_SAMPLES 262144u
#define CAPTURE_MIN_RATE 1000u
#define CAPTURE_MAX_RATE 10000000u

bool capture_config_valid(uint32_t clock_hz, uint32_t rate, uint32_t count);
bool capture_parse_request(const char *command, uint32_t *rate, uint32_t *count);
uint32_t capture_crc32(const uint8_t *data, uint32_t length);
