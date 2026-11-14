#ifndef ESSENSYS_PROGRAMMER_CONTROL_H
#define ESSENSYS_PROGRAMMER_CONTROL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PROGRAMMER_LINE_CAPACITY 64u
#define PROGRAMMER_LINE_TIMEOUT_US 1000000u

/* Diagnostic USB only. No command can authorize an unqualified board. */
typedef struct {
    void *ctx;
    void (*safe_off)(void *ctx);
    void (*reply)(void *ctx, const char *line);
} programmer_control_io;

typedef struct {
    programmer_control_io io;
    char line[PROGRAMMER_LINE_CAPACITY];
    size_t used;
    uint64_t first_byte_us;
    const char *frame_error;
    bool pending;
    bool cr_seen;
} programmer_control;

bool programmer_control_init(programmer_control *control, programmer_control_io io);
void programmer_control_feed(programmer_control *control, uint8_t byte, uint64_t now_us);
void programmer_control_poll(programmer_control *control, uint64_t now_us);
void programmer_control_disconnect(programmer_control *control);
#endif
