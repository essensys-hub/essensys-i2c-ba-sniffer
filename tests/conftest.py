import gzip
import shutil
from pathlib import Path

import pytest

CORPUS = Path(__file__).resolve().parents[1] / "captures" / "corpus"
RATE = 1_000_000


def load(name: str):
    raw = gzip.decompress((CORPUS / f"{name}.bin.gz").read_bytes())
    ann = (CORPUS / f"{name}.ann.txt").read_text().splitlines()
    exp = (CORPUS / f"{name}.expected.ndjson").read_text().splitlines()
    return raw, ann, exp


@pytest.fixture
def corpus():
    return load


needs_sigrok = pytest.mark.skipif(shutil.which("sigrok-cli") is None, reason="sigrok-cli absent")
