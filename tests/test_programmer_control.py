"""Execute the USB command parser in C; malformed streams must stay inactive."""
import ctypes
import json
from pathlib import Path
import subprocess

import pytest


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    root = Path(__file__).resolve().parents[1] / "firmware/programmer"
    temp = tmp_path_factory.mktemp("programmer-control")
    harness = temp / "harness.c"
    harness.write_text('''
#include "control.h"
#include <string.h>
static programmer_control c;
static char output[512];
static unsigned safe_count;
static void off(void *ctx) { (void)ctx; ++safe_count; }
static void emit(void *ctx, const char *s) {
    (void)ctx;
    strncpy(output, s, sizeof(output)-1);
    output[sizeof(output)-1] = 0;
}
void setup(void) {
    memset(output, 0, sizeof(output)); safe_count = 0;
    programmer_control_io io = {.safe_off=off, .reply=emit};
    programmer_control_init(&c, io);
}
void feed(unsigned char b, unsigned long long now) { programmer_control_feed(&c,b,now); }
void poll_time(unsigned long long now) { programmer_control_poll(&c,now); }
void disconnected(void) { programmer_control_disconnect(&c); }
const char *response(void) { return output; }
unsigned safes(void) { return safe_count; }
''')
    shared = temp / "control.so"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    "-I", str(root), str(harness), str(root / "control.c"),
                    "-o", str(shared)], check=True)
    lib = ctypes.CDLL(str(shared))
    lib.feed.argtypes = [ctypes.c_ubyte, ctypes.c_ulonglong]
    lib.poll_time.argtypes = [ctypes.c_ulonglong]
    lib.response.restype = ctypes.c_char_p
    lib.safes.restype = ctypes.c_uint
    return lib


@pytest.fixture
def controller(native):
    native.setup()
    return native


def send(c, wire, now=100):
    for byte in wire:
        c.feed(byte, now)
    return json.loads(c.response()) if c.response() else None


def test_info_and_stop_do_not_claim_qualified_hardware(controller):
    assert controller.safes() == 1
    info = send(controller, b"INFO\r\n")
    assert info["hardware_qualified"] is False
    assert info["programming_enabled"] is False
    assert info["ports"] == ["bp-bdm", "ba-icsp"]
    assert send(controller, b"STATUS\n")["rails_measured"] is False
    assert send(controller, b"STOP\n")["kind"] == "stopped"
    assert controller.safes() == 2


@pytest.mark.parametrize("command", [b"SELECT BP", b"SELECT BA", b"ERASE", b"PROGRAM 1",
                                     b"VPP 1", b"CAPTURE 1 4", b"SELECT BP STOP", b""])
def test_no_command_can_enable_a_port(controller, command):
    result = send(controller, command + b"\n")
    assert result["status"] == "error"
    assert result["target"] == "none"
    assert controller.safes() >= 2


def test_timeout_discards_tail_until_delimiter(controller):
    assert send(controller, b"IN", 10) is None
    controller.poll_time(1_000_010)
    assert controller.safes() == 2
    assert send(controller, b"FO\n", 1_000_011)["error"] == "command-timeout"
    assert send(controller, b"INFO\n", 1_000_012)["kind"] == "info"


@pytest.mark.parametrize("bad", [b"A" * 70, b"IN\x00FO", b"IN\rFO", b"INFO\r\r", b"INFO\xff"])
def test_bad_frames_cannot_smuggle_a_valid_suffix(controller, bad):
    result = send(controller, bad + b"STOP\n")
    assert result["status"] == "error"
    assert controller.safes() >= 2
    assert send(controller, b"INFO\n")["kind"] == "info"


def test_clock_regression_and_disconnect(controller):
    send(controller, b"IN", 500)
    assert send(controller, b"FO\n", 499)["error"] == "command-timeout"
    send(controller, b"SELECT ", 600)
    controller.disconnected()
    assert send(controller, b"INFO\n", 700)["kind"] == "info"


def test_every_non_ascii_control_byte_is_rejected(controller):
    for byte in list(range(32)) + list(range(127, 256)):
        if byte in (10, 13):
            continue
        assert send(controller, b"I" + bytes([byte]) + b"NFO\n")["status"] == "error"
