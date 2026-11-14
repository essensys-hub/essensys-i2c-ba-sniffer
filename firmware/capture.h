#pragma once
#include <stdbool.h>
#include <stdint.h>

void capture_init(void);
bool capture_run(uint32_t rate, uint32_t count, const uint8_t **data);
