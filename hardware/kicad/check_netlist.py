#!/usr/bin/env python3
"""Vérifie que la netlist exportée par KiCad correspond au circuit voulu de la sonde.

Usage : kicad-cli sch export netlist --format kicadsexpr -o sonde.net sonde-i2c-passive.kicad_sch
        python3 check_netlist.py sonde.net
"""
import re
import sys

EXPECTED = {
    "+3V3": {"C1.1", "J2.1", "U1.5"},
    "0V": {"C1.2", "D1.3", "J1.3", "J2.4", "R3.2", "R4.2", "U1.2"},
    "SCL_BUS": {"J1.2", "R2.1"},
    "SDA_BUS": {"J1.1", "R1.1"},
    "SCL_IN": {"R2.2", "R4.1", "D1.2", "U1.1"},
    "SDA_IN": {"R1.2", "R3.1", "D1.1", "U1.3"},
    "SCL_OUT": {"J2.2", "U1.6"},
    "SDA_OUT": {"J2.3", "U1.4"},
}
UNCONNECTED = {"J1.4"}  # position 4 du connecteur (+15 V) : jamais raccordée


def main(path: str) -> int:
    text = open(path, encoding="utf-8").read()
    nets = text[text.index("(nets"):]
    got, loose = {}, set()
    for block in re.split(r"\n\s*\(net\n", nets)[1:]:
        name = re.search(r'\(name "([^"]*)"\)', block)[1].lstrip("/")
        nodes = {f"{r}.{p}" for r, p in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', block) if not r.startswith("#")}
        if name.startswith("unconnected"):
            loose |= nodes
        elif nodes:
            got[name] = nodes
    errors = [f"{n} : attendu {sorted(v)}, obtenu {sorted(got.get(n, set()))}" for n, v in EXPECTED.items() if got.get(n) != v]
    errors += [f"net inattendu : {n} {sorted(v)}" for n, v in got.items() if n not in EXPECTED]
    if loose != UNCONNECTED:
        errors.append(f"broches non raccordées : attendu {sorted(UNCONNECTED)}, obtenu {sorted(loose)}")
    for e in errors:
        print("ÉCART", e)
    print("netlist conforme" if not errors else "netlist NON conforme")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
