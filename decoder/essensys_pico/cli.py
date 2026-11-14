"""Capture Pico et inspection HEX ; aucune programmation de BA dans cette version."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .hex_image import HexError, PicImage
from .transport import ProtocolError, capture, read_header, validate_request


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pico 2 : acquisition 8 voies et inspection HEX hors matériel")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect-hex", help="vérifier une image PIC16F946 sans ouvrir de port")
    inspect.add_argument("file", type=Path)
    info = sub.add_parser("info", help="lire les capacités du firmware")
    info.add_argument("--port", required=True)
    acq = sub.add_parser("capture", help="acquisition bornée, fichier brut pour rejeu sigrok")
    acq.add_argument("--port", required=True)
    acq.add_argument("--samplerate", type=int, default=1_000_000)
    acq.add_argument("--samples", type=int, default=262144)
    acq.add_argument("--out", type=Path, required=True, help="nouveau fichier .bin")
    return parser


def open_port(name: str, timeout: float):
    try:
        import serial
    except ImportError as exc:
        raise ValueError("installer l'option : pip install -e '.[pico]'") from exc
    return serial.Serial(name, baudrate=115200, timeout=timeout, write_timeout=5)


def save_capture(path: Path, data: bytes, header: dict) -> None:
    metadata = Path(str(path) + ".json")
    # Exclusive creation prevents overwriting an earlier reference acquisition.
    with path.open("xb") as output:
        try:
            meta_file = metadata.open("x")
        except OSError:
            path.unlink()
            raise
        with meta_file:
            output.write(data)
            meta_file.write(json.dumps({**header, "scl": 0, "sda": 1,
                                       "source": "pico2", "complete": True}, indent=2) + "\n")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect-hex":
            print(json.dumps(PicImage.read(args.file).report(), indent=2))
            return 0
        if args.command == "info":
            with open_port(args.port, 5) as port:
                port.write(b"INFO\n")
                print(json.dumps(read_header(port), indent=2))
            return 0
        if args.out.suffix != ".bin":
            raise ValueError("la sortie doit avoir l'extension .bin")
        if args.out.exists() or Path(str(args.out) + ".json").exists():
            raise ValueError("capture déjà présente : choisir un autre nom")
        validate_request(args.samplerate, args.samples)
        with open_port(args.port, min(300, 5 + args.samples / args.samplerate)) as port:
            data, header = capture(port, args.samplerate, args.samples)
        save_capture(args.out, data, header)
        print(f"{len(data)} échantillons à {header['samplerate']} Hz enregistrés dans {args.out}")
        return 0
    except (HexError, ProtocolError, ValueError, OSError) as exc:
        print(f"erreur : {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
