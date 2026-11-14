"""Compile/run the PIC16F946 engine against an edge-driven target model.

The model validates protocol bytes, timings and faults, not electrical hardware.
"""
from pathlib import Path
import subprocess


def test_icsp_protocol_policy_and_faults(tmp_path):
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path / "icsp-check"
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(root / "firmware/programmer"),
        str(root / "tests/native/icsp_fixture.c"),
        str(root / "firmware/programmer/icsp.c"), "-o", str(binary),
    ], check=True)
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    assert "ICSP native protocol, policy and fault tests passed" in result.stdout
