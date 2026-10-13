"""CLI ``essensys-i2c-sniff`` — espion **passif** du bus I2C BP↔BA.

Sous-commandes :

- ``live``        : acquisition par analyseur logique (sigrok, pilote fx2lafw par défaut) ;
- ``replay``      : rejeu d'une session ``.sr`` ou d'un flux brut ``.bin`` / ``.bin.gz`` ;
- ``annotations`` : décodage d'annotations sigrok enregistrées (PulseView, sigrok-cli) ;
- ``correlate``   : rapprochement d'une capture NDJSON avec les journaux du backend CM5.

Aucune sous-commande n'émet sur le bus ni ne contacte l'armoire ou le CM5.
"""

from __future__ import annotations

import argparse
import gzip
import json
import queue
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

from . import SCHEMA, __version__
from .correlate import correlate, parse_backend_log
from .output import to_ndjson, to_text
from .pipeline import Decoder, pd_command, run_stream, sigrok_bin
from .semantics import DEFAULT_PROFILES, Profile

MIN_SAMPLERATE = 1_000_000
CHUNK = 65536


def parse_samplerate(text: str) -> int:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([kKmM]?)(?:hz|Hz|HZ)?\s*", text)
    if not m:
        raise argparse.ArgumentTypeError(f"fréquence invalide : {text}")
    value = float(m[1]) * {"": 1, "k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6}[m[2]]
    return int(value)


def check_samplerate(rate: int) -> None:
    if rate < MIN_SAMPLERATE:
        raise SystemExit(
            f"erreur : fréquence d'échantillonnage {rate} Hz refusée — minimum {MIN_SAMPLERATE} Hz "
            "(20 fois le débit du bus à 50 kHz)."
        )


def load_profiles(path: str | None) -> dict[int, Profile]:
    profiles = dict(DEFAULT_PROFILES)
    if path:
        for addr, p in json.loads(Path(path).read_text()).items():
            profiles[int(addr, 16)] = Profile(int(p["lamps"]), int(p["dimmers"]), int(p["shutters"]))
    return profiles


class Printer:
    def __init__(self, fmt: str, stream=None) -> None:
        self.fmt = fmt
        self.stream = stream or sys.stdout
        self.records: list[dict] = []

    def __call__(self, rec: dict) -> None:
        self.records.append(rec)
        self.stream.write((to_ndjson(rec) if self.fmt == "ndjson" else to_text(rec)) + "\n")
        self.stream.flush()


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--scl", type=int, default=0, help="numéro de voie de SCL (défaut 0 = D0)")
    p.add_argument("--sda", type=int, default=1, help="numéro de voie de SDA (défaut 1 = D1)")
    p.add_argument("--format", choices=("text", "ndjson"), default="text")
    p.add_argument("--profiles", help="JSON {\"0x12\": {\"lamps\":7,\"dimmers\":4,\"shutters\":5}, …}")
    p.add_argument("--stuck-ms", type=float, default=10.0, help="seuil de ligne bloquée au niveau bas (ms)")
    p.add_argument("--repeat-window", type=float, default=2.0, help="fenêtre de répétition / abandon (s)")
    p.add_argument("--state", action="store_true", help="afficher l'état commandé inféré en fin de session")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="essensys-i2c-sniff", description="Espion passif du bus I2C BP↔BA Essensys (lecture seule).")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__} ({SCHEMA})")
    sub = parser.add_subparsers(dest="command", required=True)

    live = sub.add_parser("live", help="capture en direct par analyseur logique (sigrok)")
    live.add_argument("--driver", default="fx2lafw")
    live.add_argument("--samplerate", type=parse_samplerate, default=MIN_SAMPLERATE)
    live.add_argument("--duration", type=float, help="durée de capture en secondes (défaut : jusqu'à Ctrl-C)")
    live.add_argument("--raw-out", help="enregistrer aussi le flux brut (.bin) et ses métadonnées (.json) pour rejeu")
    _common(live)

    replay = sub.add_parser("replay", help="rejeu d'une capture .sr, .bin ou .bin.gz")
    replay.add_argument("file")
    replay.add_argument("--samplerate", type=parse_samplerate, help="obligatoire pour un .bin sans fichier .json associé")
    _common(replay)

    ann = sub.add_parser("annotations", help="décoder des annotations i2c sigrok enregistrées (sans flux brut)")
    ann.add_argument("file")
    ann.add_argument("--samplerate", type=parse_samplerate, required=True)
    _common(ann)

    cor = sub.add_parser("correlate", help="rapprocher une capture NDJSON des journaux du backend CM5")
    cor.add_argument("--capture", required=True, help="capture au format NDJSON (avec son enregistrement session)")
    cor.add_argument("--backend-log", required=True, help="fichier exporté de « docker logs essensys-backend »")
    cor.add_argument("--capture-start", help="heure locale de début de capture AAAA-MM-JJTHH:MM:SS (sinon : session)")
    cor.add_argument("--offset", type=float, help="décalage capture − journaux en secondes (sinon : recalage automatique)")
    cor.add_argument("--window", type=float, default=5.0, help="fenêtre de recherche après l'acquittement (s)")
    cor.add_argument("--format", choices=("text", "ndjson"), default="text")
    return parser


def _decoder(args, samplerate: int, use_raw: bool = True) -> Decoder:
    return Decoder(
        samplerate, scl_bit=args.scl, sda_bit=args.sda, profiles=load_profiles(args.profiles),
        stuck_ms=args.stuck_ms, repeat_window_s=args.repeat_window, use_raw=use_raw,
    )


def _session(printer: Printer, source: str, samplerate: int, start: datetime | None) -> None:
    printer({"type": "session", "sample": 0, "t_ms": 0.0, "source": source, "samplerate": samplerate,
             "start_time": start.isoformat(timespec="seconds") if start else None, "tool": __version__})


def _end(printer: Printer, dec: Decoder, args) -> None:
    if args.state:
        summary = dec.frames.state.summary()
        if printer.fmt == "ndjson":
            printer({"type": "state", "sample": 0, "t_ms": 0.0, **summary})
        else:
            print(json.dumps(summary, ensure_ascii=False, indent=2))


def cmd_live(args) -> int:
    check_samplerate(args.samplerate)
    printer = Printer(args.format)
    start = datetime.now()
    _session(printer, f"live:{args.driver}", args.samplerate, start)
    acq = [sigrok_bin(), "-d", args.driver, "--config", f"samplerate={args.samplerate}", "-O", "binary"]
    acq += ["--time", f"{int(args.duration * 1000)}"] if args.duration else ["--continuous"]
    proc = subprocess.Popen(acq, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    messages: "queue.Queue[str]" = queue.Queue()

    def errors() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            messages.put(line.decode("utf-8", "replace"))

    threading.Thread(target=errors, daemon=True).start()
    raw_out = open(args.raw_out, "wb") if args.raw_out else None
    if args.raw_out:
        Path(args.raw_out + ".json").write_text(json.dumps({"samplerate": args.samplerate, "start_time": start.isoformat(timespec="seconds"), "scl": args.scl, "sda": args.sda}))

    def chunks():
        assert proc.stdout is not None
        while True:
            data = proc.stdout.read1(CHUNK)
            if not data:
                return
            if raw_out:
                raw_out.write(data)
            yield data

    dec = _decoder(args, args.samplerate)
    try:
        run_stream(chunks(), dec, pd_command(args.samplerate, args.scl, args.sda), printer, messages, idle_seconds=1.0)
    except KeyboardInterrupt:
        proc.terminate()
    finally:
        if raw_out:
            raw_out.close()
    _end(printer, dec, args)
    return 0


def _read_meta(path: Path) -> dict:
    meta = Path(str(path) + ".json")
    if not meta.exists() and path.suffix == ".gz":
        meta = path.with_suffix("").with_suffix(".bin.json")
    return json.loads(meta.read_text()) if meta.exists() else {}


def cmd_replay(args) -> int:
    path = Path(args.file)
    printer = Printer(args.format)
    start = None
    if path.suffix == ".sr":
        show = subprocess.run([sigrok_bin(), "-i", str(path), "--show"], capture_output=True, text=True, check=True).stdout
        rate = int(re.search(r"Samplerate:\s*(\d+)", show)[1])
        unit = re.search(r"Logic unitsize:\s*(\d+)", show)
        if unit and int(unit[1]) != 1:
            raise SystemExit("erreur : seules les captures de 8 voies au plus (unitsize 1) sont prises en charge")
        raw = subprocess.run([sigrok_bin(), "-i", str(path), "-O", "binary"], capture_output=True, check=True).stdout
    else:
        meta = _read_meta(path)
        rate = args.samplerate or meta.get("samplerate")
        if not rate:
            raise SystemExit("erreur : --samplerate est obligatoire pour ce fichier")
        if meta.get("start_time"):
            start = datetime.fromisoformat(meta["start_time"])
        raw = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    check_samplerate(rate)
    _session(printer, f"replay:{path.name}", rate, start)
    dec = _decoder(args, rate)
    run_stream((raw[i:i + CHUNK] for i in range(0, len(raw), CHUNK)), dec, pd_command(rate, args.scl, args.sda), printer)
    _end(printer, dec, args)
    return 0


def cmd_annotations(args) -> int:
    check_samplerate(args.samplerate)
    printer = Printer(args.format)
    _session(printer, f"annotations:{Path(args.file).name}", args.samplerate, None)
    dec = _decoder(args, args.samplerate, use_raw=False)
    for line in Path(args.file).read_text().splitlines():
        for rec in dec.feed_annotation(line):
            printer(rec)
    for rec in dec.finish():
        printer(rec)
    _end(printer, dec, args)
    return 0


def cmd_correlate(args) -> int:
    records = [json.loads(line) for line in Path(args.capture).read_text().splitlines() if line.strip()]
    session = next((r for r in records if r.get("type") == "session"), {})
    start_text = args.capture_start or session.get("start_time")
    if not start_text:
        raise SystemExit("erreur : heure de début de capture inconnue, utiliser --capture-start")
    actions = parse_backend_log(Path(args.backend_log).read_text(errors="replace").splitlines())
    results, offset = correlate(actions, records, datetime.fromisoformat(start_text), args.offset, args.window)
    printer = Printer(args.format)
    if args.format == "text":
        print(f"décalage d'horloge retenu : {offset:+.1f} s ({'fourni' if args.offset is not None else 'automatique'})")
    for rec in results:
        rec.update(sample=0, t_ms=0.0)
        printer(rec)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return {"live": cmd_live, "replay": cmd_replay, "annotations": cmd_annotations, "correlate": cmd_correlate}[args.command](args)
    except BrokenPipeError:  # sortie fermée par le lecteur (ex. « | head »)
        import os
        os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    sys.exit(main())
