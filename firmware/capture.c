// ARCHITECTURE NOTE: capture first, transfer afterwards. USB backpressure cannot
// silently drop samples inside the requested acquisition window.
#include "capture.h"
#include "capture_config.h"
#include "hardware/clocks.h"
#include "hardware/dma.h"
#include "hardware/pio.h"
#include "hardware/regs/pio.h"
#include "hardware/watchdog.h"
#include "pico/stdlib.h"

static uint32_t samples[CAPTURE_MAX_SAMPLES / 4];
static PIO const acquisition_pio = pio0;
static uint state_machine, program_offset;
static int dma_channel;

void capture_init(void) {
    const uint16_t instructions[] = {
        pio_encode_pull(false, true),
        pio_encode_out(pio_x, 32),
        pio_encode_in(pio_pins, 8),
        pio_encode_jmp_x_dec(2),
        pio_encode_irq_wait(false, 0),
    };
    const struct pio_program program = {.instructions = instructions, .length = 5, .origin = -1};
    program_offset = pio_add_program(acquisition_pio, &program);
    state_machine = pio_claim_unused_sm(acquisition_pio, true);
    dma_channel = dma_claim_unused_channel(true);
    for (uint pin = 0; pin < 8; ++pin) {
        pio_gpio_init(acquisition_pio, pin);
        gpio_disable_pulls(pin);
    }
    pio_sm_set_consecutive_pindirs(acquisition_pio, state_machine, 0, 8, false);
}

bool capture_run(uint32_t rate, uint32_t count, const uint8_t **data) {
    const uint32_t clock_hz = clock_get_hz(clk_sys);
    if (!capture_config_valid(clock_hz, rate, count)) return false;
    pio_sm_set_enabled(acquisition_pio, state_machine, false);
    pio_sm_clear_fifos(acquisition_pio, state_machine);
    pio_sm_config config = pio_get_default_sm_config();
    sm_config_set_wrap(&config, program_offset + 4, program_offset + 4);
    sm_config_set_in_pins(&config, 0);
    // Four 8-bit samples form each 32-bit FIFO word, first sample at bits 7:0.
    sm_config_set_in_shift(&config, true, true, 32);
    // IN + JMP take two cycles per sample; the IRQ stops after exactly count.
    // No post-window RX stall can be confused with a loss during acquisition.
    sm_config_set_clkdiv_int_frac(&config, clock_hz / (2 * rate), 0);
    pio_sm_init(acquisition_pio, state_machine, program_offset, &config);
    pio_interrupt_clear(acquisition_pio, 0);
    const uint32_t stall_mask = 1u << (PIO_FDEBUG_RXSTALL_LSB + state_machine);
    acquisition_pio->fdebug = stall_mask;
    pio_sm_put_blocking(acquisition_pio, state_machine, count - 1);
    dma_channel_config dma = dma_channel_get_default_config(dma_channel);
    channel_config_set_transfer_data_size(&dma, DMA_SIZE_32);
    channel_config_set_read_increment(&dma, false);
    channel_config_set_write_increment(&dma, true);
    channel_config_set_high_priority(&dma, true);
    channel_config_set_dreq(&dma, pio_get_dreq(acquisition_pio, state_machine, false));
    dma_channel_configure(dma_channel, &dma, samples,
                          &acquisition_pio->rxf[state_machine], count / 4, true);
    const uint64_t deadline = time_us_64() + (uint64_t)count * 1000000u / rate + 1000000u;
    pio_sm_set_enabled(acquisition_pio, state_machine, true);
    while (dma_channel_is_busy(dma_channel) || !pio_interrupt_get(acquisition_pio, 0)) {
        watchdog_update();
        if (time_us_64() > deadline) {
            pio_sm_set_enabled(acquisition_pio, state_machine, false);
            dma_channel_abort(dma_channel);
            return false;
        }
        tight_loop_contents();
    }
    pio_sm_set_enabled(acquisition_pio, state_machine, false);
    if (acquisition_pio->fdebug & stall_mask) return false;
    *data = (const uint8_t *)samples;
    return true;
}
