#!/usr/bin/env python3
"""Rapport hors matériel des trois images historiques, sans publier les HEX.

Usage : uv run python hardware/pico2/inspect_ba_images.py /chemin/ESSENSYS
"""
import json
from pathlib import Path
import sys

from essensys_pico.hex_image import PicImage

IMAGES = {
    "SC940D": "essensys-board-SC940/SC940D/Prog/ba v1_7 piece vie.hex",
    "SC941C": "essensys-board-SC941C/SC941C/Prog/ba v1_7 piece eau.hex",
    "SC942C": "essensys-board-SC942C/SC942C/Prog/ba v1_7 piece chambre.hex",
}


if __name__ == "__main__":
    root = Path(sys.argv[1])
    reports = [{"board": board, "source": relative, **PicImage.read(root / relative).report()}
               for board, relative in IMAGES.items()]
    print(json.dumps({"images": reports, "physical_qualification": "pending"}, indent=2))
