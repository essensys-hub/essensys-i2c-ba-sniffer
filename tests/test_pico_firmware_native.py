"""Exécute les validations et le CRC du firmware C sur l'hôte, sans simuler le PIO."""
from pathlib import Path
import subprocess


def test_native_capture_bounds_and_crc(tmp_path):
    firmware = Path(__file__).resolve().parents[1] / "firmware"
    test = tmp_path / "check.c"
    test.write_text('''
#include <assert.h>
#include "capture_config.h"
int main(void) {
    uint32_t rate, count;
    assert(capture_parse_request("CAPTURE 1000000 262144", &rate, &count));
    assert(rate == 1000000 && count == 262144);
    assert(!capture_parse_request("CAPTURE 4294967296001000000 4", &rate, &count));
    assert(!capture_parse_request("CAPTURE -4293967296 4", &rate, &count));
    assert(!capture_parse_request("CAPTURE 1000000 4 extra", &rate, &count));
    assert(!capture_parse_request("CAPTURE 1000000", &rate, &count));
    assert(!capture_parse_request("PROGRAM 1000000 4", &rate, &count));
    assert(capture_config_valid(120000000, 1000000, 262144));
    assert(capture_config_valid(120000000, 10000000, 4));
    assert(!capture_config_valid(120000000, 24000000, 4));
    assert(!capture_config_valid(120000000, 7000000, 4));
    assert(!capture_config_valid(120000000, 1000000, 262148));
    assert(!capture_config_valid(120000000, 1000000, 3));
    assert(!capture_config_valid(120000000, 0, 4));
    assert(capture_crc32((const uint8_t *)"123456789", 9) == 0xcbf43926);
    assert(capture_crc32((const uint8_t *)"", 0) == 0);
    return 0;
}
''')
    binary = tmp_path / "check"
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(firmware),
                    str(test), str(firmware / "capture_config.c"), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
