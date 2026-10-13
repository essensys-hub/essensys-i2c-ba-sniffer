"""Décodeur passif du bus I2C BP↔BA Essensys.

L'outil n'émet jamais sur le bus et ne pilote jamais l'armoire : il lit des
échantillons logiques (analyseur + sigrok) et les annotations du décodeur I2C
de sigrok, puis reconstruit et interprète le protocole Essensys.
"""

__version__ = "0.1.0"

#: Version du format NDJSON (champ ``schema`` de chaque enregistrement).
SCHEMA = "essensys-i2c-sniff/1"
