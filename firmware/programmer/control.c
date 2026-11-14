#include "control.h"
#include <stdio.h>
#include <string.h>

static void reset_frame(programmer_control *c) {
    c->used = 0;
    c->pending = false;
    c->cr_seen = false;
    c->frame_error = NULL;
}

static void error(programmer_control *c, const char *code) {
    char response[192];
    c->io.safe_off(c->io.ctx);
    (void)snprintf(response, sizeof(response),
        "{\"schema\":\"essensys.programmer.v1\",\"status\":\"error\","
        "\"error\":\"%s\",\"target\":\"none\"}\n", code);
    c->io.reply(c->io.ctx, response);
}

bool programmer_control_init(programmer_control *c, programmer_control_io io) {
    if (!c || !io.safe_off || !io.reply) return false;
    memset(c, 0, sizeof(*c));
    c->io = io;
    io.safe_off(io.ctx);
    return true;
}

static void dispatch(programmer_control *c) {
    c->line[c->used] = '\0';
    if (strcmp(c->line, "INFO") == 0) {
        c->io.reply(c->io.ctx,
            "{\"schema\":\"essensys.programmer.v1\",\"status\":\"ok\","
            "\"kind\":\"info\",\"mode\":\"diagnostic-only\",\"target\":\"none\","
            "\"hardware_qualified\":false,\"programming_enabled\":false,"
            "\"ports\":[\"bp-bdm\",\"ba-icsp\"],\"capture\":\"fx2\","
            "\"reason\":\"board-not-qualified\"}\n");
    } else if (strcmp(c->line, "STATUS") == 0) {
        c->io.reply(c->io.ctx,
            "{\"schema\":\"essensys.programmer.v1\",\"status\":\"ok\","
            "\"kind\":\"state\",\"target\":\"none\",\"programming_enabled\":false,"
            "\"outputs_commanded_safe\":true,\"rails_measured\":false}\n");
    } else if (strcmp(c->line, "STOP") == 0) {
        c->io.safe_off(c->io.ctx);
        c->io.reply(c->io.ctx,
            "{\"schema\":\"essensys.programmer.v1\",\"status\":\"ok\","
            "\"kind\":\"stopped\",\"target\":\"none\",\"programming_enabled\":false}\n");
    } else if (strcmp(c->line, "SELECT BP") == 0 || strcmp(c->line, "SELECT BA") == 0) {
        error(c, "board-not-qualified");
    } else {
        error(c, "unsupported-command");
    }
}

void programmer_control_poll(programmer_control *c, uint64_t now_us) {
    if (c->pending && !c->frame_error &&
        (now_us < c->first_byte_us ||
         now_us - c->first_byte_us >= PROGRAMMER_LINE_TIMEOUT_US)) {
        c->io.safe_off(c->io.ctx);
        c->frame_error = "command-timeout";
        /* Discard through LF: the tail of a timed-out command is not a new one. */
    }
}

void programmer_control_feed(programmer_control *c, uint8_t byte, uint64_t now_us) {
    programmer_control_poll(c, now_us);
    if (!c->pending) {
        c->pending = true;
        c->first_byte_us = now_us;
    }
    if (byte == '\n') {
        if (c->frame_error) error(c, c->frame_error);
        else dispatch(c);
        reset_frame(c);
        return;
    }
    if (c->frame_error) return;
    if (byte == '\r' && !c->cr_seen) {
        c->cr_seen = true;
        return;
    }
    if (c->cr_seen || byte < 32 || byte > 126) {
        c->frame_error = "invalid-command-byte";
    } else if (c->used >= PROGRAMMER_LINE_CAPACITY - 1) {
        c->frame_error = "command-too-long";
    } else {
        c->line[c->used++] = (char)byte;
        return;
    }
    c->io.safe_off(c->io.ctx);
}

void programmer_control_disconnect(programmer_control *c) {
    c->io.safe_off(c->io.ctx);
    reset_frame(c);
}
