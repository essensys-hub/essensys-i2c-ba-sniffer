#include <stdio.h>
#include <string.h>
#include "board_contract.h"
#include "control.h"
#include "hardware/clocks.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"

static void safe_off(void *unused) {
    (void)unused;
    /* Disable external drivers first. No source of VPP is enabled by this build. */
    const uint enables[] = {BA_VPP_EN_PIN, BA_OE_PIN, BP_OE_PIN};
    for (size_t i = 0; i < sizeof(enables) / sizeof(enables[0]); ++i) {
        gpio_init(enables[i]);
        gpio_put(enables[i], false);
        gpio_set_dir(enables[i], GPIO_OUT);
        gpio_disable_pulls(enables[i]);
    }
    const uint signals[] = {BA_PGC_PIN, BA_PGD_OUT_PIN, BA_PGD_IN_PIN, BA_PGD_DIR_PIN,
        BP_DSCLK_PIN, BP_DSI_PIN, BP_DSO_PIN, BP_BKPT_PIN, BP_RESET_PIN, BP_ALLPST_PIN,
        BP_RESET_SENSE_PIN,
        BA_VDD_SENSE_PIN, BA_VPP_SENSE_PIN, BP_VREF_SENSE_PIN};
    for (size_t i = 0; i < sizeof(signals) / sizeof(signals[0]); ++i) {
        gpio_init(signals[i]);
        gpio_set_dir(signals[i], GPIO_IN);
        gpio_disable_pulls(signals[i]);
    }
}

static void reply(void *unused, const char *line) {
    (void)unused;
    if (stdio_usb_connected()) {
        stdio_put_string(line, (int)strlen(line), false, false);
        stdio_flush();
    }
}

int main(void) {
    safe_off(NULL);
    set_sys_clock_khz(48000, true);
    stdio_init_all();
    programmer_control control;
    const programmer_control_io io = {.safe_off = safe_off, .reply = reply};
    if (!programmer_control_init(&control, io)) return 1;
    watchdog_enable(2000, true);
    bool connected = false;
    while (true) {
        watchdog_update();
        bool current = stdio_usb_connected();
        if (current != connected) {
            programmer_control_disconnect(&control);
            connected = current;
        }
        if (!connected) {
            sleep_ms(1);
            continue;
        }
        const int byte = getchar_timeout_us(1000);
        const uint64_t now = time_us_64();
        programmer_control_poll(&control, now);
        if (byte != PICO_ERROR_TIMEOUT) programmer_control_feed(&control, (uint8_t)byte, now);
    }
}
