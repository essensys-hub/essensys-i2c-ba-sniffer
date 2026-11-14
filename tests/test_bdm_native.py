"""Primary-manual BDM wire vectors and fault injection, no physical target."""
from pathlib import Path
import subprocess

import pytest


@pytest.fixture(scope="module")
def bdm_binary(tmp_path_factory):
    root = Path(__file__).resolve().parents[1]
    binary = tmp_path_factory.mktemp("bdm") / "bdm-check"
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(root / "firmware/programmer"),
        str(root / "tests/native/bdm_core.c"),
        str(root / "firmware/programmer/bdm.c"), "-o", str(binary),
    ], check=True)
    return binary


@pytest.mark.parametrize("case", range(28), ids=[
    "qualification", "long-busy-msb-data-ffff", "unaligned-tail", "bounds",
    "bus-error", "illegal-command", "unknown-status", "atomic-on-second-word-error",
    "bounded-busy", "cancel-mid-frame", "voltage-mid-frame", "reset-mid-frame",
    "interlock-mid-frame", "io-mid-frame", "voltage-before-enable", "reset-before-enable",
    "interlock-before-enable", "cancel-before-enable", "halt-timeout", "explicit-resume",
    "resume-still-halted", "debug-revision-not-identity", "halt-and-revision-required",
    "invalid-config", "wall-timeout", "enable-error-release",
    "reopen-active-releases", "null-csr-releases",
])
def test_bdm_protocol(bdm_binary, case):
    subprocess.run([str(bdm_binary), str(case)], check=True, timeout=5)
