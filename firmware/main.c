#include <stdio.h>
#include <string.h>
#include "capture.h"
#include "capture_config.h"
#include "hardware/clocks.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"

static void error(const char *code) {
    printf("{\"schema\":\"essensys.pico.v1\",\"status\":\"error\",\"error\":\"%s\"}\n", code);
}

static void dispatch(const char *command) {
    uint32_t rate, count;
    if (strcmp(command, "INFO") == 0) {
        printf("{\"schema\":\"essensys.pico.v1\",\"status\":\"ok\",\"mode\":\"capture-only\","
               "\"channels\":8,\"clock_hz\":%lu,\"max_samples\":%u,\"icsp_enabled\":false}\n",
               (unsigned long)clock_get_hz(clk_sys), CAPTURE_MAX_SAMPLES);
        return;
    }
    if (!capture_parse_request(command, &rate, &count)) {
        error("unsupported-command");
        return;
    }
    if (!capture_config_valid(clock_get_hz(clk_sys), rate, count)) {
        error("invalid-capture-parameters");
        return;
    }
    const uint8_t *data;
    if (!capture_run(rate, count, &data)) {
        error("acquisition-incomplete-or-timeout");
        return;
    }
    const uint32_t crc = capture_crc32(data, count);
    watchdog_update();
    printf("{\"schema\":\"essensys.pico.v1\",\"status\":\"ok\",\"kind\":\"capture\","
           "\"channels\":8,\"samplerate\":%lu,\"samples\":%lu,\"crc32\":%lu}\n",
           (unsigned long)rate, (unsigned long)count, (unsigned long)crc);
    for (uint32_t offset = 0; offset < count; offset += 256) {
        if (!stdio_usb_connected()) return;  // Host rejects the truncated frame.
        uint32_t length = count - offset < 256 ? count - offset : 256;
        // Raw binary must bypass newline/CRLF conversion in the stdio driver.
        stdio_put_string((const char *)data + offset, length, false, false);
        watchdog_update();
    }
    stdio_flush();
}

int main(void) {
    // 120 MHz yields exact integer dividers at 1, 2, 5 and 10 MS/s.
    set_sys_clock_khz(120000, true);
    // Reserved VPP enables remain low. No ICSP command exists until the
    // MCLR/NCP803 circuit of the target BA has been qualified on a bench.
    for (uint pin = 12; pin <= 13; ++pin) {
        gpio_init(pin);
        gpio_put(pin, false);
        gpio_set_dir(pin, GPIO_OUT);
    }
    stdio_init_all();
    capture_init();
    watchdog_enable(2000, true);
    char line[96];
    size_t used = 0;
    bool overflow = false;
    while (true) {
        watchdog_update();
        const int c = getchar_timeout_us(1000);
        if (c == PICO_ERROR_TIMEOUT) continue;
        if (c == '\r') continue;
        if (c == '\n') {
            line[used] = '\0';
            if (overflow) error("command-too-long");
            else dispatch(line);
            used = 0;
            overflow = false;
        } else if (c < 32 || c > 126 || used == sizeof(line) - 1) {
            overflow = true;
        } else if (!overflow) {
            line[used++] = (char)c;
        }
    }
}
