"""Génère le corpus de référence ``captures/corpus/``.

Pour chaque scénario :

- ``<nom>.bin.gz``        : flux brut synthétique (format sigrok binary, 1 MHz, bit 0 = SCL, bit 1 = SDA) ;
- ``<nom>.ann.txt``       : annotations produites par le **décodeur I2C de sigrok** (oracle indépendant) ;
- ``<nom>.expected.ndjson`` : sortie attendue du décodeur (hors enregistrement ``session``).

Usage : ``python tools/make_corpus.py`` (sigrok-cli requis). Toute modification
de la sortie attendue doit être relue : c'est la référence de non-régression.
"""

from __future__ import annotations

import gzip
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "decoder"))

from essensys_i2c_sniffer.output import to_ndjson  # noqa: E402
from essensys_i2c_sniffer.pipeline import I2C_CLASSES, decode_offline, sigrok_bin  # noqa: E402
from essensys_i2c_sniffer.synth import Waveform, request, response  # noqa: E402

RATE = 1_000_000
OUT = ROOT / "captures" / "corpus"


def ok(w: Waveform, addr: int, code: int, payload: bytes) -> None:
    req = request(code, payload)
    w.exchange(addr, req, response(code, req))


def scenarios() -> dict[str, tuple[str, Waveform]]:
    s: dict[str, tuple[str, Waveform]] = {}

    w = Waveform().idle_ms(1)
    ok(w, 0x11, 1, bytes([0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])); w.idle_ms(100)
    ok(w, 0x11, 1, bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])); w.idle_ms(5)
    s["forcage_sorties_ok"] = ("FORCAGE_SORTIES vers 0x11 : lampe 0 ON puis OFF, réponses validées", w)

    w = Waveform().idle_ms(1)
    ok(w, 0x12, 2, bytes([0x01, 0x00, 0x02, 0x01, 0, 0, 0, 0])); w.idle_ms(5)
    s["conf_sorties_ok"] = ("CONF_SORTIES vers 0x12 : modes des 4 variateurs + bourrage", w)

    w = Waveform().idle_ms(1)
    ok(w, 0x13, 3, bytes([10, 0, 5] + [0] * 13)); w.idle_ms(5)
    s["tps_extinction_ok"] = ("TPS_EXTINCTION vers 0x13 : minutes par relais lampe", w)

    w = Waveform().idle_ms(1)
    ok(w, 0x11, 4, bytes([30, 30, 25, 0, 0, 0, 0, 0])); w.idle_ms(5)
    s["tps_action_ok"] = ("TPS_ACTION vers 0x11 : secondes par volet", w)

    w = Waveform().idle_ms(1)
    ok(w, 0x12, 5, bytes([0x00])); w.idle_ms(100)
    ok(w, 0x12, 5, bytes([0x02])); w.idle_ms(5)
    s["actions_ok"] = ("ACTIONS vers 0x12 : transition du drapeau blocage des volets", w)

    w = Waveform().idle_ms(1)
    w.address_nack(0x12); w.idle_ms(5)
    s["address_nack"] = ("NACK d'adresse : BA chambres absent", w)

    w = Waveform().idle_ms(1)
    bad = request(1, bytes([0x00, 0x01, 0, 0, 0, 0, 0, 0]), corrupt_crc=True)
    w.exchange(0x11, bad, response(1, bad, accepted=False)); w.idle_ms(5)
    s["crc_faux"] = ("CRC de requête faux : le BA renvoie 00 00 en écho", w)

    w = Waveform().idle_ms(1)
    for _ in range(3):
        w.address_nack(0x13); w.idle_ms(100)
    w.idle_ms(2500)
    s["repetitions_abandon"] = ("3 tentatives NACK vers 0x13 puis silence : abandon du maître", w)

    w = Waveform().idle_ms(1).low("SDA", 15).idle_ms(2)
    s["ligne_bloquee"] = ("SDA maintenue basse 15 ms", w)

    w = Waveform().idle_ms(1)
    ok(w, 0x11, 1, bytes([0x00, 0x01, 0, 0, 0, 0, 0, 0])); w.idle_ms(100)
    w.address_nack(0x12); w.idle_ms(100)
    w.address_nack(0x13); w.idle_ms(5)
    s["cas_installation_2026_10"] = ("Cas observé le 2026-10-13 : 0x11 répond, 0x12 et 0x13 muets (signal synthétique)", w)
    return s


def annotate(raw: bytes) -> list[str]:
    cmd = [sigrok_bin(), "-I", f"binary:numchannels=2:samplerate={RATE}", "-i", "-", "-P", "i2c:scl=0:sda=1",
           "-A", f"i2c={I2C_CLASSES}", "--protocol-decoder-samplenum"]
    return subprocess.run(cmd, input=raw, capture_output=True, check=True).stdout.decode().splitlines()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = ["# Corpus de référence", "", "Généré par `tools/make_corpus.py`. Signaux synthétiques à 1 MHz (bit 0 = SCL, bit 1 = SDA), annotations par le décodeur I2C de sigrok.", "", "| Scénario | Description |", "|---|---|"]
    for name, (desc, w) in scenarios().items():
        raw = bytes(w.data)
        (OUT / f"{name}.bin.gz").write_bytes(gzip.compress(raw, mtime=0))
        lines = annotate(raw)
        (OUT / f"{name}.ann.txt").write_text("\n".join(lines) + "\n")
        records = decode_offline(raw, lines, RATE)
        (OUT / f"{name}.expected.ndjson").write_text("".join(to_ndjson(r) + "\n" for r in records))
        index.append(f"| `{name}` | {desc} |")
        print(name, len(raw), "échantillons,", len(records), "enregistrements")
    (OUT / "README.md").write_text("\n".join(index) + "\n")


if __name__ == "__main__":
    main()
